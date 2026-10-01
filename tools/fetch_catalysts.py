# -*- coding: utf-8 -*-
"""
当天领涨板块的「消息面催化」抓取器

为什么需要它：
    日历里能看到「今天哪些板块领涨」，但看不到「为什么涨」。
    这一层把当天的新闻和当天的领涨板块对起来，回答「是什么消息把它推上去的」。

--------------------------------------------------------------------
⚠️ 关于匹配口径（第一版翻车记录，改动前务必先读）

第一版只用「新浪财经滚动新闻」（pageid=153&lid=2516，约 250~450 条/天），
并要求板块名出现在标题里。实测量了 5 个交易日 × 6 个领涨板块 = 30 个组合，
**只命中 2 个（≈7%）**。2026-09-30 白酒板块领涨 +2.82%，当天 431 条新闻里
「白酒」在标题中出现 0 次；「油气开采及服务」「种植业与林业」「电子化学品」
这类申万/同花顺行业名，本来就不是新闻用语。

结论：**不是匹配规则的问题，是语料太薄、且不是市场向的。**
换成下面两个源之后，同一批日子命中 4/6 个板块（09-29、09-30 均为 4/6）。

两个源：
  A. 新浪 7×24 财经快讯（覆盖最近几天）
     https://zhibo.sina.com.cn/api/zhibo/feed?page={p}&page_size=100
             &zhibo_id=152&tag_id=0&dire=f&dpc=1
     每交易日 ~2200 条，是滚动新闻的 5 倍，且是市场向的。
     ⚠️ 实测**只能回溯约 8 天**（约 1 万条），再往前翻只会返回老内容 ——
     所以 STALL_LIMIT（连续 20 页无新条目就停）是必须的：
     第一版没有它，硬翻满 900 页、白等 28 分钟才发现一直在取重复内容。
  B. 同花顺股市快讯（回溯长 + 高置信度）
     https://news.10jqka.com.cn/tapp/news/push/stock/?page={p}&track=website&pagesize=50
     每交易日 ~350 条，实测能回溯 30 天以上。关键：**同花顺自己给每条快讯标了所属板块**
       "field": [{"name":"黄金概念","stockCode":"886064","stockMarket":"48"}]
     这个 name 和我们的板块名是同一套词表，直接按名对即可 —— 不用字符串猜。
     另有 "stock" 字段列出关联个股。带 field 的约 7%，量少但几乎不会错。

匹配规则（两条路，宁缺勿滥）：
    tag 路：快讯 field 里的板块名 == 当天领涨板块名 → 直接命中，界面标「官方标注」。
            这条由同花顺自己保证相关性，不再加任何额外条件。
    match 路：板块名出现在标题里（标题取 rich_text 的【...】，没有则取前 60 字），
            并要过两道闸：① 过滤涨停雷达/公告/龙虎榜这类日常栏目；
            ② 标题里必须出现市场动作词（见 ACTION_WORDS）。
            加②是因为「元件」这种泛词会把「日本电产把旗下子公司电产元件出售给凯雷」
            也算成元件板块的催化 —— 板块名确实在标题里，但跟 A 股板块毫无关系。
    两者合并去重，每个板块最多留 2 条；tag 优先被保留。

输出：data/catalysts_daily.json
  -> { "YYYY-MM-DD": { "板块名": [{"t":标题,"u":链接,"m":来源,"hm":HH:MM,"src":"match|tag"}] } }

用法：
    python3 fetch_catalysts.py                # 增量：只补最近 3 天
    python3 fetch_catalysts.py --days 30      # 回填最近 30 天
"""
import datetime as dt
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(DATA, "catalysts_daily.json")
SECTORS = os.path.join(DATA, "sector_daily.json")

CN = dt.timezone(dt.timedelta(hours=8))     # 全项目统一北京时间

SINA_FEED = ("https://zhibo.sina.com.cn/api/zhibo/feed"
             "?page={page}&page_size=100&zhibo_id=152&tag_id=0&dire=f&dpc=1")
SINA_REF = "https://finance.sina.com.cn/7x24/"
THS_FEED = ("https://news.10jqka.com.cn/tapp/news/push/stock/"
            "?page={page}&tag=&track=website&pagesize=50")
THS_REF = "https://news.10jqka.com.cn/"

MAX_PAGES = 400          # 硬上限，防止翻页停不下来
STALL_LIMIT = 20         # 连续这么多页没有新条目就停：说明这个源已经翻到底了
                         # （一次 100 条 × 20 页 = 2000 条全新内容都不可能没新条目，
                         #  所以不会因为「当天新闻少」误停；放假期间条目仍在增加）
PAGE_GAP = 0.3           # 页间间隔，别把人家打疼
KEEP_DAYS = 120          # 文件只留最近 120 天
MAX_ITEMS_PER_SECTOR = 2
MAX_SECTORS_PER_DAY = 6
TITLE_MAX = 60           # 快讯没有【】时，取正文前多少字当标题
MIN_NEWS_TO_DROP = 100   # 少于这么多条新闻就不敢判定「今天没催化」，免得误删旧结论

# 与领涨板块无关的日常栏目：涨停雷达、个股公告之类，标题里带板块名也不代表催化
TITLE_NOISE = ["涨停雷达", "龙虎榜", "公告", "股东减持", "大宗交易",
               "停复牌", "异动", "盘中必读", "早报", "晚报", "复盘"]

# 「字面命中」这条路的第二道闸：标题里必须出现市场动作词。
# 起因：「元件」这种泛词会把「日本电产把旗下子公司电产元件出售给凯雷」也算成
# 元件板块的催化 —— 板块名确实在标题里，但那条消息跟 A 股板块毫无关系。
# tag 命中不需要这道闸：同花顺只给它真的关联过的快讯打标。
ACTION_WORDS = ["拉升", "涨停", "跌停", "走强", "走弱", "高开", "低开", "冲高", "回落",
                "领涨", "领跌", "大涨", "大跌", "爆发", "走高", "走低", "回调", "上扬",
                "下挫", "翻红", "翻绿", "封板", "攀升", "涨", "跌"]

_OPENER_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_OPENER_PROXY = urllib.request.build_opener()


def _get(url, ref, retries=3, timeout=20):
    """直连优先、失败退代理（本机全局挂的 HTTPS_PROXY 会零星断连，见 fetch_breadth.py）。"""
    headers = {"User-Agent": UA, "Referer": ref}
    last = None
    for i in range(retries):
        for opener in (_OPENER_DIRECT, _OPENER_PROXY):
            try:
                req = urllib.request.Request(url, headers=headers)
                with opener.open(req, timeout=timeout) as r:
                    return r.read().decode("utf-8", "ignore")
            except urllib.error.HTTPError as e:
                last = e
                if e.code in (403, 404):      # 明确的拒绝/不存在，换 opener 也没用
                    break
            except Exception as e:  # noqa
                last = e
        time.sleep(0.8 * (2 ** i))
    raise last


def _brief(rich_text):
    """快讯正文里【...】就是标题；没有的话截前 N 字。"""
    s = re.sub(r"<[^>]+>", "", rich_text or "").strip()
    m = re.match(r"^【([^】]{2,60})】", s)
    return m.group(1).strip() if m else s[:TITLE_MAX]


def fetch_sina(until_date, max_pages=MAX_PAGES):
    """新浪 7×24：从最新往回翻，返回 {日期: [条目]}。

    ⚠️ 实测这个源**只能回溯约 8 天**（约 1 万条），再往前翻只会返回老内容。
    第一版没有「翻到底」判断，硬翻满 900 页、白等 28 分钟才出来 ——
    所以这里加了 STALL_LIMIT：连续 40 页没有新条目就当到底，直接停。
    30 天的回填真正靠同花顺快讯那段补齐。
    """
    by_day, seen = {}, set()
    pages = stall = 0
    for page in range(1, max_pages + 1):
        try:
            d = json.loads(_get(SINA_FEED.format(page=page), SINA_REF))
        except Exception as e:
            print(f"      新浪第 {page} 页失败：{e}")
            break
        lst = ((d.get("result") or {}).get("data") or {}).get("feed", {}).get("list") or []
        if not lst:
            break
        pages = page
        oldest, fresh = None, 0
        for it in lst:
            k = it.get("id")
            if k in seen:
                continue
            seen.add(k)
            ct = (it.get("create_time") or "")[:19]
            if len(ct) < 10:
                continue                      # 取不到时间的条目一律不要，免得污染日期归属
            fresh += 1
            day = ct[:10]
            oldest = day if oldest is None or day < oldest else oldest
            by_day.setdefault(day, []).append({
                "t": _brief(it.get("rich_text")),
                "u": (it.get("docurl") or "").strip(),
                "m": "新浪7×24",
                "hm": ct[11:16],
                "e": [],          # 该源没有官方板块标注
            })
        stall = 0 if fresh else stall + 1
        if page % 40 == 0 or stall >= STALL_LIMIT:
            print(f"        新浪已翻 {page} 页 · {len(seen)} 条 · 最早 {oldest} · 连续无新 {stall}")
        if stall >= STALL_LIMIT:
            print(f"        新浪连续 {stall} 页无新条目 → 该源已翻到底，停止")
            break
        if oldest and oldest < until_date:
            break
        time.sleep(PAGE_GAP)
    print(f"      新浪7×24：{pages} 页 / {len(seen)} 条 / 覆盖 {len(by_day)} 天"
          f"（{min(by_day) if by_day else '-'} ~ {max(by_day) if by_day else '-'}）")
    return by_day


def fetch_ths(until_date, max_pages=MAX_PAGES):
    """同花顺快讯：多一层官方 field 板块标注，命中更准、回溯也更长（实测 30 天没问题）。"""
    by_day, seen = {}, set()
    pages = stall = 0
    for page in range(1, max_pages + 1):
        try:
            d = json.loads(_get(THS_FEED.format(page=page), THS_REF))
        except Exception as e:
            print(f"      同花顺第 {page} 页失败：{e}")
            break
        lst = (d.get("data") or {}).get("list") or []
        if not lst:
            break
        pages = page
        oldest, fresh = None, 0
        for it in lst:
            k = it.get("id")
            if k in seen:
                continue
            seen.add(k)
            try:
                ts = int(it.get("ctime"))
            except (TypeError, ValueError):
                continue
            fresh += 1
            t = dt.datetime.fromtimestamp(ts, CN)
            day = t.strftime("%Y-%m-%d")
            oldest = day if oldest is None or day < oldest else oldest
            fields = []
            for f in (it.get("field") or []):
                if isinstance(f, dict) and f.get("name"):
                    fields.append(str(f["name"]).strip())
            by_day.setdefault(day, []).append({
                "t": (it.get("title") or "").strip() or _brief(it.get("digest")),
                "u": (it.get("url") or "").strip(),
                "m": "同花顺快讯",
                "hm": t.strftime("%H:%M"),
                "e": fields,      # 同花顺官方板块标注
            })
        stall = 0 if fresh else stall + 1
        if page % 40 == 0 or stall >= STALL_LIMIT:
            print(f"        同花顺已翻 {page} 页 · {len(seen)} 条 · 最早 {oldest} · 连续无新 {stall}")
        if stall >= STALL_LIMIT:
            print(f"        同花顺连续 {stall} 页无新条目 → 该源已翻到底，停止")
            break
        if oldest and oldest < until_date:
            break
        time.sleep(PAGE_GAP)
    print(f"      同花顺快讯：{pages} 页 / {len(seen)} 条 / 覆盖 {len(by_day)} 天"
          f"（{min(by_day) if by_day else '-'} ~ {max(by_day) if by_day else '-'}）")
    return by_day


def merge(*sources):
    """把多个源按天合并。同一条（同标题）只留一次，保留带官方标注的那份。"""
    out = {}
    for src in sources:
        for day, items in src.items():
            bucket = out.setdefault(day, {})
            for it in items:
                k = it["t"]
                if not k:
                    continue
                cur = bucket.get(k)
                if cur is None or (not cur["e"] and it["e"]):
                    bucket[k] = it
    return {d: list(v.values()) for d, v in out.items()}


def match_day(sectors, news):
    """把某天的领涨板块和当天快讯对上。

    tag 命中（同花顺官方标注）优先级最高；match 命中要求板块名出现在标题里。
    """
    out = {}
    for sec in sectors[:MAX_SECTORS_PER_DAY]:
        name = (sec.get("name") or "").strip()
        if not name:
            continue
        tagged, matched = [], []
        for it in news:
            if name in (it["e"] or []):
                tagged.append(it)
                continue
            title = it["t"]
            if not title or name not in title:
                continue
            if any(w in title for w in TITLE_NOISE):
                continue
            # 第二道闸：字面命中还要求标题里有市场动作词（见 ACTION_WORDS 的说明）。
            # tag 命中不需要这道 —— 同花顺只给它真的关联过的快讯打标。
            if not any(w in title for w in ACTION_WORDS):
                continue
            matched.append(it)
        hits = tagged + matched
        if hits:
            # 同一天同一板块可能有多条，取最早的两条（消息通常先于涨幅）
            # 上面 tagged 排前面，所以官方标注的那条更容易被保留下来
            out[name] = [{"t": h["t"], "u": h["u"], "m": h["m"], "hm": h["hm"],
                          "src": "tag" if h in tagged else "match"} for h in hits[:MAX_ITEMS_PER_SECTOR]]
    return out


def main():
    days_back = 3
    if "--days" in sys.argv:
        days_back = int(sys.argv[sys.argv.index("--days") + 1])

    old = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            old = json.load(f)
        print(f"[0/4] 已有催化数据 {len(old)} 天")

    if not os.path.exists(SECTORS):
        print("[✗] 缺少 sector_daily.json，先跑 fetch_sectors.py")
        return
    with open(SECTORS, encoding="utf-8") as f:
        sec = json.load(f)

    today = dt.datetime.now(CN).date()
    until = (today - dt.timedelta(days=days_back)).strftime("%Y-%m-%d")

    print(f"[1/4] 抓新浪 7×24 快讯（回溯到 {until}）...")
    sina = fetch_sina(until)
    print(f"[2/4] 抓同花顺快讯（回溯到 {until}）...")
    ths = fetch_ths(until)
    if not sina and not ths:
        print("[✗] 两个源都没拿到数据，保留原有文件")
        return
    by_day = merge(sina, ths)

    print("[3/4] 按领涨板块匹配 ...")
    out = dict(old)
    hit_days = tagged_n = dropped = 0
    for day, news in sorted(by_day.items()):
        if day < until:
            continue
        s = sec.get(day)
        if not s or not s.get("up"):
            continue
        m = match_day(s["up"], news)
        if m:
            out[day] = m
            hit_days += 1
            tagged_n += sum(1 for arr in m.values() for x in arr if x["src"] == "tag")
        elif len(news) >= MIN_NEWS_TO_DROP and day in out:
            # 这天本次确实抓到了足够多的新闻、却一个板块都没匹配上 → 把旧结论撤掉。
            # 不撤的话，上一版宽松规则匹配出来的条目会永远挂在日历上，
            # 改了规则也不会消失（比如「元件」被「日本电产出售子公司」蒙对的那条）。
            # 加 MIN_NEWS_TO_DROP 是为了防「抓取残缺 → 误删好数据」。
            out.pop(day, None)
            dropped += 1

    # 只保留最近 N 天，别让文件无限长大
    floor = (today - dt.timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    out = {d: v for d, v in out.items() if d >= floor}

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    total = sum(len(arr) for v in out.values() for arr in v.values())
    print(f"[4/4] 写出 {OUT}")
    print(f"      覆盖 {len(out)} 天 / {total} 条板块催化（其中 {tagged_n} 条来自同花顺官方标注）/ "
          f"本次新增命中 {hit_days} 天 / 撤回 {dropped} 天 / 体积 {os.path.getsize(OUT)/1024:.0f}KB")
    for d in sorted(out)[-3:]:
        print(f"      {d}:")
        for name, arr in out[d].items():
            print(f"        {name} ← [{arr[0]['hm']}][{arr[0]['src']}] {arr[0]['t'][:40]}")


if __name__ == "__main__":
    main()
