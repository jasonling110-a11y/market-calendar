# -*- coding: utf-8 -*-
"""
A 股板块历史涨跌抓取器

数据源（按优先级）：
  1. 同花顺 d.10jqka.com.cn —— 【当前主源】每页给一个板块的完整日线历史，
     90 个二级行业(881xxx) + 293 个概念(885xxx/886xxx)，含开高低收，
     可自行算涨跌幅。域名稳定可达，是 2026-10 起的主力数据源。
  2. 东方财富 push2 / push2his —— 理想源（一次拉 420 天），但实测该域名族
     在本机与 GitHub Actions 均完全不可达（连接 0.1 秒即被重置），仅作保留。
  3. 腾讯 proxy.finance.qq.com —— 当天板块快照（行业 + 概念，含涨跌幅）
  4. 新浪 vip.stock.finance.sina.com.cn —— 当天行业板块快照（GBK）

模式：同花顺可用时全量重建；否则东财全量；再否则降级为「只补最新交易日」。
⚠️ 绝不因为抓取失败就把已有历史覆盖成空 —— 那会让整段历史行情排行消失。

输出：data/sector_daily.json
  -> { "YYYY-MM-DD": { "up": [...], "down": [...], "breadth": {...} } }
"""
import datetime as dt
import json
import os
import re
import ssl
import threading
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT_DIR, exist_ok=True)

DAYS = 420          # 期望覆盖的交易日数
_MIN_ITEMS = 100    # 单日板块样本少于该数视为不完整，丢弃


_last_call = [0.0]
_lock = threading.Lock()
_MIN_GAP = 0.05     # 全局最小请求间隔


def _throttle():
    with _lock:
        gap = time.time() - _last_call[0]
        if gap < _MIN_GAP:
            time.sleep(_MIN_GAP - gap)
        _last_call[0] = time.time()


def _get(url, retries=4, timeout=25, referer=None, encoding="utf-8"):
    """带节流 + 指数退避的 GET，返回文本。"""
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    last = None
    for i in range(retries):
        _throttle()
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.read().decode(encoding, "ignore")
        except Exception as e:  # noqa
            last = e
            time.sleep(min(6, 0.7 * (2 ** i)) + 0.2 * i)
    raise last


# ---- 噪音板块黑名单 --------------------------------------------------
# 打板/情绪类、指数成分类、资金标签类、财务标签类：不是真正的行业或产业主题，
# 出现在"领涨板块"里会误导，统一剔除。
NOISE_KEYWORDS = [
    "昨日", "涨停", "跌停", "连板", "首板", "打板", "触板", "炸板", "竞价",
    "融资融券", "GDR", "QFII", "社保重仓", "基金重仓", "机构重仓", "券商重仓",
    "MSCI", "标普", "富时", "沪股通", "深股通", "北向", "养老金", "险资",
    "预盈预增", "预亏预减", "业绩", "扭亏", "破净", "ST", "*ST", "次新",
    "转债", "送转", "高送转", "举牌", "增持", "回购", "减持", "解禁",
    "员工持股", "股权激励", "参股", "分拆", "重组", "壳资源",
    "低价股", "高价股", "大盘", "中盘", "小盘", "微盘", "上证", "深证",
    "中证", "沪深", "茅指数", "宁组合", "北交所", "科创板", "创业板综",
    "标准普尔", "富时罗素", "AH股", "B股", "H股", "独角兽",
    "同花顺", "指数",
]


def _is_noise(name):
    return any(kw in name for kw in NOISE_KEYWORDS)


def pick(seq, n=6):
    """优先行业板块，其次概念板块；同板块只出现一次"""
    seen, res = set(), []
    for tag in ("行业", "概念"):
        for name, tg, pct in seq:
            if tg != tag or name in seen:
                continue
            seen.add(name)
            res.append({"name": name, "pct": pct, "tag": tag})
            if len(res) >= n:
                return res
    return res


def build_day(items, min_items=_MIN_ITEMS):
    """(名称, 标签, 涨跌幅) 列表 -> 单日 {up, down, breadth}；样本太少返回 None"""
    if len(items) < min_items:
        return None
    items = sorted(items, key=lambda x: -x[2])
    up = pick(items)
    # 领跌保持「最跌在前」：前端按数组顺序渲染，反过来存会让第一名变成跌得最少的
    down = pick(list(reversed(items)))
    rising = sum(1 for _, _, p in items if p > 0)
    return {
        "up": up,
        "down": down,
        "breadth": {"total": len(items), "rising": rising,
                    "falling": len(items) - rising},
    }


# =====================================================================
# 数据源 1：同花顺
# =====================================================================
THS_HY = "https://q.10jqka.com.cn/thshy/"
THS_GN = "https://q.10jqka.com.cn/gn/"
THS_LINE = "https://d.10jqka.com.cn/v6/line/bk_{code}/01/{period}.js"
THS_REF = "https://q.10jqka.com.cn/"

THS_BOARD_CACHE = os.path.join(OUT_DIR, "ths_boards.json")


def ths_board_list():
    """同花顺板块清单：行业(881xxx) + 概念(885xxx/886xxx)。
    行业取自 thshy 页面的详情链接；概念取自 gn 页面的 gnSection JSON。
    成功即落盘缓存。"""
    boards = {}
    got = False

    # --- 行业 ---
    try:
        html = _get(THS_HY, referer=THS_REF, encoding="gbk")
        for code, name in re.findall(
                r'thshy/detail/code/(\d{6})/"[^>]*>([^<]+)</a>', html):
            name = name.strip()
            if not name or _is_noise(name):
                continue
            boards[code] = {"code": code, "name": name, "tag": "行业"}
        got = bool(boards)
        print(f"      同花顺行业板块 {len(boards)} 个")
    except Exception as e:
        print(f"      [warn] 同花顺行业列表失败：{e}")

    # --- 概念 ---
    try:
        html = _get(THS_GN, referer=THS_REF, encoding="gbk")
        m = re.search(r'id="gnSection"\s+value=\'(.*?)\'\s*/?>', html, re.S)
        raw = m.group(1) if m else ""
        if not raw:
            m = re.search(r'gnSection"\s*value=\'(\{.*?\})\'', html, re.S)
            raw = m.group(1) if m else ""
        n_concept = 0
        if raw:
            for item in json.loads(raw).values():
                code = str(item.get("platecode") or "").strip()
                name = str(item.get("platename") or "").strip()
                if not code or not name or _is_noise(name):
                    continue
                boards[code] = {"code": code, "name": name, "tag": "概念"}
                n_concept += 1
        print(f"      同花顺概念板块 {n_concept} 个")
        got = got or n_concept > 0
    except Exception as e:
        print(f"      [warn] 同花顺概念列表失败：{e}")

    vals = list(boards.values())
    if vals and got:
        with open(THS_BOARD_CACHE, "w", encoding="utf-8") as f:
            json.dump(vals, f, ensure_ascii=False, separators=(",", ":"))
        print(f"      板块清单已缓存 → {THS_BOARD_CACHE}（共 {len(vals)} 个）")
    elif os.path.exists(THS_BOARD_CACHE):
        with open(THS_BOARD_CACHE, encoding="utf-8") as f:
            vals = json.load(f)
        print(f"      在线拉取失败，改用缓存清单 {len(vals)} 个")
    return vals


def ths_kline(board, period):
    """同花顺单板块日线。period: 'last'(近140根) 或 '2026' 之类的年份。

    返回 [(日期, 涨跌幅%), ...]，涨跌幅由相邻收盘价自算。
    行格式：日期,开,高,低,收,成交量,成交额,,,,
    """
    url = THS_LINE.format(code=board["code"], period=period)
    try:
        txt = _get(url, retries=3, referer=THS_REF)
    except Exception:
        return board, []
    i, j = txt.find("("), txt.rfind(")")
    if i < 0 or j <= i:
        return board, []
    try:
        obj = json.loads(txt[i + 1:j])
    except Exception:
        return board, []
    rows = []
    prev_close = None
    for line in (obj.get("data") or "").split(";"):
        p = line.split(",")
        if len(p) < 5 or not re.fullmatch(r"\d{8}", p[0]):
            continue
        try:
            close = float(p[4])
        except ValueError:
            continue
        d = f"{p[0][:4]}-{p[0][4:6]}-{p[0][6:]}"
        if prev_close:
            rows.append((d, round((close - prev_close) / prev_close * 100, 2)))
        prev_close = close
    return board, rows


def ths_full(periods=("2025", "2026")):
    """同花顺全量重建。返回 {date: build_day(...)}"""
    boards = ths_board_list()
    if not boards:
        return {}

    # 同一板块可能多年份文件都返回，按 (代码, 日期) 去重
    per_date = {}
    ok, fails = 0, 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(ths_kline, b, p) for b in boards for p in periods]
        for f in as_completed(futs):
            board, rows = f.result()
            if rows:
                ok += 1
            else:
                fails += 1
            for date, pct in rows:
                per_date.setdefault(date, {})[(board["code"], board["name"])] = \
                    (board["name"], board["tag"], pct)
    print(f"      同花顺：成功 {ok} 个板块-年份，失败 {fails}，"
          f"覆盖 {len(per_date)} 个交易日")

    out = {}
    for date, dmap in per_date.items():
        items = list(dmap.values())
        day = build_day(items)
        if day:
            out[date] = day
    return out


# =====================================================================
# 数据源 2：东方财富（保留；当前网络下不可达）
# =====================================================================
BOARD_CACHE = os.path.join(OUT_DIR, "boards.json")


def fetch_board_list():
    """行业板块(t:2) + 概念板块(t:3)，分页拉取 + 去噪 + 去重。"""
    em_headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}
    boards = {}
    got_any = False
    for fs, tag in (("m:90+t:2+f:!50", "行业"), ("m:90+t:3+f:!50", "概念")):
        for page in range(1, 7):
            url = (f"https://push2.eastmoney.com/api/qt/clist/get?pn={page}&pz=100"
                   "&po=1&np=1&fltt=2&invt=2&fid=f3&fs=" +
                   urllib.parse.quote(fs) + "&fields=f2,f3,f12,f14,f20")
            try:
                req = urllib.request.Request(url, headers=em_headers)
                with urllib.request.urlopen(req, timeout=8, context=CTX) as r:
                    d = json.loads(r.read().decode("utf-8", "ignore"))
            except Exception as e:
                print(f"[warn] {tag}板块 第{page}页失败:", e)
                break
            diff = (d.get("data") or {}).get("diff") or []
            if not diff:
                break
            got_any = True
            for it in diff:
                code, name = it.get("f12"), it.get("f14")
                if not code or not name:
                    continue
                if name.endswith("Ⅲ"):
                    continue
                name = name.rstrip("Ⅰ").strip()
                if _is_noise(name):
                    continue
                boards[code] = {"code": code, "name": name, "tag": tag}
            total = (d.get("data") or {}).get("total") or 0
            if page * 100 >= total:
                break

    vals = list(boards.values())
    if vals and got_any:
        with open(BOARD_CACHE, "w", encoding="utf-8") as f:
            json.dump(vals, f, ensure_ascii=False, indent=1)
        print(f"      东财板块列表已缓存 → {BOARD_CACHE}")
    elif os.path.exists(BOARD_CACHE):
        with open(BOARD_CACHE, encoding="utf-8") as f:
            vals = json.load(f)
        print(f"      在线拉取失败，改用缓存列表 {len(vals)} 个")
    return vals


def fetch_kline(board):
    """东财单板块日 K：返回 [(日期, 涨跌幅%), ...]"""
    url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?secid=90.{board['code']}&fields1=f1,f2,f3,f4,f5,f6"
           "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
           f"&klt=101&fqt=1&end=20500101&lmt={DAYS}")
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
            d = json.loads(r.read().decode("utf-8", "ignore"))
    except Exception:
        return board, []
    rows = []
    for line in ((d.get("data") or {}).get("klines") or []):
        parts = line.split(",")
        if len(parts) < 9:
            continue
        try:
            rows.append((parts[0], round(float(parts[8]), 2)))
        except (ValueError, IndexError):
            continue
    return board, rows


def eastmoney_full():
    """东财全量重拉（420 天历史）。失败返回空 dict。"""
    boards = fetch_board_list()
    if not boards:
        return {}
    per_date = {}
    ok = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(fetch_kline, b): b for b in boards}
        for f in as_completed(futs):
            board, rows = f.result()
            if rows:
                ok += 1
            for date, pct in rows:
                per_date.setdefault(date, []).append(
                    (board["name"], board["tag"], pct))
    print(f"      东财：成功 {ok}/{len(boards)} 个板块，覆盖 {len(per_date)} 个交易日")
    out = {}
    for date, items in per_date.items():
        day = build_day(items, 60)
        if day:
            out[date] = day
    return out


# =====================================================================
# 数据源 3：腾讯 / 新浪 当天快照（仅能补最新交易日）
# =====================================================================
QQ_RANK = ("https://proxy.finance.qq.com/cgi/cgi-bin/rank/pt/getRank"
           "?board_type={bt}&sort_type=price&direct=down&offset={off}&count=50")
SINA_HY = "https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php"
SINA_HQ = "https://hq.sinajs.cn/list=sh000001"
SINA_KLINE = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
              "CN_MarketData.getKLineData?symbol=sh000001&scale=240&ma=no&datalen=5")


def latest_trade_date():
    """确定最新交易日。三级降级，取到就返回：
    1) 上证指数日 K 的最后一根 —— 最可靠
    2) 上证指数实时快照里的日期字段
    3) 北京时间今天（兜底）
    """
    try:
        txt = _get(SINA_KLINE, retries=2, timeout=15,
                   referer="https://finance.sina.com.cn/")
        ds = re.findall(r'"(\d{4}-\d{2}-\d{2})"', txt)
        if ds:
            return max(ds)
    except Exception as e:
        print(f"      日K判定交易日失败：{e}")
    try:
        txt = _get(SINA_HQ, retries=2, timeout=15, encoding="gbk",
                   referer="https://finance.sina.com.cn/")
        m = re.search(r'"([^"]+)"', txt)
        if m:
            for p in m.group(1).split(","):
                p = p.strip()
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p):
                    return p
    except Exception as e:
        print(f"      快照判定交易日失败：{e}")
    return (dt.datetime.utcnow() + dt.timedelta(hours=8)).strftime("%Y-%m-%d")


def fetch_tencent():
    """腾讯板块排行当天快照 -> [(名称, 标签, 涨跌幅), ...]"""
    items = []
    for bt, tag in (("hy", "行业"), ("gn", "概念")):
        for off in range(0, 600, 50):
            try:
                d = json.loads(_get(QQ_RANK.format(bt=bt, off=off),
                                    retries=2, timeout=20))
            except Exception:
                break
            rl = (d.get("data") or {}).get("rank_list") or []
            if not rl:
                break
            for x in rl:
                name = (x.get("name") or "").strip()
                if not name or _is_noise(name):
                    continue
                try:
                    items.append((name, tag, round(float(x.get("zdf")), 2)))
                except (TypeError, ValueError):
                    continue
            if len(rl) < 50:
                break
    return items


def fetch_sina():
    """新浪行业板块当天快照（GBK）-> [(名称, 标签, 涨跌幅), ...]
    字段：代码,名称,家数,均价,涨跌额,涨跌幅,成交量,成交额,领涨股…
    """
    txt = _get(SINA_HY, retries=2, timeout=20, encoding="gbk",
               referer="https://finance.sina.com.cn/")
    m = re.search(r"=\s*(\{.*\})", txt, re.S)
    if not m:
        return []
    items = []
    for v in json.loads(m.group(1)).values():
        parts = str(v).split(",")
        if len(parts) < 6:
            continue
        name = parts[1].strip()
        if not name or _is_noise(name):
            continue
        try:
            items.append((name, "行业", round(float(parts[5]), 2)))
        except (ValueError, IndexError):
            continue
    return items


def main():
    path = os.path.join(OUT_DIR, "sector_daily.json")
    old = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
        print(f"[0/4] 已有历史 {len(old)} 个交易日"
              f"（{min(old) if old else '-'} ~ {max(old) if old else '-'}）")

    src, out = None, {}

    # --- 1) 同花顺全量 ---
    print("[1/4] 同花顺全量重建 ...")
    try:
        ths = ths_full()
    except Exception as e:
        print(f"      同花顺不可用：{e}")
        ths = {}
    if len(ths) >= max(60, len(old) // 2):
        out, src = ths, "同花顺（全量重建）"
    else:
        # --- 2) 东财全量 ---
        print("[2/4] 同花顺覆盖不足，尝试东财全量 ...")
        try:
            em = eastmoney_full()
        except Exception as e:
            print(f"      东财不可用：{e}")
            em = {}
        if len(em) >= max(60, len(old) // 2):
            out, src = em, "东财（全量重建）"
        else:
            # --- 3) 当天快照增量 ---
            print("[3/4] 降级为当天快照（腾讯 → 新浪）...")
            date = latest_trade_date()
            items, label = [], "-"
            for fn, lb in ((fetch_tencent, "腾讯"), (fetch_sina, "新浪")):
                try:
                    items = fn()
                except Exception as e:
                    print(f"      {lb}源失败：{e}")
                    items = []
                if items:
                    label = lb
                    print(f"      {lb}源返回 {len(items)} 个板块")
                    break
            day = build_day(items, 20)
            out = dict(old)
            if date and day:
                out[date] = day
                src = f"{label}（增量补齐 {date}）"
            else:
                src = None

    if not out or src is None:
        print("[✗] 本次未拿到任何数据，放弃写入（保护已有历史）")
        return

    print("[4/4] 落盘 ...")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"      数据源：{src}")
    print(f"      写出 {path}  交易日数={len(out)}  "
          f"体积={os.path.getsize(path)/1024:.0f}KB")

    for d in sorted(out.keys())[-4:]:
        print("      ", d,
              "领涨:", [f"{x['name']}{x['pct']}%" for x in out[d]["up"][:3]],
              "领跌:", [f"{x['name']}{x['pct']}%" for x in out[d]["down"][:3]])


if __name__ == "__main__":
    main()
