# -*- coding: utf-8 -*-
"""
A 股板块历史涨跌抓取器

数据源（按优先级）：
  1. 东方财富 push2 / push2his —— 能一次拉 420 天历史，是理想源。
     但实测该域名在不少网络环境（含本机与 GitHub Actions）完全不可达，
     连接 0.05 秒即被重置，备用镜像域名同样不可达。
  2. 腾讯 proxy.finance.qq.com —— 当天板块快照（行业 + 概念，含涨跌幅与涨跌家数）
  3. 新浪 vip.stock.finance.sina.com.cn —— 当天行业板块快照（GBK）

模式：东财可用时全量重拉；不可用时降级为「只补最新交易日」的增量追加。
⚠️ 绝不因为抓取失败就把已有历史覆盖成空 —— 那会让整段历史行情排行消失。

输出：data/sector_daily.json  ->  { "YYYY-MM-DD": { "up": [...], "down": [...], "breadth": {...} } }
"""
import datetime as dt
import json
import os
import re
import ssl
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT_DIR, exist_ok=True)

DAYS = 420  # 需要覆盖的天数（交易日约 280 个，多取一些保险）


_last_call = [0.0]
_MIN_GAP = 0.18          # 全局最小请求间隔，避免触发限流


def _get(url, retries=6):
    """带全局节流 + 指数退避的 GET。东财对高频请求会直接断连，必须退避。"""
    last = None
    for i in range(retries):
        gap = time.time() - _last_call[0]
        if gap < _MIN_GAP:
            time.sleep(_MIN_GAP - gap)
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                _last_call[0] = time.time()
                return json.loads(r.read().decode("utf-8", "ignore"))
        except Exception as e:  # noqa
            last = e
            _last_call[0] = time.time()
            time.sleep(min(8, 1.0 * (2 ** i)) + 0.3 * i)
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
]


def _is_noise(name):
    for kw in NOISE_KEYWORDS:
        if kw in name:
            return True
    return False


BOARD_CACHE = os.path.join(OUT_DIR, "boards.json")


def fetch_board_list():
    """行业板块(t:2) + 概念板块(t:3)，分页拉取 + 去噪 + 去重。
    列表接口易被限流，成功一次即落盘缓存，后续可离线复用。"""
    boards = {}
    got_any = False
    for fs, tag in (("m:90+t:2+f:!50", "行业"), ("m:90+t:3+f:!50", "概念")):
        for page in range(1, 7):     # 每页 100，最多 600 个
            url = (f"https://push2.eastmoney.com/api/qt/clist/get?pn={page}&pz=100"
                   "&po=1&np=1&fltt=2&invt=2&fid=f3&fs=" + urllib.parse.quote(fs) +
                   "&fields=f2,f3,f12,f14,f20")
            try:
                d = _get(url)
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
                if name.endswith("Ⅲ"):        # 三级行业，与二级重复
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
        print(f"      板块列表已缓存 → {BOARD_CACHE}")
    elif os.path.exists(BOARD_CACHE):
        with open(BOARD_CACHE, encoding="utf-8") as f:
            vals = json.load(f)
        print(f"      在线拉取失败，改用缓存列表 {len(vals)} 个")
    return vals


def fetch_kline(board):
    """拉取单个板块日 K：返回 [(日期, 涨跌幅%), ...]"""
    url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?secid=90.{board['code']}&fields1=f1,f2,f3,f4,f5,f6"
           "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
           f"&klt=101&fqt=1&end=20500101&lmt={DAYS}")
    try:
        d = _get(url)
    except Exception:
        return board, []
    # fields2 顺序：f51日期 f52开盘 f53收盘 f54最高 f55最低 f56成交量
    #              f57成交额 f58振幅 f59涨跌幅 f60涨跌额 f61换手率
    rows = []
    for line in ((d.get("data") or {}).get("klines") or []):
        parts = line.split(",")
        if len(parts) < 9:
            continue
        date = parts[0]
        try:
            pct = float(parts[8])          # f59 当日涨跌幅（相对前收盘）
        except (ValueError, IndexError):
            continue
        if pct == "" or pct != pct:        # NaN 过滤
            continue
        rows.append((date, round(pct, 2)))
    return board, rows


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


def build_day(items, min_items=20):
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
                per_date.setdefault(date, []).append((board["name"], board["tag"], pct))
    print(f"      东财：成功 {ok}/{len(boards)} 个板块，覆盖 {len(per_date)} 个交易日")
    out = {}
    for date, items in per_date.items():
        if len(items) < 60:          # 板块覆盖不足，跳过不完整交易日
            continue
        out[date] = build_day(items, 60)
    return out


# ---- 降级数据源（东财 push2 不可达时使用）------------------------------
# 腾讯：proxy.finance.qq.com 板块排行，行业 + 概念当天快照，UTF-8 JSON，
#       自带 zdf（涨跌幅）与 zgb（"57/122" 涨家数/总家数）
QQ_RANK = ("https://proxy.finance.qq.com/cgi/cgi-bin/rank/pt/getRank"
           "?board_type={bt}&sort_type=price&direct=down&offset={off}&count=50")
# 新浪：行业板块当天快照，GBK 文本；另用 hq.sinajs.cn 拿上证指数日期判定交易日
SINA_HY = "https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php"
SINA_HQ = "https://hq.sinajs.cn/list=sh000001"


def _text(url, encoding="utf-8", referer=None, retry=3):
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
                return r.read().decode(encoding, "ignore")
        except Exception as e:
            if i == retry - 1:
                raise
            time.sleep(0.8 * (i + 1))


SINA_KLINE = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
              "CN_MarketData.getKLineData?symbol=sh000001&scale=240&ma=no&datalen=5")


def latest_trade_date():
    """确定最新交易日。三级降级，取到就返回：

    1) 上证指数日 K 的最后一根 —— 最可靠，直接就是真实交易日
       （周末/中秋这类休市日不会出现在序列里，可避免把休市日写成空数据）
    2) 上证指数实时快照里的日期字段
    3) 北京时间今天（兜底）
    """
    try:
        txt = _text(SINA_KLINE, "utf-8", "https://finance.sina.com.cn/")
        ds = re.findall(r'"(\d{4}-\d{2}-\d{2})"', txt)
        if ds:
            return max(ds)
    except Exception as e:
        print(f"      日K判定交易日失败：{e}")
    try:
        txt = _text(SINA_HQ, "gbk", "https://finance.sina.com.cn/")
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
                d = json.loads(_text(QQ_RANK.format(bt=bt, off=off)))
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
                    pct = round(float(x.get("zdf")), 2)
                except (TypeError, ValueError):
                    continue
                items.append((name, tag, pct))
            if len(rl) < 50:
                break
    return items


def fetch_sina():
    """新浪行业板块当天快照（GBK） -> [(名称, 标签, 涨跌幅), ...]

    字段：代码,名称,家数,均价,涨跌额,涨跌幅,成交量,成交额,领涨股代码,…
    """
    txt = _text(SINA_HY, "gbk", "https://finance.sina.com.cn/")
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
            pct = round(float(parts[5]), 2)
        except (ValueError, IndexError):
            continue
        items.append((name, "行业", pct))
    return items


def main():
    path = os.path.join(OUT_DIR, "sector_daily.json")
    old = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
        print(f"[0/3] 已有历史 {len(old)} 个交易日"
              f"（{min(old) if old else '-'} ~ {max(old) if old else '-'}）")

    print("[1/3] 尝试东财全量重拉 ...")
    try:
        full = eastmoney_full()
    except Exception as e:
        print(f"      东财不可用：{e}")
        full = {}

    # 只有拿到足够多的历史才允许覆盖，否则会把已有数据清空
    if len(full) >= max(60, len(old) // 2):
        out, src = full, "东财（全量）"
    else:
        print("[2/3] 东财不可用，降级为当天快照（腾讯 → 新浪）...")
        date = latest_trade_date()
        items = []
        for fn, label in ((fetch_tencent, "腾讯"), (fetch_sina, "新浪")):
            try:
                items = fn()
            except Exception as e:
                print(f"      {label}源失败：{e}")
                items = []
            if items:
                print(f"      {label}源返回 {len(items)} 个板块")
                break
        day = build_day(items)
        out = dict(old)
        if date and day:
            out[date] = day
            src = f"{label}（增量补齐 {date}）"
        else:
            src = "无可用源，保持原数据不变"

    print("[3/3] 落盘 ...")
    # 兜底：新结果比旧的还少很多，说明抓取异常，绝不覆盖
    if not out:
        print("      [✗] 本次未拿到任何数据，放弃写入（保护已有历史）")
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"      数据源：{src}")
    print(f"      写出 {path}  交易日数={len(out)}  体积={os.path.getsize(path)/1024:.0f}KB")

    for d in sorted(out.keys())[-3:]:
        print("      ", d, "领涨:", [f"{x['name']}{x['pct']}%" for x in out[d]["up"][:3]],
              "领跌:", [f"{x['name']}{x['pct']}%" for x in out[d]["down"][:3]])


if __name__ == "__main__":
    main()
