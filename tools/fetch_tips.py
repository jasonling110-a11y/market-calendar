# -*- coding: utf-8 -*-
"""
交易提示抓取器 —— 限售解禁

数据源：东方财富数据中心 RPT_LIFT_STAGE（公开接口，31593 条，覆盖 2010 至 2035）
输出：data/tips.json  →  { "YYYY-MM-DD": { "c": 家数, "cap": 解禁市值(亿元), "top": [...] } }

为什么按日聚合而不是逐条存：
  全市场每天几十家公司解禁，逐条存会瞬间撑爆主包（原始 3.2 万条）。
  交易者真正关心的是「今天解禁压力大不大」「谁最大」，聚合到日级既省体积又直击重点。
"""
import json
import os
import ssl
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "tips.json")

MIN_DATE = "2018-01-01"        # 更早的解禁对复盘价值低，不收录
PAGE_SIZE = 500

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}


def _get(url, retries=4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                return json.loads(r.read().decode("utf-8", "ignore"))
        except Exception as e:      # noqa
            last = e
            time.sleep(0.6 * (i + 1))
    raise last


def fetch_lifts():
    """分页抓取全部限售解禁记录"""
    rows = []
    page = 1
    pages = None
    while True:
        url = ("https://datacenter-web.eastmoney.com/api/data/v1/get"
               "?reportName=RPT_LIFT_STAGE&columns=ALL"
               f"&pageSize={PAGE_SIZE}&pageNumber={page}"
               "&sortColumns=FREE_DATE&sortTypes=-1")
        try:
            d = _get(url)
        except Exception as e:
            print(f"  [warn] 第 {page} 页失败：{str(e)[:50]}")
            break
        res = d.get("result") or {}
        data = res.get("data") or []
        if pages is None:
            pages = res.get("pages") or 0
            print(f"      共 {res.get('count')} 条 / {pages} 页")
        if not data:
            break
        stop = False
        for it in data:
            fd = str(it.get("FREE_DATE") or "")[:10]
            if not fd:
                continue
            if fd < MIN_DATE:          # 已按日期倒序，遇到早于下限即可停
                stop = True
                break
            rows.append({
                "d": fd,
                "n": it.get("SECURITY_NAME_ABBR") or it.get("SECURITY_CODE") or "",
                "cap": it.get("LIFT_MARKET_CAP"),          # 万元
                "shares": it.get("CURRENT_FREE_SHARES"),   # 万股
                "type": it.get("FREE_SHARES_TYPE") or "",
            })
        if stop:
            break
        if pages and page >= pages:
            break
        page += 1
        if page % 10 == 0:
            print(f"      已抓 {page}/{pages} 页，{len(rows)} 条")
    return rows


def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def aggregate(rows):
    """按解禁日聚合：家数 / 总市值(亿元) / 市值最大的 3 家"""
    by_date = {}
    for r in rows:
        cap = _num(r["cap"])
        d = by_date.setdefault(r["d"], {"c": 0, "cap": 0.0, "top": []})
        d["c"] += 1
        if cap:
            d["cap"] += cap
            # 紧凑键：n 公司名 / v 解禁市值(亿元) / s 解禁股数(万股)
            d["top"].append({"n": r["n"], "v": round(cap / 10000, 1),
                             "s": round((_num(r["shares"]) or 0), 1)})
    out = {}
    for d, v in by_date.items():
        v["top"].sort(key=lambda x: -x["v"])
        # 只留市值最大的 2 家，且不带解禁类型长文本
        # （「首发原股东限售股份」这类字符串长度是公司名的两倍，2760 天累积下来白占几百 KB）
        out[d] = {
            "c": v["c"],
            "cap": round(v["cap"] / 10000, 1),      # 万元 -> 亿元
            "top": v["top"][:2],
        }
    return out


def main():
    print("[1/2] 抓取限售解禁 ...")
    rows = fetch_lifts()
    print(f"      原始 {len(rows)} 条（{MIN_DATE} 之后）")

    print("[2/2] 按日聚合 ...")
    agg = aggregate(rows)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(agg, f, ensure_ascii=False, separators=(",", ":"))

    total_cap = sum(v["cap"] for v in agg.values())
    biggest = sorted(agg.items(), key=lambda kv: -kv[1]["cap"])[:3]
    print(f"[✓] 覆盖 {len(agg)} 个解禁日，解禁总市值 {total_cap/10000:.1f} 万亿")
    print(f"    体积 {os.path.getsize(OUT)/1024:.0f}KB → {OUT}")
    for d, v in biggest:
        print(f"    压力最大：{d}  {v['c']} 家 / {v['cap']:.0f} 亿  首位 {v['top'][0]['n'] if v['top'] else '-'}")


if __name__ == "__main__":
    main()
