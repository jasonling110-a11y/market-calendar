# -*- coding: utf-8 -*-
"""
每日摘要推送到微信（PushPlus）

为什么用 PushPlus：个人使用场景下它最省事——你不用装新 App，
关注一个公众号就能收到推送，免费额度每天 200 条，日常够用。

推送内容（今天该看什么）：
  1. 今日财经日历（★★ 以上，按时间排序）
  2. 今日已公布数值（实际 / 预期 / 前值）
  3. 今日 UP 主视频要点
  4. 明日重点前瞻

Token 存放位置（按优先级）：
  1. 环境变量 PUSHPLUS_TOKEN
  2. ~/.market-calendar.push.json   ->  {"token": "xxxx", "topic": ""}
     （故意放在项目之外：token 等同密码，不该跟着项目被同步出去）

用法：
    python3 push_daily.py --dry     # 只打印将要推送的内容，不发送
    python3 push_daily.py           # 真正发送
    python3 push_daily.py --test    # 发一条测试消息，验证 token 是否有效
"""
import datetime as dt
import json
import os
import ssl
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "miniprogram", "data")
CONF = os.path.join(os.path.expanduser("~"), ".market-calendar.push.json")

API = "https://www.pushplus.plus/send"
MIN_IMP = 2                 # 只推 ★★ 以上；不然一天几十条没人看
TZ = dt.timezone(dt.timedelta(hours=8))


def load_js(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    return json.loads(src.split("module.exports = ", 1)[1].rstrip().rstrip(";"))


def get_token():
    t = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    if t:
        return t, os.environ.get("PUSHPLUS_TOPIC", "")
    if os.path.exists(CONF):
        try:
            with open(CONF, encoding="utf-8") as f:
                d = json.load(f)
            tk = str(d.get("token") or "").strip()
            if tk:
                return tk, str(d.get("topic") or "")
        except Exception:
            pass
    return "", ""


def num(v):
    if v is None:
        return ""
    n = float(v)
    if n == int(n):
        return str(int(n))
    return ("%.2f" % n).rstrip("0").rstrip(".")


def pd_text(pd):
    if not pd or len(pd) != 4:
        return ""
    return str(int(pd[2:])) + " 月"


def compose(day, HIST, META, IND, C, N):
    """组装某一天的区块，返回 markdown 行列表"""
    d = HIST.get(day) or {}
    vals = {p[0]: p for p in (d.get("v") or [])}
    out = []

    # ---- 财经日历（按时间排序，全天排最后）----
    rows = []
    for e in (d.get("c") or []):
        tm, ci, ni, imp, kind, pd, mk = (list(e) + [""] * 7)[:7]
        if imp < MIN_IMP:
            continue
        co = C[ci] if ci is not None and ci < len(C) else ""
        nm = N[ni] if ni is not None and ni < len(N) else ""
        v = vals.get(mk) if mk else None
        val = ""
        if v and v[1] is not None:
            val = "　实 **" + num(v[1]) + (IND.get(mk) or {}).get("u", "") + "**"
        rows.append((tm or "99:99", tm or "全天", imp, co, nm, val))
    rows.sort(key=lambda x: (x[0], -x[2]))

    if rows:
        out.append("### 财经日历（" + str(len(rows)) + " 项）")
        for _, tms, imp, co, nm, val in rows:
            star = "`★★★`" if imp >= 3 else "`★★`"
            loc = ("**" + co + "** ") if co else ""
            out.append("- `" + tms + "` " + star + " " + loc + nm + val)
    else:
        out.append("### 财经日历")
        out.append("- 无 ★★ 以上安排")

    # ---- 关键数值（日历行没挂上的那些）----
    linked = set()
    for e in (d.get("c") or []):
        if len(e) > 6 and e[6]:
            linked.add(e[6])
    kv = []
    for k, p in vals.items():
        if k in linked or p[1] is None:
            continue
        m = IND.get(k) or {}
        line = "- **" + m.get("n", k) + "** 实际 **" + num(p[1]) + m.get("u", "") + "**"
        if p[2] is not None:
            line += "　预期 " + num(p[2]) + m.get("u", "")
        if p[3] is not None:
            line += "　前值 " + num(p[3]) + m.get("u", "")
        kv.append((-(m.get("i") or 2), line))
    if kv:
        kv.sort(key=lambda x: x[0])
        out.append("### 关键数值")
        out += [x[1] for x in kv[:8]]

    # ---- UP 主观点 ----
    for u in (d.get("u") or []):
        pts = (u.get("p") or [])[:6]
        if not pts:
            continue
        out.append("### UP 主观点")
        out.append("**" + (u.get("t") or "") + "**")
        out += ["- " + x for x in pts]
        out.append("[看原视频](https://www.bilibili.com/video/" + u.get("k", "") + ")")

    return out


def build_markdown():
    HIST = load_js(os.path.join(DATA, "history.js"))
    META = load_js(os.path.join(DATA, "meta.js"))
    IND = META.get("indicators", {})
    C, N = META.get("calCountries", []), META.get("calNames", [])

    today = dt.datetime.now(TZ).date()
    # --date=2026-10-28 可指定日期，便于预览/核对某天的推送内容
    for a in sys.argv:
        if a.startswith("--date="):
            try:
                today = dt.date.fromisoformat(a.split("=", 1)[1])
            except ValueError:
                print("[!] --date 格式应为 --date=YYYY-MM-DD")
                raise SystemExit(1)
    t, tm1 = today.isoformat(), (today + dt.timedelta(days=1)).isoformat()

    md = ["## " + str(today.month) + " 月 " + str(today.day) + " 日 市场日历", ""]
    md += compose(t, HIST, META, IND, C, N)

    nxt = compose(tm1, HIST, META, IND, C, N)
    if nxt:
        md += ["", "---", "", "### 明天前瞻", ""] + nxt[:12]

    md += ["", "---", "",
           "数据来源：东方财富 · 金十数据中心　|　仅供参考，不构成投资建议"]
    return "\n".join(md), today


def send(token, topic, title, content, dry=False, template="markdown"):
    body = {"token": token, "title": title, "content": content, "template": template}
    if topic:
        body["topic"] = topic
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    if dry:
        print("[dry-run] 不发送。请求体：")
        print(json.dumps(body, ensure_ascii=False, indent=1)[:1500])
        return True
    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        API, data=payload,
        headers={"Content-Type": "application/json; charset=utf-8",
                 "User-Agent": "market-calendar/1.0"})
    try:
        r = urllib.request.urlopen(req, timeout=20, context=ctx)
        res = json.loads(r.read().decode("utf-8", "ignore"))
        ok = res.get("code") == 200
        print(("[✓] 推送成功 " if ok else "[!] 推送失败 ") + json.dumps(res, ensure_ascii=False))
        return ok
    except Exception as e:
        print("[!] 推送请求异常：" + type(e).__name__ + " " + str(e)[:120])
        return False


def main():
    dry = "--dry" in sys.argv
    token, topic = get_token()
    if not token and not dry:
        print("[!] 没有找到 PushPlus token，推送未发送。")
        print("    配置方法（二选一）：")
        print("      1. 环境变量： export PUSHPLUS_TOKEN=你的token")
        print("      2. 写配置文件：" + CONF)
        print("         内容： {\"token\": \"你的token\"}")
        print("    获取 token：https://www.pushplus.plus/ 微信扫码登录 → 一对一消息 → token")
        print("    想先看推送内容： python3 push_daily.py --dry")
        return 1

    if "--test" in sys.argv:
        return 0 if send(token, topic,
                         "市场日历 · 推送测试",
                         "如果你看到这条消息，说明 token 配置正确。\n\n"
                         "之后每天会自动推送当天的财经日历与要点。") else 1

    md, today = build_markdown()
    if dry:
        print(md)
        print()
    title = (str(today.month) + "月" + str(today.day) + "日 市场日历")
    ok = send(token, topic, title, md, dry=dry)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
