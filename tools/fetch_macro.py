# -*- coding: utf-8 -*-
"""
宏观数据抓取器（全量版）—— 给日历补上「实际值 / 市场预期 / 前值 / 同比 / 环比」

数据源：金十数据中心 datacenter-api.jin10.com/reports/list_v2（公开接口）
  · 按 attr_id 查指标，返回 [日期, 今值, 预测值, 前值]
  · 每次 20 条，用 max_date 向前翻页
  · 响应的 keys 里带各列单位

指标清单来自金十数据中心（attr_id 1~94 中有数据的 83 个，这里收录名称可考的 54 个，
外加 5 个中国统计局口径指标）。

输出：data/macro_series.json
⚠️ 只写入真实抓到的数值，抓不到就留空，绝不用推算值冒充实测值。
"""
import calendar as _cal
import datetime as dt
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "macro_series.json")

MIN_YEAR = 2008          # 早于此年份的数据不收录，控制数据包体积
CAL_YEAR = 2016          # 低重要度指标只保留此年份之后的数据

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

HEADERS = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "Chrome/107.0.0.0 Safari/537.36",
    "x-app-id": "rU6QIu7JHe2gOUeR",
    "x-csrf-token": "x-csrf-token",
    "x-version": "1.0.0",
}

# (attr_id, 指标键, 展示名, 地区, 分类, 重要度 3高/2中/1低)
INDICATORS = [
    # ---------------- 美国：通胀 ----------------
    (9,  "us_cpi",      "美国 CPI 月率",           "US", "macro_us", 3),
    (6,  "us_ccpi",     "美国核心 CPI 月率",        "US", "macro_us", 3),
    (37, "us_ppi",      "美国 PPI 月率",           "US", "macro_us", 2),
    (7,  "us_cppi",     "美国核心 PPI 月率",        "US", "macro_us", 2),
    (80, "us_pce",      "美国核心 PCE 物价指数年率",  "US", "macro_us", 3),
    (79, "us_exprice",  "美国出口价格指数",          "US", "macro_us", 1),
    (18, "us_imprice",  "美国进口物价指数",          "US", "macro_us", 1),
    # ---------------- 美国：就业 ----------------
    (33, "us_nfp",      "美国非农就业人数",          "US", "macro_us", 3),
    (47, "us_unemp",    "美国失业率",              "US", "macro_us", 3),
    (1,  "us_adp",      "美国 ADP 就业人数",        "US", "macro_us", 2),
    (44, "us_claims",   "美国初请失业金人数",         "US", "macro_us", 2),
    (78, "us_challenger", "美国挑战者企业裁员人数",     "US", "macro_us", 1),
    (93, "us_lmci",     "美联储劳动力市场状况指数",     "US", "macro_us", 1),
    # ---------------- 美国：增长与景气 ----------------
    (53, "us_gdp",      "美国 GDP",               "US", "macro_us", 3),
    (28, "us_ism",      "美国 ISM 制造业 PMI",      "US", "macro_us", 3),
    (29, "us_ism_svc",  "美国 ISM 非制造业 PMI",     "US", "macro_us", 2),
    (74, "us_markit_mfg", "美国 Markit 制造业 PMI",  "US", "macro_us", 1),
    (89, "us_markit_svc", "美国 Markit 服务业 PMI",  "US", "macro_us", 1),
    (20, "us_indprod",  "美国工业产出月率",          "US", "macro_us", 2),
    (13, "us_durable",  "美国耐用品订单月率",         "US", "macro_us", 2),
    (16, "us_factory",  "美国工厂订单月率",          "US", "macro_us", 1),
    (4,  "us_bizinv",   "美国商业库存月率",          "US", "macro_us", 1),
    (63, "us_nfib",     "美国 NFIB 小型企业信心指数",  "US", "macro_us", 1),
    # ---------------- 美国：消费与信心 ----------------
    (39, "us_retail",   "美国零售销售月率",          "US", "macro_us", 2),
    (35, "us_perspend", "美国个人支出月率",          "US", "macro_us", 2),
    (81, "us_realcons", "美国实际个人消费支出季率",     "US", "macro_us", 1),
    (5,  "us_conf",     "美国谘商会消费者信心指数",     "US", "macro_us", 2),
    (50, "us_mich",     "美国密歇根大学消费者信心指数",  "US", "macro_us", 2),
    # ---------------- 美国：房地产 ----------------
    (17, "us_housing_start", "美国新屋开工总数年化",  "US", "macro_us", 2),
    (3,  "us_buildpermit", "美国营建许可总数",       "US", "macro_us", 1),
    (32, "us_newsale",  "美国新屋销售总数年化",       "US", "macro_us", 1),
    (15, "us_homesale", "美国成屋销售总数年化",       "US", "macro_us", 2),
    (34, "us_pendsale", "美国成屋签约销售指数月率",    "US", "macro_us", 1),
    (31, "us_nahb",     "美国 NAHB 房产市场指数",    "US", "macro_us", 1),
    (51, "us_fhfa",     "美国 FHFA 房价指数月率",    "US", "macro_us", 1),
    (52, "us_spcs",     "美国 S&P/CS20 房价指数年率", "US", "macro_us", 1),
    # ---------------- 美国：贸易与能源 ----------------
    (42, "us_trade",    "美国贸易帐",              "US", "macro_us", 2),
    (12, "us_curracct", "美国经常账",              "US", "macro_us", 1),
    (10, "us_eia",      "美国 EIA 原油库存",        "US", "macro_us", 1),
    (69, "us_api",      "美国 API 原油库存",        "US", "macro_us", 1),
    # ---------------- 中国 ----------------
    (56, "cn_cpi_y",    "中国 CPI 年率",           "CN", "macro_cn", 3),
    (72, "cn_cpi",      "中国 CPI 月率",           "CN", "macro_cn", 2),
    (60, "cn_ppi_y",    "中国 PPI 年率",           "CN", "macro_cn", 3),
    (57, "cn_gdp",      "中国 GDP 年率",           "CN", "macro_cn", 3),
    (59, "cn_m2_y",     "中国 M2 货币供应年率",      "CN", "macro_cn", 3),
    (58, "cn_indprod",  "中国规模以上工业增加值年率",   "CN", "macro_cn", 2),
    (65, "cn_pmi_off",  "中国官方制造业 PMI",        "CN", "macro_cn", 3),
    (75, "cn_pmi_nonm", "中国官方非制造业 PMI",      "CN", "macro_cn", 2),
    (73, "cn_pmi_cx",   "中国财新制造业 PMI 终值",    "CN", "macro_cn", 2),
    (67, "cn_pmi_cxsvc", "中国财新服务业 PMI",       "CN", "macro_cn", 2),
    (61, "cn_trade",    "中国以美元计算贸易帐",       "CN", "macro_cn", 2),
    (66, "cn_export",   "中国以美元计算出口年率",      "CN", "macro_cn", 2),
    (77, "cn_import",   "中国以美元计算进口年率",      "CN", "macro_cn", 2),
    (76, "cn_fxres",    "中国外汇储备",             "CN", "macro_cn", 1),
]

_sem = [0.0]
GAP = 0.05               # 全局最小请求间隔
skipped = [0]            # 被过滤的 01-01 假日期数据点计数


def _get(url, retries=4, timeout=20):
    last = None
    for i in range(retries):
        gap = time.time() - _sem[0]
        if gap < GAP:
            time.sleep(GAP - gap)
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                _sem[0] = time.time()
                return json.loads(r.read().decode("utf-8", "ignore"))
        except Exception as e:      # noqa
            last = e
            _sem[0] = time.time()
            time.sleep(0.4 * (i + 1))
    raise last


def _num(v):
    try:
        f = float(v)
        if f != f:          # NaN
            return None
        return round(f, 4)
    except (TypeError, ValueError):
        return None


def _prev_day(s):
    """'2026-09-11' -> '2026-09-10'，用于翻页游标"""
    import datetime as dt
    try:
        d = dt.date.fromisoformat(s) - dt.timedelta(days=1)
        return d.isoformat()
    except ValueError:
        return None


def fetch_indicator(attr, name, key):
    """抓单个指标的全部历史（翻页到 MIN_YEAR 之前为止）"""
    rows, unit = [], ""
    max_date = ""
    for _ in range(80):                       # 硬上限，防死循环
        url = ("https://datacenter-api.jin10.com/reports/list_v2"
               f"?max_date={max_date}&category=ec&attr_id={attr}"
               f"&_={int(time.time() * 1000)}")
        d = _get(url)
        data = d.get("data") or {}
        vals = data.get("values") or []
        if not vals:
            break
        keys = data.get("keys") or []
        if not unit and len(keys) > 1:
            unit = (keys[1] or {}).get("unit", "") or ""
        for v in vals:
            if not v or not v[0]:
                continue
            date = str(v[0])[:10]
            if date < f"{MIN_YEAR}-01-01":
                return rows, unit
            # 过滤 01-01：接口对早期（超出精确范围）的数据会退化到「月份精度」，
            # 日期被填成该月 1 日。元旦不可能发布经济数据，这类点的日期是假的，
            # 留着会让日历上 1 月 1 日凭空冒出二十几条数据。
            if date[5:] == "01-01":
                skipped[0] += 1
                continue
            rows.append({
                "d": date,
                "a": _num(v[1]) if len(v) > 1 else None,
                "f": _num(v[2]) if len(v) > 2 else None,
                "p": _num(v[3]) if len(v) > 3 else None,
            })
        if len(vals) < 20:                    # 最后一页
            break
        nxt = _prev_day(str(vals[-1][0])[:10])
        if not nxt or nxt == max_date:
            break
        max_date = nxt
    return rows, unit


def _month_cn_to_ym(s):
    s = str(s)
    if "年" in s:
        try:
            return int(s[:4]), int(s[5:7].replace("月", "").strip())
        except ValueError:
            return None, None
    if len(s) == 6 and s.isdigit():
        return int(s[:4]), int(s[4:6])
    return None, None


def _last_day(y, m):
    import calendar
    return calendar.monthrange(y, m)[1]


def _add_month(y, m, delta):
    t = y * 12 + (m - 1) + delta
    return t // 12, (t % 12) + 1


def _pub_date(y, m, rule):
    """统计局口径：把「数据所属月份」换算成「公布日期」"""
    if rule == "month_end":
        return f"{y}-{m:02d}-{_last_day(y, m):02d}"
    if rule == "next_9":
        yy, mm = _add_month(y, m, 1)
        return f"{yy}-{mm:02d}-09"
    if rule == "next_13":
        yy, mm = _add_month(y, m, 1)
        return f"{yy}-{mm:02d}-13"
    return f"{y}-{m:02d}-01"


def fetch_stat_series():
    """中国统计局口径：实际值 + 同比 + 环比（官方数据无公开市场预期）"""
    out = {}
    try:
        import akshare as ak
    except ImportError:
        print("  [skip] 未安装 akshare，跳过统计局口径指标")
        return out

    def grab(fn, key, name, rule, field, unit="", mom_field=None):
        try:
            df = getattr(ak, fn)()
        except Exception as e:
            print(f"  [fail] {name}: {str(e)[:60]}")
            return
        rows = []
        for _, r in df.iterrows():
            y, m = _month_cn_to_ym(r.get("月份"))
            if not y or y < MIN_YEAR:
                continue
            a = _num(r.get(field))
            if a is None:
                continue
            rows.append({"d": _pub_date(y, m, rule), "a": a, "f": None, "p": None,
                         "y": a, "m": _num(r.get(mom_field)) if mom_field else None})
        if rows:
            rows.sort(key=lambda x: x["d"])
            out[key] = {"n": name, "u": unit, "r": "CN", "i": 3 if "PMI" in name else 2, "v": rows}
            print(f"  [ok] {name:26s} {len(rows):4d} 期  最新 {rows[-1]['d']}")

    grab("macro_china_pmi",      "cn_pmi_st", "中国制造业 PMI(统计局)", "month_end",
         "制造业-指数", "")
    grab("macro_china_ppi",      "cn_ppi_st", "中国 PPI 同比(统计局)", "next_9",
         "当月同比增长", "%")
    grab("macro_china_money_supply", "cn_m2", "中国 M2 同比", "next_13",
         "货币和准货币(M2)-同比增长", "%", "货币和准货币(M2)-环比增长")
    grab("macro_china_shrzgm",   "cn_shrong", "中国社会融资规模增量", "next_13",
         "社会融资规模增量", "亿元")

    # LPR：TRADE_DATE 本身就是公布日
    try:
        df = ak.macro_china_lpr()
        rows, seen = [], set()
        for _, r in df.iterrows():
            d = str(r.get("TRADE_DATE", ""))[:10]
            if not d or d < f"{MIN_YEAR}-01-01" or d[:7] in seen:
                continue
            a = _num(r.get("LPR1Y"))
            if a is None:
                continue
            seen.add(d[:7])
            rows.append({"d": d, "a": a, "f": None, "p": None, "y": None, "m": None})
        if rows:
            rows.sort(key=lambda x: x["d"])
            out["cn_lpr"] = {"n": "中国 LPR 1 年期", "u": "%", "r": "CN", "i": 3, "v": rows}
            print(f"  [ok] {'中国 LPR':26s} {len(rows):4d} 期  最新 {rows[-1]['d']}")
    except Exception as e:
        print(f"  [fail] LPR: {str(e)[:60]}")

    return out


# ---------------- 美国宏观：东财全球宏观（数据源实时，金十已滞后一年）----------------
# 为什么必须加这一路：金十的美国序列最新只到 2025-09，而日历窗口是「近 18 个月 +
# 未来 15 个月」，等于这半年多的美国读数全部没有值，日历行只能显示一个空名字。
# 东财「全球宏观」接口一次给全：公布日 PUBLISH_DATE / 今值 VALUE / 前值 PRE_VALUE /
# 报告期 REPORT_DATE_CH，正好是日历要的三样东西。
#
# 单位换算（scale = 原始值 ÷ scale 得展示值）：
#   非农原始是「千人」，展示用「万人」→ 10
#   贸易帐原始是「百万美元」，展示用「亿美元」→ 100
EM_US_REPORT = "RPT_ECONOMICVALUE_USANEW"
EM_US = [
    # (INDICATOR_ID, 指标键, 展示名, 单位, 重要度, scale)
    ("EMG00000770", "us_cpi",          "美国 CPI 月率",             "%",   3, 1),
    ("EMG00000733", "us_cpi_y",        "美国 CPI 年率",             "%",   3, 1),
    ("EMG00000771", "us_ccpi",         "美国核心 CPI 月率",          "%",   3, 1),
    ("EMG00000746", "us_ccpi_y",       "美国核心 CPI 年率",          "%",   3, 1),
    ("EMG00177897", "us_ppi",          "美国 PPI 月率",             "%",   2, 1),
    ("EMG00177909", "us_cppi",         "美国核心 PPI 月率",          "%",   2, 1),
    ("EMG00177799", "us_cppi_y",       "美国核心 PPI 年率",          "%",   2, 1),
    ("EMG00152118", "us_nfp",          "美国非农就业人数",            "万人", 3, 10),
    ("EMG00001039", "us_unemp",        "美国失业率",                "%",   3, 1),
    ("EMG00002790", "us_ism",          "美国 ISM 制造业 PMI",        "",    3, 1),
    ("EMG00002791", "us_ism_svc",      "美国 ISM 服务业 PMI",        "",    2, 1),
    ("EMG00159633", "us_gdp",          "美国 GDP 环比折年率",         "%",   3, 1),
    ("EMG00342254", "us_durable",      "美国耐用品订单月率",           "%",   2, 1),
    ("EMG00003721", "us_retail",       "美国零售销售月率",            "%",   2, 1),
    ("EMG00000700", "us_trade",        "美国贸易帐",                "亿美元", 2, 100),
    ("EMG00003078", "us_homesale",     "美国成屋销售",               "万户", 2, 1),
    ("EMG00342249", "us_pendsale",     "美国成屋签约销售月率",         "%",   1, 1),
    ("EMG00003224", "us_housing_start", "美国新屋开工年化",           "万户", 2, 1),
    ("EMG00002847", "us_conf",         "美国谘商会消费者信心指数",      "",    2, 1),
    ("EMG00002846", "us_mich",         "美国密歇根大学消费者信心指数",   "",    2, 1),
    ("EMG00342250", "us_fed_upper",    "美国联邦基金利率上限",         "%",   3, 1),
    ("EMG00358536", "us_fed_lower",    "美国联邦基金利率下限",         "%",   3, 1),
]
EM_US_BY_ID = {r[0]: r for r in EM_US}


def _em_us_pub(y, m, rule):
    """东财全球宏观的 REPORT_DATE 只是「报告期」，真正的公布日另有 PUBLISH_DATE 字段，
    所以这里不推算，直接取 PUBLISH_DATE。"""
    return None


def _rp(rd):
    """把 2026-08-01 这样的报告期转成日历行用的 YYMM（2608）。
    日历行第 6 位存的就是报告期，用它匹配可以绕开「公布日差几天」的问题。"""
    rd = str(rd or "")[:10]
    if len(rd) < 7:
        return ""
    return f"{rd[2:4]}{rd[5:7]}"


# ---------------- 美国：FRED 免密钥 CSV（补东财美国报告里没有的指标）----------------
# 为什么需要它：东财 RPT_ECONOMICVALUE_USANEW 只覆盖 24 个指标，PCE、初请失业金、
# 工业产出、新屋销售、商业库存、工厂订单、EIA 原油库存全都不在里面；金十的美国序列
# 又停在 2025-09。结果是日历上这些行长期「只有名字、没有数字」。
# FRED 的 fredgraph.csv 不需要 API Key，直连就能拿到最新数据。
#
# 变换（transform）：
#   lv  = 直接取水平值（÷div 换算单位）
#   mom = 环比 %（(本期/上期-1)×100）
#   yoy = 同比 %（按月频往前推 12 期，季频推 4 期）
# lag = 报告期结束后大概多少天公布，用来给出一个合理的公布日；
#       真正对齐日历行靠的是 rp（报告期），lag 只影响「关键数值」卡片落在哪天。
FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
FRED = [
    # (FRED序列, 指标键, 展示名, 单位, 重要度, 变换, 除数, lag天)
    ("PCEPILFE",  "us_pce",         "美国核心 PCE 物价指数年率", "%",    3, "yoy", 1,     31),
    ("PCEPILFE",  "us_pce_m",       "美国核心 PCE 物价指数月率", "%",    3, "mom", 1,     31),
    ("PCEPI",     "us_pce_h",       "美国 PCE 物价指数月率",     "%",    2, "mom", 1,     31),
    ("PCE",       "us_perspend",    "美国个人支出月率",          "%",    2, "mom", 1,     31),
    ("ICSA",      "us_claims",      "美国初请失业金人数",        "万人",  2, "lv",  10000,  5),
    ("INDPRO",    "us_indprod",     "美国工业产出月率",          "%",    2, "mom", 1,     15),
    ("HSN1F",     "us_newsale",     "美国新屋销售总数年化",       "万户",  2, "lv",  10,    24),
    ("BUSINV",    "us_bizinv",      "美国商业库存月率",          "%",    1, "mom", 1,     45),
    ("AMTMNO",    "us_factory",     "美国工厂订单月率",          "%",    1, "mom", 1,     25),
    ("PERMIT",    "us_buildpermit", "美国营建许可总数",          "万户",  1, "lv",  10,    18),
    ("JTSJOL",    "us_jobopen",     "美国职位空缺人数",          "万人",  2, "lv",  10,    35),
    ("SPCS20RSA", "us_spcs",        "美国 S&P/CS20 房价指数年率", "%",    1, "yoy", 1,     60),
    ("IEABC",     "us_curracct",    "美国经常账",               "亿美元", 1, "lv",  100,   90),
    ("IPMAN",     "us_indprod_mfg", "美国工业产出指数:制造业月率",  "%",    1, "mom", 1,     15),
    # ADP 在 FRED 上只有「就业人数水平」，市场看的「新增就业」是它的月度增量
    ("ADPMNUSNERSA", "us_adp",      "美国 ADP 就业人数",         "万人",  2, "diff", 10000, 3),
]


def _fred_rows(series):
    """拉一个 FRED 序列，返回 [(date对象, 值)]。必须显式绕开环境代理：
    本机与 CI 都挂着 HTTP(S)_PROXY，走代理访问 FRED 会超时。"""
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(FRED_BASE.format(series),
                                 headers={"User-Agent": "Mozilla/5.0"})
    with op.open(req, timeout=30) as r:
        txt = r.read().decode("utf-8", "ignore")
    out = []
    for i, line in enumerate(txt.splitlines()):
        if i == 0 or not line.strip():
            continue
        p = line.split(",")
        if len(p) < 2:
            continue
        try:
            d = dt.date.fromisoformat(p[0].strip())
            v = float(p[1])
        except ValueError:
            continue                     # FRED 用 "." 表示缺失
        out.append((d, v))
    out.sort(key=lambda x: x[0])
    return out


def _fred_freq(rows):
    """按相邻日期的间隔推断频率（月 / 季 / 周）。"""
    if len(rows) < 3:
        return 1
    gaps = [(rows[i][0] - rows[i - 1][0]).days for i in range(1, len(rows))]
    g = sorted(gaps)[len(gaps) // 2]
    if g <= 10:
        return 52
    if g <= 45:
        return 12
    return 4


def fetch_fred():
    """抓 FRED，把指数水平换算成同比/环比，供日历行挂值。"""
    out = {}
    for sid, key, name, unit, imp, tfm, div, lag in FRED:
        try:
            rows = _fred_rows(sid)
        except Exception as e:
            print(f"  [fail] FRED {sid}: {str(e)[:50]}")
            continue
        rows = [x for x in rows if x[0].year >= MIN_YEAR and x[1] is not None]
        if len(rows) < 15:
            continue
        n = _fred_freq(rows)
        weekly = n == 52
        pts = []
        for i, (d, v) in enumerate(rows):
            if tfm == "lv":
                a = round(v / div, 2)
            elif tfm == "diff":
                # 存量序列的环比增量（ADP 就业人数就是这种：市场看的是「新增」）
                a = (round((v - rows[i - 1][1]) / div, 2)
                     if i >= 1 and rows[i - 1][1] else None)
            elif tfm == "mom":
                a = (round((v / rows[i - 1][1] - 1) * 100, 2)
                     if i >= 1 and rows[i - 1][1] else None)
            elif tfm == "yoy":
                a = (round((v / rows[i - n][1] - 1) * 100, 2)
                     if i >= n and rows[i - n][1] else None)
            else:
                a = None
            if a is None:
                continue
            # 周频序列（初请）的观测日就是当周截止日，公布日 = 观测日 + lag；
            # 月/季频的观测日是期初，先落到期末再 + lag。
            if weekly:
                pub_d = d + dt.timedelta(days=lag)
            else:
                pub_d = d.replace(day=_cal.monthrange(d.year, d.month)[1]) \
                    + dt.timedelta(days=lag)
            pts.append({"d": pub_d.isoformat(), "a": a, "f": None, "p": None,
                        "y": None, "m": None,
                        # 周频序列一个月有好几期，别带报告期（YYMM 会撞车）
                        "rp": "" if weekly else _rp(d.isoformat())})
        if not pts:
            continue
        pts.sort(key=lambda x: x["d"])
        for i in range(1, len(pts)):
            if pts[i]["p"] is None and pts[i - 1]["a"] is not None:
                pts[i]["p"] = pts[i - 1]["a"]
        out[key] = {"n": name, "u": unit, "r": "US", "c": "macro_us", "i": imp,
                    "v": pts, "_fred": sid}
        print(f"  [ok] FRED {name:24s} {len(pts):5d} 期  最新 {pts[-1]['d']}  值={pts[-1]['a']}")
    return out


def fetch_us_east():
    """抓东财美国宏观。一次翻页拉全表，按 INDICATOR_ID 分组。"""
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get"
           f"?reportName={EM_US_REPORT}&columns=ALL&pageNumber=1&pageSize=500"
           "&sortColumns=REPORT_DATE&sortTypes=-1&source=WEB&client=WEB"
           "&filter=" + urllib.parse.quote("(PUBLISH_DATE>='2016-01-01')"))
    rows = []
    page = 1
    while page <= 12:
        u = url.replace("pageNumber=1", f"pageNumber={page}")
        try:
            req = urllib.request.Request(u, headers=EM_HEADERS)
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                d = json.loads(r.read().decode("utf-8", "ignore"))
        except Exception as e:
            print(f"  [fail] 东财美国宏观 第{page}页: {str(e)[:50]}")
            break
        res = d.get("result") or {}
        batch = res.get("data") or []
        rows += batch
        if len(batch) < 500 or len(rows) >= (res.get("count") or 0):
            break
        page += 1
        time.sleep(0.3)

    groups = {}
    raw_names = {}
    for r in rows:
        iid = r.get("INDICATOR_ID")
        if iid in EM_US_BY_ID:
            groups.setdefault(iid, []).append(r)
            if r.get("INDICATOR_NAME"):
                raw_names.setdefault(iid, r["INDICATOR_NAME"])

    out = {}
    for iid, spec in EM_US_BY_ID.items():
        _, key, name, unit, imp, scale = spec
        pts, seen = [], set()
        for r in groups.get(iid, []):
            pub = str(r.get("PUBLISH_DATE") or "")[:10]
            if not pub or pub < f"{MIN_YEAR}-01-01" or pub in seen:
                continue
            a = _num(r.get("VALUE"))
            p = _num(r.get("PRE_VALUE"))
            if a is not None:
                a = round(a / scale, 2)
            if p is not None:
                p = round(p / scale, 2)
            if a is None and p is None:
                continue
            seen.add(pub)
            # rp = 报告期（YYMM）。东财的 PUBLISH_DATE 偶尔与东财日历的日期差 1~2 天，
            # 而日历行自带报告期（如 6-3 公布的 ADP 对应 2605），按报告期兜底匹配更稳。
            rp = _rp(str(r.get("REPORT_DATE") or ""))
            pts.append({"d": pub, "a": a, "f": None, "p": p, "y": None, "m": None,
                        "rp": rp})
        if not pts:
            continue
        pts.sort(key=lambda x: x["d"])
        # cn 保留东财原始指标名（如「美国:CPI:季调:环比」），
        # build_dataset 用它自动建立「日历条目 -> 宏观指标」的映射，
        # 否则每加一个指标都要手写一条 CAL2MACRO。
        out[key] = {"n": name, "u": unit, "r": "US", "c": "macro_us", "i": imp,
                    "v": pts, "cn": raw_names.get(iid, "")}
        last = [x for x in pts if x["a"] is not None]
        print(f"  [ok] {name:26s} {len(pts):4d} 期  最新 {pts[-1]['d']}"
              f"  值={last[-1]['a'] if last else '-'}")
    return out


# ---------------- 中国宏观：东财数据中心（数据源实时，比金十新）----------------
# 金十的经济日历数据只更新到 2025-09；东财这个接口的 CPI/PPI/PMI/GDP 是当月最新的，
# 所以中国核心指标以它为准，覆盖金十同名指标。
EM_CN = [
    # reportName, 指标键, 字段, 公布日规则, 数值变换
    # 变换说明：东财有些字段是「指数」而不是百分数（如 CPI 累计 100.9 = +0.9%），
    #          这类必须减 100 才能当同比/累计同比用，写 "minus100"。
    ("RPT_ECONOMY_CPI", "cn_cpi_y", "NATIONAL_SAME", "next9", None),
    ("RPT_ECONOMY_CPI", "cn_cpi", "NATIONAL_SEQUENTIAL", "next9", None),      # 环比
    ("RPT_ECONOMY_CPI", "cn_cpi_acc", "NATIONAL_ACCUMULATE", "next9", "minus100"),  # 累计同比
    ("RPT_ECONOMY_PPI", "cn_ppi_y", "BASE_SAME", "next9", None),
    ("RPT_ECONOMY_PPI", "cn_ppi_acc", "BASE_ACCUMULATE", "next9", "minus100"),      # 累计同比
    ("RPT_ECONOMY_PMI", "cn_pmi_off", "MAKE_INDEX", "monthend", None),
    ("RPT_ECONOMY_PMI", "cn_pmi_nonm", "NMAKE_INDEX", "monthend", None),      # 官方非制造业
    ("RPT_ECONOMY_GDP", "cn_gdp", "SUM_SAME", "next19", None),
    # 海关总署：出口/进口当月同比，与日历里的「出口金额(当月同比)」同口径
    ("RPT_ECONOMY_CUSTOMS", "cn_export", "EXIT_BASE_SAME", "next9", None),
    ("RPT_ECONOMY_CUSTOMS", "cn_import", "IMPORT_BASE_SAME", "next9", None),
    ("RPT_ECONOMY_CUSTOMS", "cn_export_acc", "EXIT_ACCUMULATE_SAME", "next9", None),
    ("RPT_ECONOMY_CUSTOMS", "cn_import_acc", "IMPORT_ACCUMULATE_SAME", "next9", None),
    # 统计局月度发布会：工业增加值当月同比 / 累计同比（发布会一般在 15~19 日）
    ("RPT_ECONOMY_INDUS_GROW", "cn_indprod", "BASE_SAME", "next16", None),
    ("RPT_ECONOMY_INDUS_GROW", "cn_indprod_acc", "BASE_ACCUMULATE", "next16", None),
    # 消费者信心指数（月末发布）
    ("RPT_ECONOMY_FAITH_INDEX", "cn_faith", "CONSUMERS_FAITH_INDEX", "monthend", None),
    # 社会消费品零售总额（统计局月度发布会）
    ("RPT_ECONOMY_TOTAL_RETAIL", "cn_retail", "RETAIL_TOTAL_SAME", "next16", None),
    ("RPT_ECONOMY_TOTAL_RETAIL", "cn_retail_acc", "RETAIL_ACCUMULATE_SAME", "next16", None),
    # 外汇和黄金储备（月初约 7 日）
    ("RPT_ECONOMY_GOLD_CURRENCY", "cn_fxres", "FOREX", "next7", None),
    # 新增人民币贷款（约 12 日）
    ("RPT_ECONOMY_RMB_LOAN", "cn_newloan", "RMB_LOAN", "next12", None),
    # 央行货币供应量（约 12~15 日）。注意东财这张表的字段名与常识相反：
    #   BASIC_CURRENCY = M2（三百多万亿）、CURRENCY = M1、FREE_CASH = M0（十几万亿），
    #   已按数值量级核对过，不是笔误。
    ("RPT_ECONOMY_CURRENCY_SUPPLY", "cn_m2_y", "BASIC_CURRENCY_SAME", "next12", None),
    ("RPT_ECONOMY_CURRENCY_SUPPLY", "cn_m1_y", "CURRENCY_SAME", "next12", None),
    ("RPT_ECONOMY_CURRENCY_SUPPLY", "cn_m0_y", "FREE_CASH_SAME", "next12", None),
]
EM_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}
CN_NAME = {
    "cn_cpi_y": ("中国 CPI 年率", 3, "%"),
    "cn_cpi": ("中国 CPI 月率", 3, "%"),
    "cn_cpi_acc": ("中国 CPI 累计年率", 2, "%"),
    "cn_ppi_y": ("中国 PPI 年率", 3, "%"),
    "cn_ppi_acc": ("中国 PPI 累计年率", 2, "%"),
    "cn_pmi_off": ("中国官方制造业 PMI", 3, ""),
    "cn_pmi_nonm": ("中国官方非制造业 PMI", 3, ""),
    "cn_gdp": ("中国 GDP 年率", 3, "%"),
    "cn_export": ("中国出口年率", 2, "%"),
    "cn_import": ("中国进口年率", 2, "%"),
    "cn_export_acc": ("中国出口累计年率", 2, "%"),
    "cn_import_acc": ("中国进口累计年率", 2, "%"),
    "cn_indprod": ("中国工业增加值年率", 2, "%"),
    "cn_indprod_acc": ("中国工业增加值累计年率", 2, "%"),
    "cn_faith": ("中国消费者信心指数", 1, ""),
    "cn_retail": ("中国社会消费品零售总额年率", 2, "%"),
    "cn_retail_acc": ("中国社会消费品零售总额累计年率", 2, "%"),
    "cn_fxres": ("中国外汇储备", 2, "亿美元"),
    "cn_newloan": ("中国新增人民币贷款", 2, "亿元"),
    "cn_m2_y": ("中国 M2 货币供应年率", 3, "%"),
    "cn_m1_y": ("中国 M1 货币供应年率", 2, "%"),
    "cn_m0_y": ("中国 M0 货币供应年率", 1, "%"),
}


def _em_pub_date(y, m, rule):
    import calendar
    if rule == "monthend":
        return f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"
    if rule == "next9":
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        return f"{ny}-{nm:02d}-09"
    if rule == "next19":                     # 季度 GDP 在次月中旬发布
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        return f"{ny}-{nm:02d}-19"
    if rule == "next16":                     # 统计局月度发布会（工业增加值等）
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        return f"{ny}-{nm:02d}-16"
    if rule == "next7":                      # 外汇储备（月初）
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        return f"{ny}-{nm:02d}-07"
    if rule == "next12":                     # 新增人民币贷款（月中）
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        return f"{ny}-{nm:02d}-12"
    return f"{y}-{m:02d}-01"


def fetch_cn_east():
    """抓东财中国宏观，覆盖金十同名指标（金十该部分滞后一年）"""
    out = {}
    for rep, key, field, rule, tfm in EM_CN:
        url = ("https://datacenter-web.eastmoney.com/api/data/v1/get"
               f"?reportName={rep}&columns=ALL&pageSize=240"
               "&sortColumns=REPORT_DATE&sortTypes=-1")
        try:
            req = urllib.request.Request(url, headers=EM_HEADERS)
            with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
                d = json.loads(r.read().decode("utf-8", "ignore"))
        except Exception as e:
            print(f"  [fail] {key}: {str(e)[:50]}")
            continue
        rows = ((d.get("result") or {}).get("data")) or []
        pts, seen = [], set()
        for r in rows:
            a = _num(r.get(field))
            if a is None:
                continue
            if tfm == "minus100":
                # 累计字段是「上年同期=100」的指数（100.9 表示 +0.9%）
                a = round(a - 100, 2)
            rd = str(r.get("REPORT_DATE") or "")[:10]
            y, m = int(rd[:4] or 0), int(rd[5:7] or 0)
            if not y or not m or y < MIN_YEAR:
                continue
            pub = _em_pub_date(y, m, rule)
            if pub in seen:
                continue
            seen.add(pub)
            pts.append({"d": pub, "a": a, "f": None, "p": None, "y": a, "m": None,
                        "rp": _rp(rd)})
        if pts:
            pts.sort(key=lambda x: x["d"])
            # 补「前值」：统计局口径只给当期值，但「前值」就是上一期的当期值。
            # 不补的话日历行只能显示一个实际值，跟美国那边的排版也不一致。
            for i in range(1, len(pts)):
                if pts[i]["p"] is None and pts[i - 1]["a"] is not None:
                    pts[i]["p"] = pts[i - 1]["a"]
            name, imp, unit = CN_NAME[key]
            out[key] = {"n": name, "u": unit, "r": "CN", "c": "macro_cn",
                        "i": imp, "v": pts, "_em": True}
            print(f"  [ok] {name:24s} {len(pts):4d} 期  最新 {pts[-1]['d']}  值={pts[-1]['a']}")
    return out


def main():
    print(f"[1/5] 抓取金十 {len(INDICATORS)} 个指标 ...")
    data = {}
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=5) as ex:
        # 元组顺序必须与下面解包一致：(attr_id, 指标键, 展示名, 地区, 分类, 重要度)
        futs = {ex.submit(fetch_indicator, a, n, k): (a, k, n, r, c, i)
                for a, k, n, r, c, i in INDICATORS}
        for f in as_completed(futs):
            attr, key, name, region, cat, imp = futs[f]
            try:
                rows, unit = f.result()
            except Exception as e:
                fail += 1
                print(f"  [fail] {name}: {str(e)[:50]}")
                continue
            # 低重要度指标只保留近几年，控制体积
            if imp == 1:
                rows = [x for x in rows if x["d"] >= f"{CAL_YEAR}-01-01"]
            if not rows:
                fail += 1
                continue
            rows.sort(key=lambda x: x["d"])
            data[key] = {"n": name, "u": unit, "r": region, "c": cat, "i": imp, "v": rows}
            ok += 1

    print("[2/5] 抓取统计局口径指标 ...")
    stat = fetch_stat_series()
    for k, v in stat.items():
        v.setdefault("c", "macro_cn")
        v.setdefault("i", 2)

    print("[3/5] 抓取东财中国宏观（覆盖金十同名指标，数据源更新）...")
    em = fetch_cn_east()

    print("[4/5] 抓取东财美国宏观（金十美国序列滞留 2025-09，必须覆盖）...")
    em_us = fetch_us_east()

    print("[5/5] 抓取 FRED 补缺（PCE / 初请 / 工业产出 / 新屋销售 / 库存等东财没有的）...")
    fred = fetch_fred()

    # ---- 与上次已有数据做并集合并，而不是整体覆盖 ----
    # 为什么必须这样：某个数据源今天抓失败（或换了运行环境、没装 akshare）时，
    # 整体覆盖会把上次已有的指标一起抹掉。实测踩过：
    # 用没装 akshare 的 Python 跑一次，cn_lpr / cn_shrong 直接消失。
    # 云端每天定时跑，这种「静默丢数据」是最难发现的坑。
    prev = {}
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            prev = {}

    def merge_series(old_e, new_e):
        """同一指标的历史序列取并集：同一天以新抓到的为准，
        新数据里没有的旧日子保留下来 —— 历史只增不减。

        同一天两条数据都有的情况要**按字段**合，不能整条替换：
        FRED 只给实际值（a），金十那条同期的「市场预期（f）」是真数据，
        整条替换会把预期列抹掉，日历上就只剩一个光秃秃的实际值。
        """
        if not new_e:
            return old_e
        if not old_e:
            return new_e
        byd = {}
        for x in old_e.get("v", []):
            if x.get("d"):
                byd[x["d"]] = x
        for x in new_e.get("v", []):
            if not x.get("d"):
                continue
            o = byd.get(x["d"])
            if o:
                m = dict(o)
                m.update({k: v for k, v in x.items() if v is not None})
                byd[x["d"]] = m
            else:
                byd[x["d"]] = x
        out = dict(old_e)
        out.update(new_e)
        out["v"] = [byd[k] for k in sorted(byd)]
        return out

    merged = {}
    for k in set(prev) | set(data) | set(stat) | set(em) | set(em_us) | set(fred):
        # 优先级：东财中国 > 东财美国 > 统计局 > 金十。
        # 东财美国必须排在金十前面 —— 金十的美国序列最新只到 2025-09，
        # 不覆盖的话日历里近一年的美国读数全是空的。
        if k in em:
            new_e = em[k]
        elif k in em_us:
            new_e = em_us[k]
        elif k in fred:
            new_e = fred[k]
        elif k in stat:
            new_e = stat[k]
        elif k in data:
            new_e = data[k]
        else:
            new_e = None
        merged[k] = merge_series(prev.get(k), new_e)

    stale = [k for k in merged
             if k not in data and k not in stat
             and k not in em and k not in em_us and k not in fred]
    if stale:
        print(f"    [i] {len(stale)} 个指标本次未抓到，沿用上次数据：{', '.join(sorted(stale)[:8])}"
              + ("…" if len(stale) > 8 else ""))

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, separators=(",", ":"))

    total = sum(len(v["v"]) for v in merged.values())
    eff = sum(1 for v in merged.values() for x in v["v"] if x["a"] is not None)
    print(f"\n[✓] 指标 {len(merged)} 个（成功 {ok} / 失败 {fail}）")
    print(f"    数据点 {total} 个，其中有实际值 {eff} 个")
    if skipped[0]:
        print(f"    已过滤 {skipped[0]} 个 01-01 假日期数据点（接口早期数据精度退化）")
    print(f"    体积 {os.path.getsize(OUT)/1024:.0f}KB → {OUT}")


if __name__ == "__main__":
    main()
