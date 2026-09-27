# -*- coding: utf-8 -*-
"""
A 股板块历史涨跌抓取器
数据源：东方财富板块行情接口（push2 / push2his）
输出：data/sector_daily.json  ->  { "YYYY-MM-DD": { "up": [...], "down": [...], "breadth": {...} } }
"""
import json
import os
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


def main():
    print("[1/3] 拉取板块列表 ...")
    boards = fetch_board_list()
    print(f"      板块数：{len(boards)}")
    if not boards:
        raise SystemExit("板块列表为空，终止")

    print(f"[2/3] 并发拉取 {len(boards)} 个板块近 {DAYS} 天日 K ...")
    per_date = {}       # date -> list of (name, pct)
    ok = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(fetch_kline, b): b for b in boards}
        for i, f in enumerate(as_completed(futs), 1):
            board, rows = f.result()
            if rows:
                ok += 1
            for date, pct in rows:
                per_date.setdefault(date, []).append((board["name"], board["tag"], pct))
            if i % 100 == 0:
                print(f"      进度 {i}/{len(boards)}")
    print(f"      成功 {ok}/{len(boards)} 个板块，覆盖 {len(per_date)} 个交易日")

    print("[3/3] 聚合每日领涨/领跌 ...")
    out = {}
    for date, items in per_date.items():
        if len(items) < 60:          # 板块覆盖不足，跳过不完整交易日
            continue
        items.sort(key=lambda x: -x[2])

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

        up = pick(items)
        rev = list(reversed(items))
        down = pick(rev)
        down.reverse()
        rising = sum(1 for _, _, p in items if p > 0)
        out[date] = {
            "up": up,
            "down": down,
            "breadth": {
                "total": len(items),
                "rising": rising,
                "falling": len(items) - rising,
            },
        }

    path = os.path.join(OUT_DIR, "sector_daily.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"      写出 {path}  交易日数={len(out)}  体积={os.path.getsize(path)/1024:.0f}KB")

    # 抽样打印最近 3 天
    for d in sorted(out.keys())[-3:]:
        print("      ", d, "领涨:", [f"{x['name']}{x['pct']}%" for x in out[d]["up"][:3]],
              "领跌:", [f"{x['name']}{x['pct']}%" for x in out[d]["down"][:3]])


if __name__ == "__main__":
    main()
