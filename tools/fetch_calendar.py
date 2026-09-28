# -*- coding: utf-8 -*-
"""
财经日历抓取器（东方财富 RPT_CPH_FECALENDAR）

为什么需要它：之前只有「宏观数值」和 133 条人工历史事件，
用户最常看的那段窗口（今天前后两周）大量空白——未来 60 天有 50% 的日子是空的。
东财这个接口一个月就有 400+ 条，含具体时间、国家、报告期，
是撑起密度的关键数据源。

三类内容（缺一不可）：
  kind 0  经济数据  —— STD_TYPE_CODE=2，如「美国:CPI:同比(报告期:2026年09月)」
  kind 1  事件      —— 美联储/欧央行/日央行议息会议、国民经济运行情况发布会、
                        中央全会、行业会议、高峰论坛、新股申购
  kind 2  动态      —— 无 FE_TYPE 的资讯类，如「美联储公布货币政策会议纪要」
                        「台积电公布月度营业额」「CFTC周度持仓报告」
                        （实测每月 60+ 条，是交易者价值最高的一类，不能丢）

存储：紧凑数组 + 名称表（同一指标每月重复，字典存会把名字重复几百次）
  calendar.json = {
    "countries": ["美国", ...],
    "names":     ["CPI:同比", ...],            # 已剥掉国家前缀
    "days": {"2026-10-28": [[时间, 国家idx, 名称idx, 重要度, 类型, 报告期], ...]}
  }

接口限制：服务端只支持按日期过滤（START_DATE/END_DATE），
按 CITY/FE_TYPE 过滤返回空，所以只能按月抓全量再本地筛。

用法：python3 fetch_calendar.py
"""
import calendar as cal_mod
import datetime as dt
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)
OUT = os.path.join(DATA, "calendar.json")

# 未来只到 15 个月：实测 3 个月后东财自己也没多少排期（2027-01 仅 50 条）
PAST_MONTHS = 18
FUTURE_MONTHS = 15

API = "https://datacenter-web.eastmoney.com/api/data/v1/get"
REPORT = "RPT_CPH_FECALENDAR"
COLUMNS = "START_DATE,END_DATE,FE_CODE,FE_NAME,FE_TYPE,STD_TYPE_CODE,CITY"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"),
    "Referer": "https://data.eastmoney.com/",
}

# ---------- 保留策略 ----------
# 只保留五大资本市场（美国 / 中国 / 欧洲 / 日本 / 韩国）的主体。
# 加拿大、澳洲、巴西、俄罗斯、瑞士、新加坡等原本在列，但用户明确只要这五个市场，
# 它们的月度数据（合计 500+ 条）会挤掉真正要看的读数，一律不落库。
KEEP_CITY = {
    "美国", "中国", "中国香港", "中国澳门", "中国台湾",
    "欧盟", "欧元区", "英国", "德国", "法国", "意大利", "西班牙", "荷兰",
    "比利时", "奥地利", "芬兰", "爱尔兰", "葡萄牙", "希腊", "卢森堡",
    "日本", "韩国",
}

# 一级指标（保留）：这些是真正影响资产定价的读数
KW_TIER3 = ["CPI", "PPI", "PCE", "GDP", "PMI", "非农", "失业率", "利率决议",
            "M2", "货币供应", "社融", "社会融资", "新增信贷", "LPR", "MLF",
            "工业增加值", "社会消费品零售", "固定资产投资", "进出口", "贸易帐",
            "贸易差额", "外汇储备", "房价", "工业企业利润", "货币政策会议纪要"]
# 二级指标（保留）：重要但非核心。
# 注意这里**不含**「库存」——东财的「库存:铁矿石:46港」等港口库存一天 6 条，
# 是商品研究员看的细项，放进日历会淹掉真正重要的读数。
# 但 EIA/API 原油库存必须显式保留（它们才是每周真正推动油价的读数）。
KW_TIER2 = ["ISM", "初请", "ADP", "耐用品", "工业产出", "新屋", "成屋", "营建",
            "产能利用率", "零售销售", "消费者信心", "景气", "职位空缺", "时薪",
            "制造业", "服务业", "综合", "经济展望", "就业", "工业订单",
            "EIA原油库存", "EIA汽油库存", "EIA精炼油库存", "库欣原油库存",
            "出口", "进口", "利率", "汇率", "收入", "支出", "信贷", "贷款", "存款"]

# 噪音：同名指标的冗余子序列（户籍口径失业率、现价 GDP、汇率中间价…），
# 保留会让同一天出现 3 条「城镇调查失业率」变体
DROP_NAME_KW = ["人口数", "现价", "折年数", "期末汇率", "人民币汇率",
                "战略储备", "预测年度"]
# 仅当名称**以**「:值」结尾时才丢（如「GDP:值」「货物出口金额:值」）。
# 不能用子串匹配——会连「EIA原油库存:变动值」一起误杀。
DROP_NAME_SFX = [":值"]

# 展会/论坛对交易的价值低，即便保留也只给一星，避免和 CPI 抢注意力
LOW_KW = ["展览会", "博览会", "展会", "交易会", "糖酒会", "车展",
          "高峰论坛", "发布会（厂商）", "交流会议", "研讨会", "大会", "论坛"]

# 事件类里直接给最高重要度的
EVENT_TIER3 = ["美联储议息会议", "欧洲央行议息会议", "日本央行议息会议", "英国央行议息会议",
               "国民经济运行情况发布会", "中国共产党中央全会", "中央经济工作会议",
               "政府工作报告", "全国人民代表大会", "政治局会议", "瑞士央行议息会议",
               "加拿大央行议息会议", "澳洲联储议息会议", "新西兰联储议息会议"]

# 动态类（无 FE_TYPE）里价值高的信号
DYN_TIER2 = ["美联储主席", "美联储公布", "货币政策会议纪要", "利率决议",
             "主席鲍威尔", "货币会议纪要", "非农", "议息"]

# ---------- 裁剪规则（体积与价值的平衡，都是实测后定的）----------
# 1) 个股类：用户明确说过「个股的交易提示没什么用」，一并剔除，
#    否则每个新股都是一个唯一名字，名字表会被几百条一次性条目撑大
DROP_KW = ["新股申购", "新股上市", "限售解禁", "分红", "送转", "股东大会",
           "增持", "减持", "回购", "股权激励", "停牌", "复牌"]

# 2) 超长条目：实测最长 100+ 字（NYMEX 移仓换月提醒、政府停摆公告），
#    既是噪音又极占体积（名字表按字符计费）
MAX_NAME_LEN = 40

# 3) 展会类：一个月 30~40 条「XX国际XX展览会」，对交易价值低，
#    只保留临近窗口（近 3 月 + 未来 3 月），远端直接丢
EXPO_KW = ["展览会", "博览会", "展会", "交易会", "糖酒会", "车展"]
EXPO_BACK = 3
EXPO_FWD = 3

# 4) 动态类（央行讲话/报告/持仓）：量大且名字几乎全唯一，
#    只保留临近窗口（近 6 月 + 未来 3 月）——再远的讲话没有时效价值
DYN_BACK = 6
DYN_FWD = 3


def _get(url, retry=3):
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            return json.loads(urllib.request.urlopen(req, timeout=30, context=CTX)
                              .read().decode("utf-8", "ignore"))
        except Exception:
            if i == retry - 1:
                raise
            time.sleep(0.8 * (i + 1))


def fetch_month(year, month):
    """抓一个月（自动翻页，实测单月 300~450 条，pageSize 上限 500）"""
    start = f"{year}-{month:02d}-01"
    end = (f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01")
    flt = urllib.parse.quote(f"(START_DATE>='{start}')(START_DATE<'{end}')")
    rows, page = [], 1
    while page <= 6:
        url = (f"{API}?reportName={REPORT}&columns={COLUMNS}&pageSize=500"
               f"&pageNumber={page}&sortColumns=START_DATE&sortTypes=1&filter={flt}")
        d = _get(url)
        res = d.get("result") or {}
        batch = [r for r in (res.get("data") or [])
                 if r.get("FE_NAME") and r.get("START_DATE")]
        rows += batch
        if not batch or len(rows) >= (res.get("count") or 0):
            break
        page += 1
        time.sleep(0.35)
    return rows


# ---------- 名称清洗 ----------
def strip_country(name, city):
    """剥掉「美国:」「美国EIA…」这类国家前缀。
    国家已单独存一个字段，前缀会变成「美国 美国EIA原油库存」这种重复显示。

    只在后面跟冒号或 ASCII 字母数字时才剥：这样「美国EIA原油库存」能处理，
    而「中国银行间同业拆借」这种国家名本就是词一部分的不会被误伤。
    """
    if not city:
        return name.strip()
    for sep in (":", "："):
        if name.startswith(city + sep):
            return name[len(city) + 1:].strip()
    if name.startswith(city) and len(name) > len(city):
        nxt = name[len(city)]
        if nxt.isascii() and (nxt.isalnum() or nxt in "._-"):
            return name[len(city):].strip()
    return name.strip()


# 名称里没有信息量的标注（同日可能同时存在带与不带标注的两条，保留短的）
_NOISE_TAG = ["[同传]", "（同传）", "(同传)", "【同传】"]


def clean_tags(name):
    for t in _NOISE_TAG:
        name = name.replace(t, "")
    return name.strip()


def split_period(name):
    """拆出「(报告期:2026年09月)」，压成 '2609' 便于展示与排序"""
    m = re.match(r"^(.*?)\s*[（(]报告期[:：]([^）)]*)[)）]\s*$", name)
    if not m:
        return name.strip(), ""
    base = m.group(1).strip()
    per = m.group(2).strip()
    ym = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月", per)
    if ym:
        return base, ym.group(1)[2:] + ym.group(2).zfill(2)
    return base, per


def classify(row, today=None):
    """返回 (重要度, 类型, 基础名, 报告期)；不保留返回 None

    类型：0 经济数据 / 1 事件 / 2 动态
    裁剪规则见文件头部注释，全部是实测体积后定下的。
    """
    name = row["FE_NAME"].strip()
    city = row.get("CITY") or ""
    ftype = row.get("FE_TYPE") or ""
    std = str(row.get("STD_TYPE_CODE") or "")

    name = clean_tags(name)

    # 个股类直接丢（用户明确不需要）
    if any(k in name for k in DROP_KW):
        return None
    # 超长条目（移仓提醒 / 停摆公告）丢
    if len(name) > MAX_NAME_LEN:
        return None
    # 冗余子序列（户籍失业率 / 现价 GDP / 汇率中间价）丢
    if any(k in name for k in DROP_NAME_KW):
        return None
    if any(name.endswith(k) for k in DROP_NAME_SFX):
        return None

    base, period = split_period(name)
    date = row["START_DATE"][:10]
    low = any(k in base for k in LOW_KW)

    def near(days_back, days_fwd):
        y, m, d2 = int(date[:4]), int(date[5:7]), int(date[8:10])
        dd = dt.date(y, m, d2)
        return (today - dt.timedelta(days=days_back * 31)) <= dd \
            <= (today + dt.timedelta(days=days_fwd * 31))

    # --- 事件类 ---
    if ftype and ftype != "经济数据":
        # 展会类只在临近窗口保留
        if any(k in base for k in EXPO_KW) and not near(EXPO_BACK, EXPO_FWD):
            return None
        if ftype in EVENT_TIER3:
            imp = 3
        else:
            imp = 1 if low else 2        # 展会/论坛只给一星
        return imp, 1, base, ""
    if std in ("1", "3"):
        if any(k in base for k in EXPO_KW) and not near(EXPO_BACK, EXPO_FWD):
            return None
        return (1 if low else 2), 1, base, ""

    # --- 动态类（无 FE_TYPE，实测每月 60+ 条：央行讲话 / 报告 / 持仓）---
    if not ftype:
        if not near(DYN_BACK, DYN_FWD):
            return None
        imp = 2 if any(k in base for k in DYN_TIER2) else 1
        return imp, 2, base, ""

    # --- 经济数据（复用率最高的一类：5610 条只用到 345 个名字，全保留）---
    if city not in KEEP_CITY:
        return None
    if any(k in base for k in KW_TIER3):
        imp = 3 if city in ("美国", "中国") else 2
    elif any(k in base for k in KW_TIER2):
        imp = 2 if city in ("美国", "中国", "欧盟", "欧元区", "日本", "英国") else 1
    else:
        return None
    return imp, 0, strip_country(base, city), period


# 归一化时剥掉的修饰词。必须先归一化再判「是不是同一个指标」，
# 否则「CPI：当月同比」「CPI:累计同比」「CPI:季调:环比」会被当成三个不同指标，
# 一天里同一个 CPI 排出 6 行。
_CANON_DROP = ["季调", "非季调", "初值", "终值", "修正值", "预估值",
               "折年率", "年化", "当月", "总计", "总值", "数据", "报告"]


def _canon(name):
    n = (name or "").replace("：", ":").replace("（", "(").replace("）", ")")
    for w in _CANON_DROP:
        n = n.replace(w, "")
    while "::" in n:
        n = n.replace("::", ":")
    return n.strip(": ")


def _kou(name):
    """取口径（同比/环比）。东财同一指标会同时排 同比 与 环比 两行，
    偶尔还多一条没有口径的「裸名」（如「核心CPI」），后者信息量最低。"""
    n = _canon(name)
    if n.endswith("同比"):
        return "同比"
    if n.endswith("环比"):
        return "环比"
    return ""


def _base_of(name):
    """去掉口径后的基础指标名，用于判断「同一天同一指标排了几行」"""
    n = _canon(name)
    for suf in (":同比", ":环比", "同比", "环比"):
        if n.endswith(suf):
            return n[: -len(suf)].strip(": ")
    return n


def _period_ok(date, period):
    """报告期与发布日相差过远的直接丢掉。
    实测东财部分央行利率行会给出「报告期:2027年07月」这种远期口径，
    挂在 2026 年的日期上会让人误读。正常经济数据报告期领先发布日 0~3 个月。"""
    if not period or len(period) != 4:
        return True
    try:
        py, pm = 2000 + int(period[:2]), int(period[2:])
        ey, em = int(date[:4]), int(date[5:7])
    except ValueError:
        return False
    return 0 <= (ey * 12 + em) - (py * 12 + pm) <= 4


def main():
    today = dt.date.today()
    months = []
    y, m = today.year, today.month
    for i in range(-PAST_MONTHS, FUTURE_MONTHS + 1):
        mm = m + i
        yy = y + (mm - 1) // 12
        mm = (mm - 1) % 12 + 1
        months.append((yy, mm))

    print(f"[1/2] 抓取 {len(months)} 个月（{months[0][0]}-{months[0][1]:02d} "
          f"~ {months[-1][0]}-{months[-1][1]:02d}）...")

    cities, names = [], []
    city_idx, name_idx = {}, {}
    days = {}
    raw_n = kept_n = 0

    for i, (yy, mm) in enumerate(months, 1):
        try:
            rows = fetch_month(yy, mm)
        except Exception as e:
            print(f"      [{yy}-{mm:02d}] 失败：{type(e).__name__}")
            continue
        raw_n += len(rows)
        kept = 0
        for r in rows:
            c = classify(r, today)
            if not c:
                continue
            imp, kind, base, period = c
            date = r["START_DATE"][:10]
            hm = r["START_DATE"][11:16]

            city = r.get("CITY") or ""
            if city not in city_idx:
                city_idx[city] = len(cities)
                cities.append(city)
            if base not in name_idx:
                name_idx[base] = len(names)
                names.append(base)

            if kind == 0 and not _period_ok(date, period):
                period = ""
            days.setdefault(date, []).append(
                [hm, city_idx[city], name_idx[base], imp, kind, period,
                 _kou(base), _base_of(base)])
            kept += 1
        kept_n += kept
        print(f"      ({i:>2}/{len(months)}) {yy}-{mm:02d}  "
              f"原 {len(rows):>4d} → 留 {kept:>4d}")
        time.sleep(0.25)

    # 同一天同一指标排多行时收敛：
    #   ① 丢掉没有口径的「裸名」（如「核心CPI」），有 同比/环比 时它是冗余的
    #   ② 同一口径出现多次时只留一条
    for d in list(days):
        # 字段位序：[时间,国家,名称,重要度,类型,报告期,口径,基础名]
        groups = {}
        for e in days[d]:
            if e[4] == 0:
                groups.setdefault((e[1], e[7]), []).append(e)
        drop = set()
        for key, items in groups.items():
            if len(items) <= 1:
                continue
            if any(x[6] for x in items):            # 该基础指标存在带口径的行
                for x in items:
                    if not x[6]:                    # 「裸名」冗余，丢掉
                        drop.add(id(x))
        seen = {}
        keep = []
        for e in days[d]:
            if id(e) in drop:
                continue
            if e[4] == 0:
                sig = (e[1], e[7], e[6])            # 国家+基础名+口径，同口径只留一条
                if sig in seen:
                    continue
                seen[sig] = 1
            keep.append(e[:6])
        days[d] = keep

    # 每天内按时间排序，重要度高的排前面（同时间时）
    for d in days:
        days[d].sort(key=lambda x: (x[0] or "99:99", -x[3]))

    out = {"countries": cities, "names": names, "days": days,
           "generatedAt": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "range": [min(days) if days else "", max(days) if days else ""]}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size = os.path.getsize(OUT)
    print(f"\n[2/2] 完成")
    print(f"      原始 {raw_n} 条 → 保留 {kept_n} 条（{kept_n/max(1,raw_n)*100:.0f}%）")
    print(f"      覆盖 {len(days)} 天 / {len(names)} 个指标名 / {len(cities)} 个国家")
    print(f"      范围 {out['range'][0]} ~ {out['range'][1]}")
    print(f"      → {OUT}  ({size/1024:.0f}KB)")


if __name__ == "__main__":
    main()
