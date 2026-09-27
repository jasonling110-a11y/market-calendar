# -*- coding: utf-8 -*-
"""
生成 iOS 可订阅的日历文件（.ics）

为什么做这个：个人使用场景下，订阅日历比小程序方便得多——
「20:30 美国CPI」直接出现在 iPhone 自带日历里，锁屏可见、可设提醒，
不用打开任何 App，不用注册、不用审核。

订阅源内容：
  1. 财经日历（经济数据 / 央行议息会议 / 央行动态）—— 按发布时刻生成定时日程
  2. UP 主视频观点 —— 按发布日生成全天日程，要点写在日程描述里
  3. 已公布的实际值 —— 写进对应日程的描述

关键实现点：
  - 时间统一转成 UTC 并用 Z 结尾，避开 VTIMEZONE 的兼容麻烦
  - UID 必须稳定（用日期+时间+名称的哈希），否则每次刷新会重复堆积日程
  - ICS 规定单行不超过 75 字节，中文一个字 3 字节，必须折行
  - 文本里的 , ; \\ 和换行必须转义

用法：
    python3 build_ics.py
输出：
    dist/market-calendar.ics      订阅源本体
    dist/index.html               手机友好的订阅入口页
"""
import datetime as dt
import hashlib
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "miniprogram", "data")
# 输出到 docs/：这是 GitHub Pages「从分支发布」的默认目录之一，
# 同时也能被 CloudStudio 等任意静态托管直接使用。
DIST = os.path.join(ROOT, "docs")
PREVIEW = os.path.join(ROOT, "preview", "index.html")

# 订阅窗口：过去 14 天（回看）+ 未来 120 天（提前排期）
PAST_DAYS = 14
FUTURE_DAYS = 120
# 只收录 ★★ 以上的日历项，否则一个月 200 多条会把手机日历塞满
MIN_IMP = 2
# ★★★（CPI / 非农 / 议息会议）提前 15 分钟提醒
ALARM_IMP = 3

TZ = dt.timezone(dt.timedelta(hours=8))     # 北京时间
CAL_NAME = "市场日历"


def load_js(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    return json.loads(src.split("module.exports = ", 1)[1].rstrip().rstrip(";"))


def esc(t):
    """ICS TEXT 值转义：反斜杠、分号、逗号、换行都有特殊含义"""
    return (str(t).replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n"))


def fold(line):
    """按 75 字节折行（中文 1 字 3 字节），续行以单个空格开头"""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    out, cur = [], b""
    for ch in line:
        cb = ch.encode("utf-8")
        if len(cur) + len(cb) > 74:
            out.append(cur.decode("utf-8"))
            cur = b" "
        cur += cb
    out.append(cur.decode("utf-8"))
    return "\r\n".join(out)


def utc(d: dt.date, hhmm: str):
    """北京时间的某日某时 -> UTC，返回 (DTSTART, DTEND) 字符串"""
    m = re.match(r"^(\d{1,2}):(\d{2})$", hhmm or "")
    hh, mm = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    start = dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=TZ)
    return start.astimezone(dt.timezone.utc)


def fmt_utc(x):
    return x.strftime("%Y%m%dT%H%M%SZ")


def fmt_date(d):
    return d.strftime("%Y%m%d")


def uid(*parts):
    h = hashlib.md5("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:24]
    return h + "@market-calendar"


def main():
    HIST = load_js(os.path.join(DATA, "history.js"))
    META = load_js(os.path.join(DATA, "meta.js"))
    cal_c, cal_n = META.get("calCountries", []), META.get("calNames", [])
    IND = META.get("indicators", {})

    today = dt.date.today()
    lo, hi = today - dt.timedelta(days=PAST_DAYS), today + dt.timedelta(days=FUTURE_DAYS)

    # 紧凑数组 -> 可读记录
    def read_cal(ymd):
        day = HIST.get(ymd) or {}
        vals = {}
        for p in (day.get("v") or []):
            vals[p[0]] = p
        out = []
        for e in (day.get("c") or []):
            tm, ci, ni, imp, kind, pd, mk = (list(e) + [""] * 7)[:7]
            if imp < MIN_IMP:
                continue
            v = vals.get(mk) if mk else None
            out.append({
                "tm": tm, "co": cal_c[ci] if ci is not None and ci < len(cal_c) else "",
                "n": cal_n[ni] if ni is not None and ni < len(cal_n) else "",
                "i": imp, "k": kind, "pd": pd,
                "a": v[1] if v else None, "f": v[2] if v else None,
                "p": v[3] if v else None,
                "u": (IND.get(mk) or {}).get("u", "") if mk else "",
            })
        return out, (day.get("u") or [])

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//market-calendar//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:" + esc(CAL_NAME),
        "X-WR-TIMEZONE:Asia/Shanghai",
        "X-WR-CALDESC:" + esc("财经日历 + UP 主观点的自动订阅源，每日更新"),
    ]
    stamp = fmt_utc(dt.datetime.now(dt.timezone.utc))
    n_evt = 0

    d = lo
    while d <= hi:
        ymd = d.isoformat()
        items, ups = read_cal(ymd)

        # ---- 1) 财经日历 ----
        for it in items:
            name = it["n"]
            head = ("[" + it["co"] + "] " if it["co"] else "") + name
            if it["i"] >= 3:
                head = "★ " + head
            # 已公布的把实际值放进标题，锁屏一眼能看到
            if it["a"] is not None:
                head += "  实际 " + _num(it["a"]) + it["u"]

            desc = []
            if it["pd"]:
                desc.append("报告期：" + _pd_text(it["pd"]))
            if it["a"] is not None:
                desc.append("实际值：" + _num(it["a"]) + it["u"])
            if it["f"] is not None:
                desc.append("市场预期：" + _num(it["f"]) + it["u"])
            if it["p"] is not None:
                desc.append("前值：" + _num(it["p"]) + it["u"])
            if it["k"] == 1:
                desc.append("类型：会议 / 事件")
            elif it["k"] == 2:
                desc.append("类型：央行动态")
            desc.append("来源：东方财富财经日历")

            if it["tm"] and it["tm"] != "00:00":
                st = utc(d, it["tm"])
                minutes = 45 if it["k"] == 1 else 15
                en = st + dt.timedelta(minutes=minutes)
                lines += ["BEGIN:VEVENT",
                          "UID:" + uid(ymd, it["tm"], name, it["co"]),
                          "DTSTAMP:" + stamp,
                          "DTSTART:" + fmt_utc(st),
                          "DTEND:" + fmt_utc(en),
                          "SUMMARY:" + esc(head),
                          "DESCRIPTION:" + esc("\n".join(desc))]
                if it["i"] >= ALARM_IMP:
                    lines += ["BEGIN:VALARM", "TRIGGER:-PT15M",
                              "ACTION:DISPLAY",
                              "DESCRIPTION:" + esc("15 分钟后：" + head),
                              "END:VALARM"]
                lines += ["TRANSP:TRANSPARENT", "END:VEVENT"]
            else:
                # 无具体时间的（展会、全天会议）做成全天日程
                lines += ["BEGIN:VEVENT",
                          "UID:" + uid(ymd, "allday", name, it["co"]),
                          "DTSTAMP:" + stamp,
                          "DTSTART;VALUE=DATE:" + fmt_date(d),
                          "DTEND;VALUE=DATE:" + fmt_date(d + dt.timedelta(days=1)),
                          "SUMMARY:" + esc(head),
                          "DESCRIPTION:" + esc("\n".join(desc)),
                          "TRANSP:TRANSPARENT", "END:VEVENT"]
            n_evt += 1

        # ---- 2) UP 主视频观点（全天日程，要点放描述）----
        for u in ups:
            pts = u.get("p") or []
            if not pts:
                continue
            desc = list(pts) + ["", "原视频：https://www.bilibili.com/video/" + u.get("k", "")]
            lines += ["BEGIN:VEVENT",
                      "UID:" + uid(ymd, "up", u.get("k", "")),
                      "DTSTAMP:" + stamp,
                      "DTSTART;VALUE=DATE:" + fmt_date(d),
                      "DTEND;VALUE=DATE:" + fmt_date(d + dt.timedelta(days=1)),
                      "SUMMARY:" + esc("UP观点 " + (u.get("t") or "")[:40]),
                      "DESCRIPTION:" + esc("\n".join(desc)),
                      "TRANSP:TRANSPARENT", "END:VEVENT"]
            n_evt += 1

        d += dt.timedelta(days=1)

    lines.append("END:VCALENDAR")

    os.makedirs(DIST, exist_ok=True)
    ics = "\r\n".join(fold(x) for x in lines) + "\r\n"
    with open(os.path.join(DIST, "market-calendar.ics"), "w", encoding="utf-8",
              newline="") as f:
        f.write(ics)

    write_index()
    n_app = copy_app()

    if n_app:
        print(f"    → {os.path.join(DIST, 'app.html')}（完整网页版，手机可直接用）")

    print(f"[✓] 日历订阅源：{n_evt} 个日程")
    print(f"    窗口 {lo} ~ {hi}（过去 {PAST_DAYS} 天 + 未来 {FUTURE_DAYS} 天）")
    print(f"    只收录 ★★ 以上；★★★ 提前 15 分钟提醒")
    print(f"    → {os.path.join(DIST, 'market-calendar.ics')}  "
          f"({len(ics.encode('utf-8'))/1024:.0f}KB)")
    print(f"    → {os.path.join(DIST, 'index.html')}")


def _num(v):
    n = float(v)
    if n == int(n):
        return str(int(n))
    return ("%.2f" % n).rstrip("0").rstrip(".")


def _pd_text(pd):
    if not pd or len(pd) != 4:
        return pd or ""
    return "20" + pd[:2] + "年" + str(int(pd[2:])) + "月"


def copy_app():
    """把完整网页版拷进 docs/app.html。

    这样手机上打开 https://<user>.github.io/<repo>/app.html 就是完整的
    日历界面（财经日历 / 数值 / UP观点 / 笔记），可以「添加到主屏幕」当 App 用，
    不依赖任何本地环境。
    """
    if not os.path.exists(PREVIEW):
        return False
    with open(PREVIEW, "rb") as f:
        blob = f.read()
    with open(os.path.join(DIST, "app.html"), "wb") as f:
        f.write(blob)
    return True


def write_index():
    """手机友好的订阅入口页：点按钮直接唤起『添加订阅日历』"""
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>市场日历 · 订阅</title>
<style>
:root{color-scheme:dark}
body{margin:0;padding:32px 22px;background:#000;color:#fff;
 font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;line-height:1.6}
h1{font-size:22px;margin:0 0 6px}
.sub{color:#98989f;font-size:13px;margin-bottom:26px}
.btn{display:block;text-align:center;padding:15px;border-radius:12px;
 background:#0a84ff;color:#fff;font-size:16px;font-weight:600;
 text-decoration:none;margin-bottom:12px}
.btn.alt{background:#1c1c1e;color:#0a84ff;font-weight:500}
ol{padding-left:20px;color:#c7c7cc;font-size:14px}
li{margin-bottom:8px}
.card{background:#1c1c1e;border-radius:12px;padding:16px;margin-top:22px;font-size:13px;color:#98989f}
code{background:#2c2c2e;padding:2px 6px;border-radius:4px;font-size:12px;word-break:break-all}
</style>
</head>
<body>
  <h1>市场日历</h1>
  <div class="sub">财经日历 · 央行议息 · UP 主观点　每日自动更新</div>

  <a class="btn" id="sub" href="#">订阅到 iPhone 日历</a>
  <a class="btn alt" id="raw" href="#">下载 .ics 文件（手动导入）</a>
  <a class="btn alt" href="app.html">打开完整日历（网页版）</a>

  <div class="card">
    <b style="color:#c7c7cc">订阅后怎么刷新？</b>
    <ol>
      <li>iPhone：设置 → 日历 → 账户 → 获取新数据 → 拉到底，把「已订阅的日历」设为「每小时」</li>
      <li>如果没自动更新：日历 App → 底部「日历」→ 下拉刷新</li>
      <li>不想订阅了：设置 → 日历 → 账户 → 删除该订阅</li>
    </ol>
  </div>

  <div class="card">
    订阅地址<br><code id="url"></code>
  </div>

  <div class="card">
    <b style="color:#c7c7cc">如果「订阅」按钮没反应</b>
    <ol>
      <li>请在 <b>Safari</b> 里打开本页（微信内置浏览器不支持 webcal://）</li>
      <li>或用上面的「下载 .ics 文件」，下载后点开 → 添加到日历</li>
      <li>手动订阅：设置 → 日历 → 账户 → 添加账户 → 其他 → 添加已订阅的日历</li>
    </ol>
  </div>

<script>
// 用 URL 解析构造绝对地址：直接字符串拼接在「部署在根路径」时会算错
var u = new URL('market-calendar.ics', location.href).href;
document.getElementById('url').textContent = u;
document.getElementById('raw').href = u;
// webcal:// 直接唤起 iPhone 日历的「添加订阅」弹窗；
// 这条路径下由 iOS 自己取文件，不受服务器 MIME 类型影响
document.getElementById('sub').href = u.replace(/^https?:/, 'webcal:');
</script>
</body>
</html>
"""
    with open(os.path.join(DIST, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()
