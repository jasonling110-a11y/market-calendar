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


def collect_tokens(token, base_tree):
    """本地内容与远程 tree 不一致的文件。

    为什么不用 git diff：远程的 commit 常常是**本脚本自己用 API 建的**，
    它不存在于本地对象库，于是 `git diff origin/main..HEAD` 会失败；
    而退回「最新一次提交涉及的文件」又会漏掉中间几次提交改过的文件
    （实测漏掉过 macro_series.json 这类源数据）。

    所以这里改成**按内容比对**：拿远程 tree 里每个文件的 blob sha，
    和本地工作区文件算出的 sha 逐一对齐。与提交拓扑无关，也永远不会漏。
    """
    remote = {}
    if base_tree:
        tree = call(token, "GET", f"/repos/{OWNER}/{REPO}/git/trees/{base_tree}?recursive=1")
        for e in (tree or {}).get("tree", []):
            if e.get("type") == "blob":
                remote[e["path"]] = e["sha"]

    r = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    tracked = [l for l in r.stdout.split("\n") if l.strip()]
    if not tracked:
        return []

    # 用工作区文件内容算 sha（而不是 index），这样未提交的改动也不会漏
    h = subprocess.run(["git", "hash-object", "--stdin-paths"], cwd=ROOT,
                       input="\n".join(tracked), capture_output=True, text=True)
    local_sha = [l.strip() for l in h.stdout.split("\n") if l.strip()]

    out = []
    for path, sha in zip(tracked, local_sha):
        if not os.path.isfile(os.path.join(ROOT, path)):
            continue                                  # 删除需要 sha:null，这里不处理
        if remote.get(path) != sha:
            out.append(path)
    return out


def main():
    argv = sys.argv[1:]
    dry = "--dry" in argv
    argv = [a for a in argv if a != "--dry"]

    token = load_token()
    os.chdir(ROOT)

    # 先读远程 HEAD / tree —— 待推送清单要按内容跟它对，必须在收集文件之前拿到
    ref = call(token, "GET", f"/repos/{OWNER}/{REPO}/git/ref/heads/main")
    if not ref:
        print("  无法读取远程 HEAD")
        return 1
    head_sha = ref["object"]["sha"]
    base_tree = call(token, "GET", f"/repos/{OWNER}/{REPO}/git/commits/{head_sha}")["tree"]["sha"]

    if argv:
        names = argv
    else:
        names = collect_tokens(token, base_tree)
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
