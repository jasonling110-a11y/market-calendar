#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通过 GitHub API 推送文件（git push 的备用通道）。

为什么需要它：
    某些网络环境下 `github.com` 会被代理拦截（实测返回 502 CONNECT tunnel failed），
    但 `api.github.com` 是通的。此时 `git push` 完全用不了，
    而 Git Data API 仍然能正常提交。

用法：
    python3 tools/push_via_api.py                        # 推送所有未推送的改动
    python3 tools/push_via_api.py docs/app.html          # 只推送指定文件
    python3 tools/push_via_api.py --dry docs/            # 只看会推什么

依赖：只用 Python 标准库。token 从 ~/.market-calendar.github.json 读取。
"""

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

TOKEN_FILE = os.path.expanduser("~/.market-calendar.github.json")
OWNER = "jasonling110-a11y"
REPO = "market-calendar"
API = "https://api.github.com"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load_token():
    if not os.path.exists(TOKEN_FILE):
        print(f"[✗] 找不到 {TOKEN_FILE}")
        sys.exit(1)
    with open(TOKEN_FILE, encoding="utf-8") as f:
        return json.load(f)["token"]


def call(token, method, path, body=None, timeout=180):
    """调 API，带 3 次重试（代理层偶发 502）"""
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "market-calendar")
    if data:
        req.add_header("Content-Type", "application/json")
    last = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8", "ignore")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} " + e.read().decode("utf-8", "ignore")[:200]
            if e.code in (502, 503, 504) and attempt < 2:
                time.sleep(5)
                continue
            print(f"  [✗] {method} {path} → {last}")
            return None
        except Exception as e:                      # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
            if attempt < 2:
                time.sleep(5)
                continue
            print(f"  [✗] {method} {path} → {last}")
            return None
    return None


def collect_tokens():
    """未推送的改动文件。远程 ref 在本地对象库可能不存在（API 创建的 commit），
    这时退回到「本地 HEAD 相对部署目录」的简单判断。"""
    r = subprocess.run(["git", "-c", "core.quotepath=false", "status", "--porcelain"],
                       cwd=ROOT, capture_output=True, text=True)
    files = []
    for line in r.stdout.split("\n"):
        if not line.strip():
            continue
        status, path = line[:2], line[3:].strip()
        if status.strip() in ("D",):
            continue                                 # 删除需要 sha:null，这里不处理
        files.append(path)
    # 已提交但未推送的：优先与远程比对；远程 ref 在本地对象库不存在时
    # （用 API 创建过 commit 就会这样）退回到「最新一次提交涉及的文件」
    r2 = subprocess.run(["git", "-c", "core.quotepath=false", "diff", "--name-only",
                         "origin/main..HEAD"], cwd=ROOT, capture_output=True, text=True)
    if r2.returncode == 0 and r2.stdout.strip():
        for line in r2.stdout.split("\n"):
            if line.strip():
                files.append(line.strip())
    else:
        r3 = subprocess.run(["git", "-c", "core.quotepath=false", "show",
                             "--name-only", "--pretty=format:", "HEAD"],
                            cwd=ROOT, capture_output=True, text=True)
        for line in r3.stdout.split("\n"):
            if line.strip():
                files.append(line.strip())
    seen, out = set(), []
    for f in files:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def main():
    argv = sys.argv[1:]
    dry = "--dry" in argv
    argv = [a for a in argv if a != "--dry"]

    token = load_token()
    os.chdir(ROOT)

    if argv:
        names = argv
    else:
        names = collect_tokens()
        if not names:
            print("  没有可推送的改动")
            return 0

    names = [n for n in names if os.path.isfile(n)]
    if not names:
        print("  没有可推送的文件")
        return 0

    print(f"  待推送 {len(names)} 个文件：")
    total = 0
    for n in names:
        sz = os.path.getsize(n)
        total += sz
        print(f"    {sz/1024:>8.1f} KB  {n}")
    print(f"    合计 {total/1024/1024:.2f} MB")

    if dry:
        print("  （--dry，未实际推送）")
        return 0

    # ---- 远程当前 HEAD ----
    ref = call(token, "GET", f"/repos/{OWNER}/{REPO}/git/ref/heads/main")
    if not ref:
        print("  无法读取远程 HEAD")
        return 1
    head_sha = ref["object"]["sha"]
    base_tree = call(token, "GET", f"/repos/{OWNER}/{REPO}/git/commits/{head_sha}")["tree"]["sha"]
    print(f"\n  远程 HEAD {head_sha[:8]} / tree {base_tree[:8]}")

    entries = []
    for i, path in enumerate(names, 1):
        with open(path, "rb") as f:
            blob = f.read()
        res = call(token, "POST", f"/repos/{OWNER}/{REPO}/git/blobs",
                   {"content": base64.b64encode(blob).decode(), "encoding": "base64"})
        if not res:
            print(f"    [{i}/{len(names)}] ✗ 上传失败：{path}")
            return 1
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": res["sha"]})
        print(f"    [{i}/{len(names)}] ✓ {path}")

    tree = call(token, "POST", f"/repos/{OWNER}/{REPO}/git/trees",
                {"base_tree": base_tree, "tree": entries})
    if not tree:
        print("  ✗ 建 tree 失败")
        return 1

    msg = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip() or "更新"
    commit = call(token, "POST", f"/repos/{OWNER}/{REPO}/git/commits",
                  {"message": msg, "tree": tree["sha"], "parents": [head_sha]})
    if not commit:
        print("  ✗ 建 commit 失败")
        return 1

    upd = call(token, "PATCH", f"/repos/{OWNER}/{REPO}/git/refs/heads/main",
               {"sha": commit["sha"], "force": False})
    if not upd:
        print("  ✗ 更新分支失败")
        return 1

    print(f"\n  ✓ 推送成功，main → {upd['object']['sha'][:8]}")
    print(f"    仓库：https://github.com/{OWNER}/{REPO}")
    print(f"    页面：https://{OWNER}.github.io/{REPO}/  （Pages 约 1～2 分钟后重新发布）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
