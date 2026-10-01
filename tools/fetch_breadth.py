# -*- coding: utf-8 -*-
"""
A 股「个股涨跌家数」抓取器（市场宽度）

为什么需要它：
    日历里原来只显示「当日 N 个板块 · X 涨 / Y 跌」——那是**板块**广度，
    383 个板块涨跌和 5000 多只个股涨跌不是一回事，容易高估或低估市场情绪。
    这里补上真正的**个股**涨跌家数。

口径：沪深两市 A 股（node=hs_a 会连北交所一起返回，这里按 symbol 前缀 bj 剔除）。
     剔除原因：北交所 270 来只都是小微盘，混进来会把「涨跌家数」这个情绪读数带偏；
     同花顺、东财两家的「涨跌家数」默认也是沪深两市口径。

数据源：
  A. 历史回填 —— 同花顺个股日线 https://d.10jqka.com.cn/v6/line/hs_{code}/01/{period}.js
     沪深代码统一用 hs_ 前缀（实测 hs_000001 / hs_300750 / hs_688981 都通）。
     ⚠️ 各 period 文件是**独立复权**的，跨文件拼接会有跳空，
     所以每根涨跌幅只在「同一个文件内部」用相邻收盘价算，并丢弃每个文件的第一根。
  B. 每日增量 —— 新浪全市场 A 股快照（node=hs_a，num=100，约 56 页），
     直接读每只股票的 changepercent 统计，一次拿全，不需要个股日线。

--------------------------------------------------------------------
⚠️ 两条踩过的坑（改动前请先读）：

1) 「抓失败」和「本来就没有」必须分开。
   同花顺对不存在的代码回 404、对瞬时故障回 502/超时：
     - 404  → 该周期确实没有文件（例如 2025 年才上市的新股没有 2025 年数据），算「拿到了」
     - 其它 → 真失败，必须重试；重试仍失败则该股**整只作废**
   之前只看 `if not dm` 判成败，于是「2025、2026 两个文件全挂、只剩 last 成功」的股票
   也被当成成功写进 done，永久跳过 —— 结果 2025 年那段的涨跌家数只有 630 只里的 437 只，
   2026-09-30 却有 628 只。同一份数据里前后覆盖率差 30%，比没有还糟。

2) 作废的股票必须**回滚**它的计数，且不能计入 done。
   否则下一次续跑重抓这只时，同一只股票会被累加两次（days 是纯计数累加，没有去重）。

输出：data/breadth_daily.json
  -> { "YYYY-MM-DD": {"up": n, "down": n, "flat": n, "total": n} }
  total 同时就是「当天有数据的股票数」，可直接用于覆盖率审计。

用法：
    python3 fetch_breadth.py                # 增量：用新浪快照补当天
    python3 fetch_breadth.py --backfill     # 回填：遍历全部个股的 2025/2026 日线
    python3 fetch_breadth.py --backfill --limit 50    # 小样本试跑
⚠️ 与 fetch_sectors.py 同样的红线：抓不到就保留旧数据，绝不把历史覆盖成空。
"""
import datetime as dt
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "data")
os.makedirs(OUT_DIR, exist_ok=True)

OUT = os.path.join(OUT_DIR, "breadth_daily.json")
STATE = os.path.join(OUT_DIR, ".breadth_state.json")   # 回填进度（可断点续跑）

THS_LINE = "https://d.10jqka.com.cn/v6/line/hs_{code}/01/{period}.js"
THS_REF = "https://q.10jqka.com.cn/"
SINA_LIST = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
             "Market_Center.getHQNodeData?page={page}&num=100&sort=symbol&asc=1&node=hs_a")
SINA_COUNT = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
              "Market_Center.getHQNodeStockCount?node=hs_a")
SINA_REF = "https://finance.sina.com.cn/"

PERIODS = ["2025", "2026", "last"]   # last 放最后：日期重叠时以它为准（最连续）
WORKERS = 10
PERIOD_RETRY = 4                     # 单个周期最多试几次（502/超时）
PASSES = 2                           # 全量跑两轮，第二轮只补第一轮失败的
_MIN_GAP = 0.03
COVER_RATIO = 0.80                   # 覆盖率下限之一：不低于中位数的 80%（见 audit）
COVER_RATIO_MIN = 0.65               # 覆盖率下限之二：不低于本次股票池的 65%
COVER_ABS = 200                      # 绝对下限，兜住 --limit 小样本

_last_call = [0.0]
_lock = threading.Lock()


# =====================================================================
# 网络：直连优先，失败再退代理
# ---------------------------------------------------------------------
# 本机环境全局挂了 HTTPS_PROXY=127.0.0.1:57009。实测这个代理会吞 Authorization
# 之类的头，而且长时间高频请求下会零星断连（同花顺那 502 有一部分就是它）。
# 直连同样能出去（curl --noproxy '*' 验证过），所以这里先试直连、失败再走系统代理，
# 两边都试过才算真失败。
# =====================================================================
_OPENER_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_OPENER_PROXY = urllib.request.build_opener()


def _throttle():
    with _lock:
        gap = time.time() - _last_call[0]
        if gap < _MIN_GAP:
            time.sleep(_MIN_GAP - gap)
        _last_call[0] = time.time()


def _fetch(url, headers, timeout):
    """返回 (文本, 是否404)。404 单独拎出来是因为它代表「确实没有」，不该重试。"""
    last = None
    for opener in (_OPENER_DIRECT, _OPENER_PROXY):
        _throttle()
        try:
            req = urllib.request.Request(url, headers=headers)
            with opener.open(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore"), False
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "", True          # 不存在的代码/周期：确定性答案，交给上层
            last = e
        except Exception as e:  # noqa
            last = e
    raise last


def _get(url, retries=3, timeout=20, referer=None):
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    last = None
    for i in range(retries):
        try:
            txt, is404 = _fetch(url, headers, timeout)
            if is404:
                return None              # 上层按「确实没有」处理
            return txt
        except Exception as e:  # noqa
            last = e
            time.sleep(min(4, 0.6 * (2 ** i)))
    raise last


def _jsonp(txt):
    """同花顺返回的是 quotebridge_xxx({...})，剥壳取对象"""
    if not txt:
        return None
    i, j = txt.find("("), txt.rfind(")")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(txt[i + 1:j])
    except Exception:
        return None


# =====================================================================
# 个股清单 + 当天快照（新浪）
# =====================================================================
def sina_page(page):
    txt = _get(SINA_LIST.format(page=page), retries=3, referer=SINA_REF)
    try:
        return json.loads(txt or "[]")
    except Exception:
        return []


def is_bj(sym, code):
    return sym.startswith("bj") or code.startswith(("920", "83", "87", "43"))


def sina_snapshot():
    """返回 (股票清单, 当天涨跌统计)。清单形如 [{'symbol':'sh600519','code':'600519'}]"""
    try:
        total = int(re.sub(r"\D", "", _get(SINA_COUNT, retries=2, referer=SINA_REF) or "") or 0)
    except Exception:
        total = 0
    pages = max(1, (total + 99) // 100) if total else 60

    stocks, up, down, flat, seen, skipped = [], 0, 0, 0, set(), 0
    ok_pages = 0
    for p in range(1, pages + 1):
        rows = sina_page(p)
        if not rows:
            break
        ok_pages += 1
        for it in rows:
            code = str(it.get("code") or "").strip()
            sym = str(it.get("symbol") or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            if is_bj(sym, code):          # 沪深口径：北交所不计（见文件头「口径」）
                skipped += 1
                continue
            stocks.append({"code": code, "symbol": sym})
            try:
                pct = float(it.get("changepercent"))
            except (TypeError, ValueError):
                flat += 1
                continue
            if pct > 0:
                up += 1
            elif pct < 0:
                down += 1
            else:
                flat += 1
    print(f"      新浪：{ok_pages}/{pages} 页，沪深 {len(stocks)} 只"
          f"（剔除北交所 {skipped} 只）")
    if len(stocks) < 1000:
        return stocks, None            # 页数太少视为快照不完整，别写坏数据
    return stocks, {"up": up, "down": down, "flat": flat,
                    "total": up + down + flat}


# =====================================================================
# 同花顺个股日线（历史回填）
# =====================================================================
def ths_stock_days(code):
    """返回 (code, {日期: 涨跌幅%}, 失败周期列表)。

    每个 period 文件内部独立算，丢弃各自第一根。
    `bad` 里的周期是**真失败**（502/超时重试完仍不通），不是「确实没有」——
    上层拿它决定这只股票整只作废。
    """
    out, bad = {}, []
    for period in PERIODS:
        obj, got = None, False
        for attempt in range(PERIOD_RETRY):
            try:
                txt = _get(THS_LINE.format(code=code, period=period),
                           retries=2, timeout=15, referer=THS_REF)
                if txt is None:              # 404：该周期确实没有文件
                    got = True
                    break
                obj = _jsonp(txt)
                if obj is not None:
                    got = True
                    break
            except Exception:  # noqa
                pass
            time.sleep(0.3 * (attempt + 1))
        if not got:
            bad.append(period)
            continue
        rows = [r for r in ((obj or {}).get("data") or "").split(";") if r]
        prev = None
        for line in rows:
            p = line.split(",")
            if len(p) < 5 or not re.fullmatch(r"\d{8}", p[0]):
                continue
            try:
                close = float(p[4])
            except ValueError:
                continue
            d = f"{p[0][:4]}-{p[0][4:6]}-{p[0][6:]}"
            # 只在同一文件内用相邻收盘价算 —— 跨文件复权基准不同，算了就是错的
            if prev:
                out[d] = round((close - prev) / prev * 100, 4)
            prev = close
    return code, out, bad


def load_state():
    if os.path.exists(STATE):
        try:
            with open(STATE, encoding="utf-8") as f:
                st = json.load(f)
            return set(st.get("done") or []), st.get("days") or {}
        except Exception:
            pass
    return set(), {}


def save_state(done, days):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"done": sorted(done), "days": days}, f,
                  ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, STATE)


def _run_pass(todo, done, days, tag):
    """跑一轮。返回 (ok, fail, partial)；partial 的贡献**已回滚**、也没进 done。"""
    ok = fail = partial = 0
    partial_codes = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(ths_stock_days, c): c for c in todo}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                code, dm, bad = f.result()
            except Exception:
                fail += 1
                continue
            if not dm:
                fail += 1
                continue
            if bad:
                # 有周期抓失败 → 整只作废。这里**不合并 dm**，所以不需要回滚；
                # 也不进 done，下一轮/下次续跑会重新抓（见文件头坑 2）。
                partial += 1
                partial_codes.append(code)
                continue
            ok += 1
            done.add(code)
            for d, pct in dm.items():
                cell = days.setdefault(d, {"up": 0, "down": 0, "flat": 0})
                if pct > 0:
                    cell["up"] += 1
                elif pct < 0:
                    cell["down"] += 1
                else:
                    cell["flat"] += 1
            if i % 200 == 0:
                save_state(done, days)
                el = time.time() - t0
                eta = el / i * (len(todo) - i)
                print(f"        [{tag}] {i}/{len(todo)}  成功 {ok} 作废 {partial} 失败 {fail}  "
                      f"已用 {el/60:.1f} 分  预计还需 {eta/60:.1f} 分")
    save_state(done, days)
    return ok, fail, partial, partial_codes


def backfill():
    stocks, _ = sina_snapshot()
    if not stocks:
        print("[✗] 拿不到股票清单，回填中止")
        return None
    if "--limit" in sys.argv:
        n = int(sys.argv[sys.argv.index("--limit") + 1])
        stocks = stocks[:n]
        print(f"      --limit {n}：只跑前 {n} 只")

    done, days = load_state()
    todo = [s["code"] for s in stocks if s["code"] not in done]
    print(f"      回填：总 {len(stocks)} 只，已完成 {len(stocks) - len(todo)}，待跑 {len(todo)}")

    t0 = time.time()
    ok = fail = partial_all = 0
    for p in range(1, PASSES + 1):
        if not todo:
            break
        if p > 1:
            print(f"      第 {p} 轮：补抓上一轮作废的 {len(todo)} 只 ...")
            time.sleep(5)
        o, f, pt, pcs = _run_pass(todo, done, days, f"第{p}轮")
        ok += o
        fail += f
        partial_all += pt if p == 1 else 0
        todo = pcs                       # 下一轮只补这一轮作废的
    print(f"      回填完成：成功 {ok}，失败 {fail}，仍作废 {len(todo)}，"
          f"覆盖 {len(days)} 个交易日，用时 {(time.time()-t0)/60:.1f} 分")
    if todo:
        print(f"      [!] 作废股票示例：{todo[:8]}（未计入 done，下次续跑会自动重抓）")
    return days, len(done)


def audit(days, universe):
    """覆盖率审计。universe = 本次跑通的股票数。返回可用天数。

    为什么要审：作废机制修好了「少算个别股票」，但如果某一整段日子集体抓失败，
    days 里那几天仍然只有几百只 —— 直接写出去就是**错的数据**，比空着更坏。
    所以低于下限的交易日一律剔除，界面上退回到原来的板块口径。

    下限取三个里最大的那个：
      · 绝对 200         —— 免得 --limit 10 这种小样本被整段砍掉
      · 股票池 × 65%     —— 主判据：5223 只的日子不该只有 1000 只的成交
      · 中位数 × 80%     —— 防「整体偏低」时主判据跟着一起松掉
    """
    if not days:
        return days
    tots = sorted(v["up"] + v["down"] + v["flat"] for v in days.values())
    med = tots[len(tots) // 2]
    floor = max(COVER_ABS, int(universe * COVER_RATIO_MIN), int(med * COVER_RATIO))
    bad = [d for d, v in days.items() if v["up"] + v["down"] + v["flat"] < floor]
    for d in bad:
        days.pop(d)
    print(f"      覆盖率审计：股票池 {universe} 只 · 中位 {med} 只 · 下限 {floor} 只 · "
          f"剔除 {len(bad)} 个交易日" + (f"（如 {sorted(bad)[:5]}）" if bad else ""))
    return days


def main():
    old = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            old = json.load(f)
        print(f"[0/2] 已有 {len(old)} 个交易日"
              f"（{min(old) if old else '-'} ~ {max(old) if old else '-'}）")

    out, src = None, None
    if "--backfill" in sys.argv:
        print("[1/2] 同花顺个股日线回填 ...")
        res = backfill()
        if res:
            days, universe = res
            # ⚠️ 回填是按「已跑过的股票数」累加的，必须整体替换而不是合并，
            # 否则断点续跑时同一只股票会被累加两次。
            days = audit(days, universe)
            for d in days:
                days[d]["total"] = days[d]["up"] + days[d]["down"] + days[d]["flat"]
            out, src = days, "同花顺（个股日线回填）"
    else:
        print("[1/2] 新浪快照增量 ...")
        stocks, snap = sina_snapshot()
        if snap:
            date = sina_latest_date()
            out = dict(old)
            out[date] = snap
            out, src = out, f"新浪快照（增量 {date}）"
        else:
            print("      [!] 快照不完整，放弃写入")

    if not out:
        print("[✗] 本次未拿到数据，保留原有文件不动")
        return

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    ks = sorted(out)
    print(f"[2/2] 写出 {OUT}")
    print(f"      数据源：{src}")
    print(f"      交易日数={len(ks)}  {ks[0]} ~ {ks[-1]}  "
          f"体积={os.path.getsize(OUT)/1024:.0f}KB")
    for d in ks[-4:]:
        v = out[d]
        print(f"      {d}  {v['total']} 只 · {v['up']} 涨 / {v['down']} 跌"
              f" / {v['flat']} 平  涨占比 {v['up']/max(1,v['total'])*100:.1f}%")
    # 头尾各看一眼覆盖是否均匀 —— 这是上一版翻车的地方，留个显式检查
    tot = [out[d]["total"] for d in ks]
    print(f"      覆盖：最低 {min(tot)} / 中位 {sorted(tot)[len(tot)//2]} / 最高 {max(tot)} 只")


def sina_latest_date():
    """用新浪上证指数日 K 的最后一根确定最新交易日"""
    try:
        txt = _get("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                   "CN_MarketData.getKLineData?symbol=sh000001&scale=240&ma=no&datalen=5",
                   retries=2, timeout=15, referer=SINA_REF)
        ds = re.findall(r'"(\d{4}-\d{2}-\d{2})"', txt or "")
        if ds:
            return max(ds)
    except Exception as e:
        print(f"      交易日判定失败：{e}")
    return (dt.datetime.utcnow() + dt.timedelta(hours=8)).strftime("%Y-%m-%d")


if __name__ == "__main__":
    main()
