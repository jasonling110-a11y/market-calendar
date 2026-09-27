# -*- coding: utf-8 -*-
"""
板块代码探测：列表接口被限流时，用仍可用的 K 线接口反查板块代码与名称
输出：data/boards.json  —— 供 fetch_sectors.py 直接复用
"""
import json
import os
import ssl
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "boards.json")

NOISE = ['昨日', '涨停', '跌停', '连板', '首板', '打板', '触板', '炸板', '竞价',
         '融资融券', 'GDR', 'QFII', '社保重仓', '基金重仓', '机构重仓', '券商重仓',
         'MSCI', '标普', '富时', '沪股通', '深股通', '北向', '养老金', '险资',
         '预盈预增', '预亏预减', '业绩', '扭亏', '破净', 'ST', '次新',
         '转债', '送转', '举牌', '增持', '回购', '减持', '解禁',
         '员工持股', '股权激励', '参股', '分拆', '重组', '壳资源',
         '低价股', '高价股', '大盘', '中盘', '小盘', '微盘', '上证', '深证',
         '中证', '沪深', '茅指数', '宁组合', '北交所', '科创板', '创业板综']

_sem = [0.0]
GAP = 0.10


def probe(code):
    url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?secid=90.BK{code}&fields1=f1&fields2=f51,f52,f53"
           "&klt=101&fqt=1&end=20500101&lmt=1")
    for attempt in range(3):
        gap = time.time() - _sem[0]
        if gap < GAP:
            time.sleep(GAP - gap)
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
                _sem[0] = time.time()
                d = json.loads(r.read().decode("utf-8", "ignore"))
            data = d.get("data")
            if not data or not data.get("name"):
                return None
            name = data["name"]
            if name.endswith("Ⅲ"):
                return None
            name = name.rstrip("Ⅰ").strip()
            for kw in NOISE:
                if kw in name:
                    return None
            return {"code": "BK" + code, "name": name, "tag": "行业"}
        except Exception:
            _sem[0] = time.time()
            time.sleep(0.5 * (attempt + 1))
    return None


def main():
    codes = [f"{i:04d}" for i in range(400, 1101)]      # BK0400 ~ BK1100
    found = {}
    print(f"[i] 探测 {len(codes)} 个候选板块代码 ...")
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(probe, c): c for c in codes}
        done = 0
        for f in as_completed(futs):
            done += 1
            r = f.result()
            if r:
                found[r["code"]] = r
            if done % 100 == 0:
                print(f"    进度 {done}/{len(codes)}  命中 {len(found)}")
    vals = sorted(found.values(), key=lambda x: x["code"])
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(vals, f, ensure_ascii=False, indent=1)
    print(f"[✓] 命中 {len(vals)} 个板块 → {OUT}")
    print("    示例:", [v["name"] for v in vals[:12]])


if __name__ == "__main__":
    main()
