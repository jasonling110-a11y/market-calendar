#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub 一键部署：把「市场日历」发布到 GitHub Pages，并让 Actions 每天自动更新。

设计目标：用户只需在浏览器点一次授权，其余全部自动完成。

流程：
    --auth    申请设备码（展示给用户去浏览器确认）
    --wait    轮询等待授权 → 建仓库 → 推送 → 开启 Pages → 配置密钥 → 触发首次运行
    status    查看当前部署状态

为什么用「设备码授权」而不是让用户手动创建 token：
    手动创建 PAT 要找页面、选权限、复制粘贴，对用户来说步骤多；
    设备码只需在浏览器输入一个 8 位码。这是 GitHub 官方支持的 OAuth 流程，
    也是 GitHub CLI 自己用的方式。

安全说明：
    - token 存在 ~/.market-calendar.github.json（项目目录之外），权限 600，不会被 git 提交
    - 推送时通过 git 的 credential 参数临时传入，token 不写入 .git/config
    - 只申请 repo / workflow / read:org 三个权限
"""

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# GitHub CLI 的公开 client_id（开源，非机密）
CLIENT_ID = "178c6fc778ccc68e1d6a"
SCOPE = "repo workflow read:org"
REPO_NAME = "market-calendar"
REPO_DESC = "市场日历：财经日历 + 历史回顾 + 未来预告 + 个人复盘笔记"
REPO_HOME = "https://github.com/" + REPO_NAME

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOKEN_FILE = os.path.expanduser("~/.market-calendar.github.json")
DEVICE_FILE = "/tmp/mc_device.json"
PUSHPLUS_FILE = os.path.expanduser("~/.market-calendar.push.json")

UA = "market-calendar-deploy"


# ---------------------------------------------------------------- 基础工具
def log(msg=""):
    print(msg, flush=True)


def api(method, path, token=None, body=None, accept="application/vnd.github+json"):
    """调 GitHub API。path 可传完整 URL 或 /repos/... 简写"""
    url = path if path.startswith("http") else "https://api.github.com" + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", accept)
    req.add_header("User-Agent", UA)
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "ignore")
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw[:300]}
    except Exception as e:
        return 0, {"error": f"{type(e).__name__}: {e}"}


def form_post(url, fields):
    """application/x-www-form-urlencoded POST（device flow 用）"""
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        try:
            return json.loads(raw)
        except ValueError:
            return {"error": "http_" + str(e.code), "raw": raw[:200]}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def run(cmd, env=None, cwd=ROOT, quiet=True):
    r = subprocess.run(cmd, cwd=cwd, env=env,
                       capture_output=True, text=True)
    if not quiet and r.stdout:
        log(r.stdout.rstrip())
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def save_token(token, login):
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump({"token": token, "login": login, "at": int(time.time())}, f)
    os.chmod(TOKEN_FILE, 0o600)


def load_token():
    if not os.path.exists(TOKEN_FILE):
        return None, None
    try:
        with open(TOKEN_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("token"), d.get("login")
    except Exception:
        return None, None


# ---------------------------------------------------------------- 1. 授权
def step_auth():
    """申请设备码，打印给用户"""
    d = form_post("https://github.com/login/device/code",
                  {"client_id": CLIENT_ID, "scope": SCOPE})
    if not d.get("user_code"):
        log("[✗] 申请设备码失败：" + json.dumps(d, ensure_ascii=False)[:300])
        return 1
    with open(DEVICE_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f)
    log("USER_CODE=" + d["user_code"])
    log("VERIFY_URL=" + d.get("verification_uri", "https://github.com/login/device"))
    log("EXPIRES_IN=" + str(d.get("expires_in")))
    return 0


def step_wait():
    """轮询等待授权，成功后自动继续部署"""
    if not os.path.exists(DEVICE_FILE):
        log("[✗] 找不到设备码，请先跑 --auth")
        return 1
    with open(DEVICE_FILE, encoding="utf-8") as f:
        dev = json.load(f)

    device_code = dev["device_code"]
    interval = max(5, int(dev.get("interval", 5)))
    deadline = time.time() + int(dev.get("expires_in", 900)) - 10

    log("[1/6] 等待你在浏览器完成授权 ...")
    token = None
    netfail = 0
    while time.time() < deadline:
        time.sleep(interval)
        r = form_post("https://github.com/login/oauth/access_token", {
            "client_id": CLIENT_ID,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        })
        err = r.get("error")
        if r.get("access_token"):
            token = r["access_token"]
            break
        if err == "authorization_pending":
            netfail = 0          # 能正常应答说明网络是好的
            continue
        if err == "slow_down":
            interval += 5
            continue
        if err == "expired_token":
            log("[✗] 授权码已过期（15 分钟有效）。请让我重新申请一个。")
            return 2
        if err == "access_denied":
            log("[✗] 你取消了授权。如果不想部署，随时告诉我。")
            return 3

        # 网络抖动不能当成失败：实测代理会间歇性返回 502
        # （"Tunnel connection failed: 502 Bad Gateway"），重试即可恢复。
        # 这里只有「连续失败」才放弃，中间成功一次就清零。
        text = str(err) + str(r.get("raw", ""))
        flaky = any(k in text for k in (
            "URLError", "urlopen", "Bad Gateway", "timed out",
            "Connection", "SSL", "Tunnel", "Remote end closed"))
        if flaky:
            netfail += 1
            if netfail <= 3 or netfail % 12 == 0:
                log(f"      [i] 网络抖动，重试中（连续第 {netfail} 次）：{text[:60]}")
            if netfail > 60:
                log("[✗] 连续网络失败过多（约 5 分钟），请稍后让我重试")
                return 4
            interval = max(interval, 6)
            continue

        log("[!] 授权返回异常：" + json.dumps(r, ensure_ascii=False)[:200])
        return 4

    if not token:
        log("[✗] 等待超时（授权码 15 分钟内有效）。请让我重新申请一个。")
        return 2

    st, me = api("GET", "/user", token)
    if st != 200 or not me.get("login"):
        log("[✗] 拿到 token 但无法读取账号信息：" + json.dumps(me, ensure_ascii=False)[:200])
        return 5
    login = me["login"]
    save_token(token, login)
    log(f"[✓] 授权成功，账号：{login}")

    return deploy(token, login)


# ---------------------------------------------------------------- 2. 部署
def deploy(token, login):
    repo = f"{login}/{REPO_NAME}"

    # ---- 建仓库 ----
    log("")
    log("[2/6] 创建仓库 ...")
    st, r = api("GET", f"/repos/{repo}", token)
    if st == 200:
        log(f"      仓库已存在：{r.get('html_url')}")
    else:
        st, r = api("POST", "/user/repos", token, {
            "name": REPO_NAME,
            "description": REPO_DESC,
            "homepage": f"https://{login}.github.io/{REPO_NAME}/",
            "private": False,          # 免费版 Pages 需要公开仓库
            "has_issues": False,
            "has_projects": False,
            "has_wiki": False,
            "auto_init": False,
        })
        if st not in (200, 201):
            log("[✗] 创建仓库失败：" + json.dumps(r, ensure_ascii=False)[:300])
            return 6
        log(f"      ✓ 已创建：{r.get('html_url')}")

    # ---- 推送 ----
    log("")
    log("[3/6] 推送代码 ...")
    url = f"https://github.com/{repo}.git"
    rc, out, err = run(["git", "remote", "get-url", "origin"])
    if rc == 0:
        run(["git", "remote", "set-url", "origin", url])
    else:
        run(["git", "remote", "add", "origin", url])

    run(["git", "branch", "-M", "main"])

    # token 通过 git 的 credential 参数临时传入，不落 .git/config
    helper = ('!f() { echo username=x-access-token; '
              'echo "password=$MC_GH_TOKEN"; }; f')
    env = dict(os.environ)
    env["MC_GH_TOKEN"] = token
    env["GIT_TERMINAL_PROMPT"] = "0"
    push_cmd = ["git", "-c", "credential.helper=",
                "-c", f"credential.helper={helper}",
                "push", "-u", "origin", "main"]
    rc, out, err = 1, "", ""
    last = ""
    for attempt in range(1, 4):
        rc, out, err = run(push_cmd, env=env, quiet=True)
        if rc == 0:
            break
        last = (err or out)
        if attempt < 3:
            log(f"      推送未成功，10 秒后重试（第 {attempt}/3 次）：{last[:100]}")
            time.sleep(10)
    if rc != 0:
        log("[✗] 推送失败：" + last[:400])
        return 7
    log("      ✓ 已推送 main 分支")

    # 确认 token 没被写进 config
    cfg = os.path.join(ROOT, ".git", "config")
    if os.path.exists(cfg):
        with open(cfg, encoding="utf-8") as f:
            body = f.read()
        if token[:12] in body:
            log("      [!] 检测到 token 残留于 .git/config，正在清理")
            run(["git", "remote", "set-url", "origin", url])

    # ---- 开启 Pages ----
    log("")
    log("[4/6] 开启 GitHub Pages ...")
    st, r = api("GET", f"/repos/{repo}/pages", token)
    if st == 200:
        log(f"      Pages 已开启：{r.get('html_url')}")
        api("PUT", f"/repos/{repo}/pages", token, {
            "source": {"branch": "main", "path": "/docs"},
        })
        log("      已确认指向 main 分支的 /docs 目录")
    else:
        st, r = api("POST", f"/repos/{repo}/pages", token, {
            "source": {"branch": "main", "path": "/docs"},
        })
        if st in (200, 201):
            log("      ✓ 已开启：" + str(r.get("html_url")))
            log(f"      访问地址：https://{login}.github.io/{REPO_NAME}/")
        else:
            # Pages 有时需要几秒等仓库初始化，重试一次
            time.sleep(6)
            st, r = api("POST", f"/repos/{repo}/pages", token, {
                "source": {"branch": "main", "path": "/docs"},
            })
            if st in (200, 201):
                log("      ✓ 已开启（重试成功）")
            else:
                log("      [!] 开启 Pages 未成功：" + json.dumps(r, ensure_ascii=False)[:250])
                log("          稍后可在仓库 Settings → Pages 手动选 main / docs")

    # ---- 配置推送密钥（可选）----
    log("")
    log("[5/6] 配置微信推送密钥 ...")
    pp = None
    if os.path.exists(PUSHPLUS_FILE):
        try:
            with open(PUSHPLUS_FILE, encoding="utf-8") as f:
                pp = json.load(f).get("token")
        except Exception:
            pp = None
    if not pp:
        log("      跳过：本机未配置 PushPlus token（推送是可选的，不影响日历订阅）")
    else:
        st, pk = api("GET", f"/repos/{repo}/actions/secrets/public-key", token)
        if st != 200:
            log("      [!] 读取仓库公钥失败，跳过")
        else:
            try:
                from nacl import public as nacl_public
                box = nacl_public.SealedBox(
                    nacl_public.PublicKey(base64.b64decode(pk["key"])))
                enc = base64.b64encode(box.encrypt(pp.encode("utf-8"))).decode()
                st, r = api("PUT",
                            f"/repos/{repo}/actions/secrets/PUSHPLUS_TOKEN",
                            token,
                            {"encrypted_value": enc, "key_id": pk["key_id"]})
                log("      ✓ 已加密写入 PUSHPLUS_TOKEN" if st in (201, 204)
                    else "      [!] 写入失败：" + json.dumps(r, ensure_ascii=False)[:200])
            except ImportError:
                log("      [!] 本机缺少 pynacl，无法加密，跳过（可稍后在网页手动添加）")

    # ---- 触发首次运行 ----
    log("")
    log("[6/6] 触发首次自动运行 ...")
    st, r = api("POST",
                f"/repos/{repo}/actions/workflows/daily.yml/dispatches",
                token, {"ref": "main"})
    if st in (204, 201, 202):
        log("      ✓ 已触发（约 2 分钟跑完）")
    else:
        log("      [!] 触发未成功：" + json.dumps(r, ensure_ascii=False)[:250])
        log("          不影响定时任务，明天 21:00 会自己跑；也可在网页 Actions 页手动点 Run workflow")

    # ---- 汇总 ----
    log("")
    log("=" * 62)
    log("  部署完成")
    log("=" * 62)
    log(f"  仓库：      https://github.com/{repo}")
    log(f"  订阅入口：  https://{login}.github.io/{REPO_NAME}/")
    log(f"  日历订阅：  https://{login}.github.io/{REPO_NAME}/market-calendar.ics")
    log(f"  完整网页版：https://{login}.github.io/{REPO_NAME}/app.html")
    log("")
    log("  订阅方式：用 Safari 打开「订阅入口」，点「订阅到 iPhone 日历」")
    log("  自动更新：每天 21:00（北京时间），你的 Mac 关机也照样跑")
    log("=" * 62)
    return 0


def step_status():
    token, login = load_token()
    if not token:
        log("尚未授权。")
        return 1
    st, me = api("GET", "/user", token)
    if st != 200:
        log(f"[✗] token 已失效（HTTP {st}），需要重新授权")
        return 2
    login = me["login"]
    repo = f"{login}/{REPO_NAME}"
    log(f"账号：{login}")
    st, r = api("GET", f"/repos/{repo}", token)
    log(f"仓库：{'✓ ' + r.get('html_url', '') if st == 200 else '✗ 不存在'}")
    st, r = api("GET", f"/repos/{repo}/pages", token)
    if st == 200:
        log(f"Pages：✓ {r.get('html_url')} ({r.get('status')})")
    else:
        log("Pages：✗ 未开启")
    st, r = api("GET", f"/repos/{repo}/actions/runs?per_page=3", token)
    if st == 200:
        log("最近运行：")
        for w in r.get("workflow_runs", [])[:3]:
            log(f"  {w.get('created_at','')[:16]}  {w.get('status')}/{w.get('conclusion')}")
    return 0


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "--auth"
    if arg == "--auth":
        return step_auth()
    if arg == "--wait":
        return step_wait()
    if arg == "status":
        return step_status()
    log(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
