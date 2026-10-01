# -*- coding: utf-8 -*-
"""
合成小程序数据包
输入：seed_history.py（历史事件库） + seed_upcoming.py（未来日历） + data/sector_daily.json（A股真实板块行情）
输出：../miniprogram/data/history/MM.json  ../miniprogram/data/upcoming.json  ../miniprogram/data/index.json
"""
import calendar
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seed_history import SEED_EVENTS, CN_DATA_CADENCE, US_DATA_CADENCE  # noqa
from seed_upcoming import UPCOMING_CONFIRMED, UPCOMING_RULES, UPCOMING_RUMORED  # noqa

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 打板/指数成分/资金标签类板块：不是真正的行业或产业主题，
# 出现在"领涨板块"里会误导，出包前统一剔除。
NOISE = ['昨日', '涨停', '跌停', '连板', '首板', '打板', '触板', '炸板', '竞价',
         '融资融券', 'GDR', 'QFII', '社保重仓', '基金重仓', '机构重仓', '券商重仓',
         'MSCI', '标普', '富时', '沪股通', '深股通', '北向', '养老金', '险资',
         '预盈预增', '预亏预减', '业绩', '扭亏', '破净', 'ST', '次新',
         '转债', '送转', '举牌', '增持', '回购', '减持', '解禁',
         '员工持股', '股权激励', '参股', '分拆', '重组', '壳资源',
         '低价股', '高价股', '大盘', '中盘', '小盘', '微盘', '上证', '深证',
         '中证', '沪深', '茅指数', '宁组合', '北交所', '科创板', '创业板综']


def is_noise(name):
    return any(kw in name for kw in NOISE)


# ============ 宏观数值（实际值 / 市场预期 / 前值 / 同比 / 环比）============
MACRO_PATH = os.path.join(HERE, "data", "macro_series.json")
MACRO = {}
if os.path.exists(MACRO_PATH):
    with open(MACRO_PATH, encoding="utf-8") as f:
        MACRO = json.load(f)

# YYYY-MM-DD -> [数据点]：某年某月某日真实发布过的数值（精确日期，不做跨年聚合）
MACRO_BY_MD = {}
# 指标 -> 最新一期有效数据，用于未来事件的「最近一期」锚点
MACRO_LATEST = {}
# 指标 -> {报告期(YYMM): 数据点}：日历行自带报告期，用它做第二套匹配
MACRO_BY_RP = {}
# 指标键 -> {n 名称, u 单位, i 重要度}：与紧凑数组配合，避免每个数据点重复存名称
INDICATORS = {k: {"n": v["n"], "u": v["u"], "i": v.get("i", 2)}
              for k, v in MACRO.items()}

# ============ B 站 UP 主观点（转写 -> 要点总结）============
# up_raw.json      : fetch_bilibili.py 产出的转写全文（体积大，不入包，仅本地存档）
# up_summary.json  : 依据转写全文提炼的要点（人工/AI 校对后写入，入包）
UP_RAW_PATH = os.path.join(HERE, "data", "up_raw.json")
UP_SUM_PATH = os.path.join(HERE, "data", "up_summary.json")
UP_RAW = {}
UP_SUM = {}
if os.path.exists(UP_RAW_PATH):
    with open(UP_RAW_PATH, encoding="utf-8") as f:
        UP_RAW = json.load(f)
if os.path.exists(UP_SUM_PATH):
    with open(UP_SUM_PATH, encoding="utf-8") as f:
        UP_SUM = json.load(f)

# ============ 财经日历（东财 RPT_CPH_FECALENDAR）============
# 密度来源：一个月 400+ 条，含具体时间、国家、报告期。
# 结构：{countries:[], names:[], days:{'YYYY-MM-DD':[[时间,国家i,名称i,重要度,类型,报告期], ...]}}
CAL_PATH = os.path.join(HERE, "data", "calendar.json")
CAL = {"countries": [], "names": [], "days": {}}
if os.path.exists(CAL_PATH):
    with open(CAL_PATH, encoding="utf-8") as f:
        CAL = json.load(f)

# 东财日历条目 -> 我的宏观指标键。
# 目的：让日历行直接带出「实际/预期/前值」，这样就不必再单独列一遍，
# 也避免同一天同一指标在「日历」和「数值」两个卡片里各出现一次。
#
# 名称要先归一化再比对：东财同一指标存在多种变体
#   「CPI：季调：当月同比」/「CPI:季调:环比」/「CPI:非:同比」/「失业率：季调」
# 所以统一剥掉 季调/非季调/当月/累计/初值/终值/折年率 并统一冒号后再匹配。
_CANON_DROP = ["季调", "非季调", "初值", "终值", "修正值", "预估值",
               "折年率", "年化", "当月", "总计", "总值", "数据", "报告"]


def _canon_cal(s):
    s = (s or "").replace("：", ":").replace("（", "(").replace("）", ")")
    for w in _CANON_DROP:
        s = s.replace(w, "")
    s = re.sub(r":+", ":", s)
    # 剥掉口径里的「非」：东财会把同一个数同时排「核心CPI:季调:当月同比」与
    # 「核心CPI:非季调:当月同比」两行，不归一化就当成两个指标各占一行。
    while ":非:" in s:
        s = s.replace(":非:", ":")
    return s.strip(": ")


CAL2MACRO = {
    ("美国", "CPI:环比"): "us_cpi",
    ("美国", "核心CPI:环比"): "us_ccpi",
    ("美国", "PPI:环比"): "us_ppi",
    ("美国", "核心PPI:环比"): "us_cppi",
    ("美国", "PCE物价指数:季调"): "us_pce_h",
    ("美国", "核心PCE物价指数:季调:环比"): "us_pce_m",
    ("美国", "工业产出指数:制造业:季调:环比"): "us_indprod_mfg",
    ("美国", "ADP就业人数(非农私营):新增就业:季调"): "us_adp",
    ("美国", "核心PCE物价指数:同比"): "us_pce",
    ("美国", "非农就业人数"): "us_nfp",
    ("美国", "失业率"): "us_unemp",
    ("美国", "ISM:PMI:制造业"): "us_ism",
    ("美国", "ISM:服务业PMI"): "us_ism_svc",
    ("美国", "工业产出指数:环比"): "us_indprod",
    ("美国", "耐用品:新增订单:环比"): "us_durable",
    ("美国", "零售销售月率"): "us_retail",
    ("美国", "贸易差额"): "us_trade",
    ("美国", "EIA原油库存:变动值"): "us_eia",
    ("美国", "成屋销售"): "us_homesale",
    ("美国", "ADP就业人数(非农私营):新增就业"): "us_adp",
    ("美国", "密歇根大学消费者信心指数"): "us_mich",
    ("美国", "GDP:不变价:环比"): "us_gdp",
    ("中国", "CPI:同比"): "cn_cpi_y",
    ("中国", "CPI:环比"): "cn_cpi",
    ("中国", "CPI:累计同比"): "cn_cpi_acc",
    ("中国", "PPI:全部工业品:同比"): "cn_ppi_y",
    ("中国", "PPI:全部工业品:累计同比"): "cn_ppi_acc",
    ("中国", "GDP:不变价:同比"): "cn_gdp",
    ("中国", "M2:同比"): "cn_m2_y",
    ("中国", "制造业PMI"): "cn_pmi_off",
    # 东财日历里中国这条的完整名是「非制造业PMI:商务活动」（统计局口径）
    ("中国", "非制造业PMI:商务活动"): "cn_pmi_nonm",
    ("中国", "非制造业PMI"): "cn_pmi_nonm",
    ("中国", "贷款市场报价利率(LPR):1年"): "cn_lpr",
    ("中国", "社会消费品零售总额:同比"): "cn_retail",
    ("中国", "社会消费品零售总额:累计同比"): "cn_retail_acc",
    ("中国", "央行外汇储备"): "cn_fxres",
    ("中国", "外汇储备"): "cn_fxres",
    ("中国", "外汇储备:值"): "cn_fxres",
    ("中国", "新增人民币贷款"): "cn_newloan",
    ("中国", "工业增加值:同比"): "cn_indprod",
    ("中国", "工业增加值:累计同比"): "cn_indprod_acc",
    ("中国", "出口金额:累计同比"): "cn_export_acc",
    ("中国", "进口金额:累计同比"): "cn_import_acc",
    # 注：cn_export / cn_import 是「以美元计算出口/进口年率」（当月同比），
    # 而东财日历里的「出口金额」不写口径、无法确认是当月还是累计，
    # 宁可不挂值，也不要把累计同比的数字挂到当月同比的行上。
    ("中国", "社会融资规模存量"): "cn_shrong",
}

# 备用映射：这些日历条目在东财当前数据里还没出现（或口径存疑不宜挂），
# 先留着映射，将来真出现了就自动生效；但**不参与**「名字对不上」的告警，
# 免得每次构建都刷一屏假警报、把真正的问题埋掉。
CAL2MACRO_SPARE = {
    ("中国", "M2:同比"), ("中国", "制造业PMI"),
    ("中国", "非制造业PMI"),
    ("中国", "社会消费品零售总额:累计同比"),
    ("中国", "外汇储备"), ("中国", "外汇储备:值"),
    ("中国", "新增人民币贷款"),
    ("美国", "零售销售月率"),
}
CAL2MACRO_N = {(_canon_cal(c), _canon_cal(n)): k for (c, n), k in CAL2MACRO.items()}

# 自动映射：东财宏观接口（fetch_macro.fetch_us_east）会把东财原始指标名存在 meta["cn"]，
# 形如「美国:CPI:季调:环比」。把它按同样的规则规范化后与日历条目名对齐，
# 就不用每加一个指标都手写一条 CAL2MACRO —— 实测 22 个美国指标里 15 个能自动对上。
CAL2MACRO_AUTO = {}
for _k, _v in MACRO.items():
    _cn = _v.get("cn")
    if not _cn:
        continue
    _p = str(_cn).replace("：", ":").split(":", 1)
    if len(_p) == 2 and _p[0].strip():
        CAL2MACRO_AUTO[(_canon_cal(_p[0]), _canon_cal(_p[1]))] = _k

# 自动映射对不上的少数几个：两家对同一指标的叫法不同
# （东财宏观叫「供应管理协会(ISM):PMI」，东财日历叫「ISM:PMI:制造业」）。
# 这些只能显式写死，键是「日历条目规范化后的名字」。
CAL2MACRO_ALIAS = {
    ("美国", "ISM:PMI:制造业"): "us_ism",
    ("美国", "ISM:服务业PMI"): "us_ism_svc",
    ("美国", "GDP:不变价:环比"): "us_gdp",
    ("美国", "成屋签约销售指数"): "us_pendsale",
    ("美国", "ADP就业人数(非农私营):新增就业"): "us_adp",
}


def _cal_key(country, name):
    """把一条日历条目映射到宏观指标键（挂上「实际/预期/前值」用）。
    东财有些行的名称自带国家前缀（如「美国EIA原油库存:变动值」），
    有些又没有（如「EIA原油库存:变动值」），统一把前缀剥掉再查表。

    查表顺序：自动映射（东财宏观名） → 显式别名 → 人工表。
    """
    cc, nn = _canon_cal(country), _canon_cal(name)
    if cc and nn.startswith(cc):
        nn = nn[len(cc):].lstrip(": ")
    return (CAL2MACRO_AUTO.get((cc, nn))
            or CAL2MACRO_ALIAS.get((cc, nn))
            or CAL2MACRO_N.get((cc, nn))
            or CAL2MACRO_N.get((cc, _canon_cal(name))))

# ============ 财经日历的过滤（中美核心数据）============
# 用户明确要求（2026-10）：
#   「抓取的重要的事件还是太杂了，我只要核心的中美发布的数据，
#     并把具体的数据值写上去。」
# 所以策略从「五大市场全收」收紧为「只收中美 + 只收核心读数」：
#   1) 主体必须是美国 / 中国（欧盟、英国、日本、韩国、中国港澳台、地方城市全部剔除）
#   2) kind=0 经济数据：必须命中核心指标，且不是「子项」
#      —— 不排子项的话，一次 ISM 会排 7 行（物价/新订单/就业/自有库存/供应商交付/产出），
#         一次非农会排 8 行，一次 EIA 会排 4 行，真正要看的主指数反而被淹没
#   3) kind=1/2 事件与动态：只留中美央行 / 最高层 / 监管的日程，
#      其余（展会、论坛、地方活动、企业发布、官员行程）一律不落库

# 只关注这两大主体的发布
CAL_KEEP_CITY = {"美国", "中国"}

# 展会/论坛/国事访问等与资本市场无关的噪音
CAL_JUNK = re.compile(
    r"博览会|展览会|展会|展销会|交易会|洽谈会|对接会|推介会|招商|研讨会|论坛|"
    r"峰会|年会|大会|发布会|新品发布|启动仪式|开幕|闭幕|挂牌仪式|"
    r"访华|访问中国|来访|出访|会见|会谈|致辞|演讲比赛|"
    r"通航|通车|竣工|开工|投产|建成|落成|"
    r"选美|赛事|锦标赛|马拉松|演唱会|电影|剧集|综艺")

# 核心读数白名单：真正影响资产定价的中美指标
CAL_CORE = re.compile(
    r"CPI|PPI|PCE|物价|"
    r"GDP|PMI|工业增加值|社会消费品零售|固定资产投资|耐用品|工业产出|工业增加值|"
    r"非农|失业率|ADP|初请|时薪|小时工资|"
    r"利率|LPR|MLF|M2|货币供应|社会融资|社融|外汇储备|"
    r"贸易差额|贸易帐|进出口|出口金额|进口金额|"
    r"消费者信心|密歇根|谘商会|"
    r"EIA原油库存|"
    r"新屋开工|成屋销售|未决房屋")

# 核心指标下的子项：主读数已单独列出，子项只会把日历刷屏。
# ⚠️ 锚点必须打准：「非农私营」不能裸写，否则会把真正要看的
#    「ADP就业人数(非农私营):新增就业」一起误杀。
CAL_SUB = re.compile(
    r"^新增非农私营就业人数|"
    r"平均每周制造业工作时间|制造业平均小时工资|"
    r"EIA(汽油|精炼油|俄克拉荷马)|"
    r"职位空缺|消费信贷|堪萨斯|地方联储|"
    # ⚠️ 必须限定在 ISM 之下：「非制造业PMI:商务活动」是**中国统计局**的官方
    #    非制造业读数（主数据），裸写会把中国这条一起误杀，实测丢了 4 行。
    r"ISM:[^:]*:商务活动")

# 美国独有的子项（中国同名指标是主读数，不能一刀切）：
#   · 出口金额/进口金额 —— 贸易差额的子项
#   · 非农就业人数 / 新增就业人数 —— 存量口径，市场看的是「新增非农就业人数」
#   · ISM 分项（物价/新订单/就业/自有库存/供应商交付/产出/库存）—— 只留主指数
CAL_US_SUB = re.compile(
    r"^出口金额|^进口金额|^新增就业人数|^非农就业人数|"
    r"^耐用品:新增订单:非|"
    r"ISM:.*:(物价|新订单|就业|自有库存|供应商交付|产出|库存)")

# 事件 / 动态：只留中美最核心的日程
CAL_EVENT_OK = re.compile(
    r"美联储|FOMC|议息|货币政策会议纪要|利率决议|"
    r"中央政治局|中央经济工作会议|政府工作报告|全国人民代表大会|"
    r"国务院常务会议|国民经济运行情况|统计局|"
    r"中国人民银行|中国央行|证监会|交易所|财政部|LPR")


def _cal_keep(country, name, kind):
    """财经日历条目是否保留。kind: 0=数据 1=事件 2=动态

    只保留美国 / 中国的条目；数据类再过一遍核心指标白名单与子项黑名单，
    事件 / 动态类只放行央行与最高层的日程。
    """
    c = (country or "").strip()
    # 东财有些条目主体写的是城市（北京市 / 法兰克福市）或没写，
    # 一律不放行 —— 用户只要「中美」，城市级/无主体的条目几乎全是活动类的噪音。
    if c not in CAL_KEEP_CITY:
        return False
    n = name or ""
    if kind in (1, 2):
        if CAL_JUNK.search(n):
            return False
        return bool(CAL_EVENT_OK.search(n))
    if CAL_SUB.search(n):
        return False
    if c == "美国" and CAL_US_SUB.search(n):
        return False
    return bool(CAL_CORE.search(n))


for key, meta_ in MACRO.items():
    pts = meta_.get("v", [])
    last_actual = None
    for pt in pts:
        if pt.get("a") is not None:
            last_actual = pt
        # 实际值与预期值都为空的点是"已排期未公布"的占位，对历史回顾无意义
        if pt.get("a") is None and pt.get("f") is None:
            continue
        # 紧凑数组 [指标键, 实际, 预期, 前值, 同比, 环比]
        # 4000+ 天 × 上万数据点，用字典存会把指标名重复几千次，直接撑爆 2MB 主包。
        # 名称与单位统一放到 INDICATORS 表，数据点只留键。
        # 先带重要度入表，排序后再压成数组（一天可能同时发布 8 项数据）。
        MACRO_BY_MD.setdefault(pt["d"], []).append(
            (meta_.get("i", 2),
             [key, pt.get("a"), pt.get("f"), pt.get("p"), pt.get("y"), pt.get("m")]))
        # 报告期索引（只收有实际值的：没有值挂上去也没意义）
        if pt.get("rp") and pt.get("a") is not None:
            MACRO_BY_RP.setdefault(key, {})[str(pt["rp"])] = \
                [key, pt.get("a"), pt.get("f"), pt.get("p"), pt.get("y"), pt.get("m")]
    # ⚠️ 语义边界：MACRO_LATEST 只作为「上次实际公布值」锚点使用。
    # 历史序列里的 f 是**当时那一期**的市场预期，不是未来某一期的预期，
    # 直接搬到未来事件上会变成「2025 年的旧预期冒充 2026 年的当期预期」，因此这里不导出 f。
    # 未来事件的真实预期值需由云函数在发布前同步，见 cloudfunctions/syncCalendar。
    if last_actual:
        MACRO_LATEST[key] = {
            "n": meta_["n"], "u": meta_["u"], "r": meta_.get("r", ""),
            "d": last_actual["d"], "a": last_actual.get("a"),
            "p": last_actual.get("p"), "y": last_actual.get("y"),
            "m": last_actual.get("m"),
        }
# 指标键 -> [(公布日, 紧凑数据点)]，按日期升序。
# 用途：日历里的公布日与数据源的公布日有时差几天（东财日历写「20:30 美国 CPI」，
# 宏观源的 PUBLISH_DATE 偶尔差 1 天；中国的统计局口径指标是按规则推算公布日，
# 实测能差 4 天）。没有这层容差，这些行就只能显示一个光秃秃的指标名。
MACRO_BY_KEY = {}
for _d, _arr in MACRO_BY_MD.items():
    for _imp, _pt in _arr:
        MACRO_BY_KEY.setdefault(_pt[0], []).append((_d, _pt))
for _k in MACRO_BY_KEY:
    MACRO_BY_KEY[_k].sort(key=lambda x: x[0])

_MACRO_TOL = 4      # 天。月度指标相隔约 30 天，±4 天不可能串到相邻一期


def macro_near(key, date, tol=_MACRO_TOL):
    """在 ±tol 天内找该指标「最靠近 date」的那个数据点，找不到返回 None。"""
    pts = MACRO_BY_KEY.get(key)
    if not pts:
        return None
    try:
        tgt = dt.date.fromisoformat(date)
    except ValueError:
        return None
    best, best_gap = None, None
    for ds, pt in pts:
        try:
            gap = abs((dt.date.fromisoformat(ds) - tgt).days)
        except ValueError:
            continue
        if gap <= tol and (best_gap is None or gap < best_gap):
            best, best_gap = pt, gap
    return best


def macro_period(key, rp):
    """按「报告期」找数据点（日历行第 6 位就是报告期，如 2608）。

    为什么需要第二套匹配：按公布日 ±4 天匹配有个天花板——FRED 只给报告期、
    没有公布日，靠 x 天偏移推算出来的公布日很容易差出 4 天以外，
    结果就是「数据其实有，但日历行挂不上去」。报告期是两边都确定的量，
    用它兜底能把这类缺口一次补上。
    """
    rp = str(rp or "").strip()
    if not rp:
        return None
    return (MACRO_BY_RP.get(key) or {}).get(rp)


OUT = os.path.join(ROOT, "miniprogram", "data")
os.makedirs(OUT, exist_ok=True)

# ⚠️ 必须是「当天」，不能写死：写死会让未来日历窗口越跑越偏
# （例如钉在 9-26，到 10 月就有一周的数据被算成「已过去」而提前消失）。
#
# ⚠️ 必须显式用东八区，不能用 date.today()：
# 本脚本两头跑 —— 本机在 CST，GitHub Actions 在 UTC。同一句 date.today() 在
# Actions 上会拿到「UTC 那天」，而定时任务实际落在北京时间凌晨 1~4 点，
# 对应 UTC 的前一天下午，于是 TODAY / generatedAt 整体差一天（时间还差 8 小时）。
# 这个项目的所有时间口径都是北京时间，所以统一按东八区算，跨机器一致。
CN_TZ = dt.timezone(dt.timedelta(hours=8))
TODAY = dt.datetime.now(CN_TZ).date()
HORIZON = 90                      # 未来三个月

CAT_IMP = {"shock": 3, "macro_us": 2, "macro_cn": 2, "macro_eu": 2,
           "macro_jp": 2, "macro_kr": 2, "tech": 2, "policy": 2, "market": 2}

# 只收录这五大资本市场的消息（用户明确要求）。GLOBAL 保留给同时冲击这五个市场的事件。
MARKET_REGIONS = {"US", "CN", "EU", "JP", "KR", "GLOBAL"}



# ============ 周期性数据窗口（保证每一天都有真实、有意义的内容）============
# ============ 未来日历规则生成 ============
def _first_friday(y, m):
    d = dt.date(y, m, 1)
    while d.weekday() != 4:
        d += dt.timedelta(days=1)
    return d


def _first_workday(y, m):
    d = dt.date(y, m, 1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def _last_workday(y, m):
    d = dt.date(y, m, calendar.monthrange(y, m)[1])
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def _clamp_weekday(y, m, day):
    """fixed_day:N → 该月 N 日；若为周末则顺延到下一个工作日"""
    last = calendar.monthrange(y, m)[1]
    d = dt.date(y, m, min(day, last))
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
        if d.month != m:          # 跨月则回退
            d -= dt.timedelta(days=3)
            break
    return d


def gen_rule_dates(rule_id, y, m):
    if rule_id == "first_friday":
        return [_first_friday(y, m)]
    if rule_id == "first_workday":
        return [_first_workday(y, m)]
    if rule_id == "mid_month":
        return [_clamp_weekday(y, m, 13)]
    if rule_id == "mid_month_plus1":
        return [_clamp_weekday(y, m, 14)]
    if rule_id == "mid_month_plus3":
        return [_clamp_weekday(y, m, 16)]
    if rule_id == "month_end":
        return [_last_workday(y, m)]
    if rule_id.startswith("fixed_day:"):
        return [_clamp_weekday(y, m, int(rule_id.split(":")[1]))]
    if rule_id.startswith("fixed:"):
        return [dt.date.fromisoformat(rule_id.split(":")[1])]
    if rule_id == "every_wednesday":
        return [dt.date(y, m, d) for d in range(1, calendar.monthrange(y, m)[1] + 1)
                if dt.date(y, m, d).weekday() == 2]
    if rule_id == "every_thursday":
        return [dt.date(y, m, d) for d in range(1, calendar.monthrange(y, m)[1] + 1)
                if dt.date(y, m, d).weekday() == 3]
    return []


# ============ 构建历史：精确日期（YYYY-MM-DD 稀疏索引）============
def build_history(sector):
    """sector: {'YYYY-MM-DD': {...}} 真实 A 股板块行情

    与旧版的关键区别：不再按 MM-DD 做跨年份聚合。
    某一年某月某日只呈现「这一天真正发生过的事」，没有就是没有。
    """
    # 板块行情本身就带精确交易日
    sector_by_ymd = {date: v for date, v in sector.items()}

    # ---- 按「精确的 YYYY-MM-DD」组织：某一年某一天真正发生了什么 ----
    # 稀疏 map：只包含至少有一项内容的日期，不再做跨年份聚合。
    days = {}
    stats = {"days": 0, "events": 0, "sector_days": 0,
             "macro_days": 0, "macro_points": 0, "up_days": 0, "up_videos": 0,
             "cal_days": 0, "cal_items": 0, "cal_linked": 0}

    def touch(ymd):
        return days.setdefault(ymd, {"e": [], "v": [], "s": None, "u": None, "c": None})

    # 1) 历史事件：MM-DD + 年份 = 精确日期
    skipped = []
    for md, year, cat, region, title, desc in SEED_EVENTS:
        # 只保留五大资本市场。种子库已按这个范围整理过，这里是兜底，
        # 免得以后往种子库里加条目时不小心又把无关内容放进来。
        if region not in MARKET_REGIONS:
            skipped.append((region, title))
            continue
        ymd = f"{year}-{md}"
        touch(ymd)["e"].append({
            "t": title, "y": year, "c": cat, "r": region, "d": desc,
            "i": CAT_IMP.get(cat, 2),
        })
    if skipped:
        print(f"[i] 事件库：已过滤 {len(skipped)} 条非五大资本市场条目"
              f"（{[r for r, _ in skipped]}）")

    # 2) 宏观数值：MACRO_BY_MD 的 key 就是精确公布日
    for ymd, pts in MACRO_BY_MD.items():
        if not pts:
            continue
        # 排序：先按重要度降序（3 高 / 2 中 / 1 低），再按有没有实际值
        pts = [p for _, p in sorted(pts, key=lambda x: (-x[0], x[1][1] is None))]
        touch(ymd)["v"] = pts
        stats["macro_points"] += len(pts)

    # 3) A 股板块：精确交易日
    for ymd, v in sector_by_ymd.items():
        up = [{"n": x["name"], "p": x["pct"]}
              for x in v["up"] if not is_noise(x["name"])]
        up = sorted(up, key=lambda x: -x["p"])[:5]        # 最涨在前
        down = [{"n": x["name"], "p": x["pct"]}
                for x in v["down"] if not is_noise(x["name"])]
        # 必须显式按涨幅升序重排：历史存量里 down 是「跌幅从小到大」存的，
        # 直接 [:5] 会把最跌的板块截掉（实测 9-28 最跌的通信 -7.36% 就被丢了）
        down = sorted(down, key=lambda x: x["p"])[:5]
        if not up and not down:
            continue
        touch(ymd)["s"] = {
            "date": ymd,
            "up": up, "down": down,
            "bt": v["breadth"]["total"], "br": v["breadth"]["rising"],
        }

    # 4) B 站 UP 主观点：按视频发布日期挂到当天
    #    只放「要点」不放全文：全文几万字会直接撑爆主包，且界面也不需要。
    for bvid, s in UP_SUM.items():
        d = s.get("d")
        if not d or not s.get("p"):
            continue
        item = {
            "k": bvid,                       # BV 号，客户端据此拼视频链接
            "t": s.get("t") or s.get("title") or "",
            "p": s["p"],
            "n": s.get("n") or "艾丽的无废话财经",
            # auto=True 表示这是 summarize_up.py 的机器摘录（还没经 AI 归纳），
            # 界面上要如实标注，避免把原文摘句当成结论
            "auto": bool(s.get("auto")),
        }
        slot = touch(d)
        if slot["u"] is None:
            slot["u"] = []
        slot["u"].append(item)

    # 5) 财经日历：并入当日全部发布项（含时间 / 国家 / 报告期）
    #    关键设计：能对上宏观指标的日历行，把指标键挂在该行（第 7 位），
    #    该指标就不再重复出现在「数值」卡片里——否则同一天同一读数会显示两遍。
    cal_countries, cal_names = CAL.get("countries", []), CAL.get("names", [])
    linked = {}          # ymd -> set(已挂到日历行的宏观键)
    stats_cal_dropped = {}   # 类型 -> 被过滤掉的条数
    for ymd, arr in (CAL.get("days") or {}).items():
        slot = touch(ymd)
        have = {p[0] for p in (slot["v"] or [])}

        # ---- 第一步：过滤 + 同一天同一指标的不同口径变体只留一条 ----
        # 东财对同一个数会排好几行：「核心CPI:季调:当月同比」和
        # 「核心CPI:非季调:当月同比」是同一个数字，全列出来只会把日历刷屏。
        # 规范化（_canon_cal 会剥掉 季调/非季调/当月/初值/…）后同名即视为同一指标，
        # 优先保留「能挂上宏观值」的那一条。
        cand = []                      # [(tm, ci, ni, im, kd, pd, sig)]
        best_sig = {}                  # sig -> 该组当前选中的候选下标
        for tm, ci, ni, im, kd, pd in arr:
            country = cal_countries[ci] if 0 <= ci < len(cal_countries) else ""
            name = cal_names[ni] if 0 <= ni < len(cal_names) else ""
            if not _cal_keep(country, name, kd):
                stats_cal_dropped[kd] = stats_cal_dropped.get(kd, 0) + 1
                continue
            idx = len(cand)
            cand.append([tm, ci, ni, im, kd, pd, None, country, name])
            if kd != 0:
                continue
            sig = (ci, _canon_cal(name))
            cand[idx][6] = sig
            cur = best_sig.get(sig)
            if cur is None:
                best_sig[sig] = idx
            elif (_cal_key(country, name) is not None
                  and _cal_key(cand[cur][7], cand[cur][8]) is None):
                best_sig[sig] = idx        # 新的这条能挂上值，换掉旧的
        drop_idx = set()
        for sig, idx in best_sig.items():
            for j, c in enumerate(cand):
                if j != idx and c[6] == sig:
                    drop_idx.add(j)
        cand = [c for j, c in enumerate(cand) if j not in drop_idx]

        # ---- 第二步：挂宏观值，并写出行数据 ----
        used = set()      # 同一天同一指标只挂第一次（如「累计同比」与「同比」并存）
        out = []
        for tm, ci, ni, im, kd, pd, _sig, country, name in cand:
            mk = _cal_key(country, name)
            # 公布日有偏差时，把最近的那一期数值补进当天的数值表再挂上去。
            # 补进去不会造成重复显示：日历行一旦带上实际值，「关键数值」卡片
            # 就会按 linked 把这个指标剔除（见 build_preview 的 dvals 过滤）。
            if mk and mk not in have:
                _pt = macro_near(mk, ymd) or macro_period(mk, pd)
                if _pt:
                    slot.setdefault("v", [])
                    slot["v"].append(list(_pt))
                    have.add(mk)
            if mk and (mk not in have or mk in used):
                mk = None                       # 该日没这个指标的数值，或已挂过
            if mk:
                used.add(mk)
                linked.setdefault(ymd, set()).add(mk)
            out.append([tm, ci, ni, im, kd, pd, mk or ""])
        slot["c"] = out

    # 注意：这里**不**把已挂值的指标从 "v" 里删掉。
    # 客户端要读 "v" 才能渲染出实际值，去重放在 UI 层做
    # （日历行已带出值的指标，「数值」卡片不再重复列）。删掉会导致日历行无值可显示。

    # 收尾：事件按重要度排序，统计
    for ymd, v in days.items():
        v["e"].sort(key=lambda e: (-e["i"], -e["y"]))
        if v["c"]:
            v["c"].sort(key=lambda x: (x[0] or "24:00", -x[3]))
            stats["cal_days"] += 1
            stats["cal_items"] += len(v["c"])
        if v["u"]:
            v["u"].sort(key=lambda x: x["k"])
            stats["up_days"] += 1
            stats["up_videos"] += len(v["u"])
        if v["e"]:
            stats["events"] += len(v["e"])
        if v["s"]:
            stats["sector_days"] += 1
        if v["v"]:
            stats["macro_days"] += 1
    stats["days"] = len(days)
    stats["cal_linked"] = sum(len(s) for s in linked.values())
    if stats_cal_dropped:
        kind_cn = {1: "事件(展会/访问等)", 2: "动态", 0: "数据"}
        detail = "、".join(f"{kind_cn.get(k, k)} {v} 条"
                           for k, v in sorted(stats_cal_dropped.items()))
        print(f"[i] 财经日历：已过滤非五大资本市场条目 —— {detail}")

    return days, stats


# ============ 构建未来日历 ============
def build_upcoming():
    end = TODAY + dt.timedelta(days=HORIZON)
    items = {}

    def add(date, cat, region, title, desc, time_, conf, imp, macro_key=None):
        if isinstance(date, str):
            date = dt.date.fromisoformat(date)
        if not (TODAY <= date <= end):
            return
        key = date.isoformat()
        val = None
        if macro_key and macro_key in MACRO_LATEST:
            m = MACRO_LATEST[macro_key]
            # 只带「上次实际公布值」，标签由 UI 明确写成"上次"，不冒充本期预期
            val = {"n": m["n"], "u": m["u"], "d": m["d"], "a": m["a"],
                   "p": m["p"], "y": m["y"], "m": m["m"]}
        items.setdefault(key, []).append({
            "t": title, "c": cat, "r": region, "d": desc,
            "tm": time_, "cf": conf, "i": imp, "v": val,
        })

    for date, cat, region, title, desc, time_, imp in UPCOMING_CONFIRMED:
        add(date, cat, region, title, desc, time_, "confirmed", imp, None)

    # 规则类事件：遍历「覆盖到的每一个月」，否则会整月漏掉
    months = []
    cur = dt.date(TODAY.year, TODAY.month, 1)
    while cur <= end:
        months.append((cur.year, cur.month))
        cur = dt.date(cur.year + (cur.month == 12), (cur.month % 12) + 1, 1)

    WEEKLY_LIMIT = 6      # 周频数据（EIA/初请）只预告未来 6 周，避免日历被刷屏
    for rid, cat, region, title, desc, time_, imp, rule, macro_key in UPCOMING_RULES:
        weekly = rule in ("every_wednesday", "every_thursday")
        seen = set()
        count = 0
        for (y, m) in months:
            for d in gen_rule_dates(rule, y, m):
                if d in seen:          # 固定日期规则会被多个月重复命中
                    continue
                seen.add(d)
                if not (TODAY <= d <= end):
                    continue
                if weekly:
                    if count >= WEEKLY_LIMIT:
                        continue
                    count += 1
                add(d, cat, region, title, desc, time_, "estimated", imp, macro_key)

    for date, cat, region, title, desc, time_, imp in UPCOMING_RUMORED:
        add(date, cat, region, title, desc, time_, "rumored", imp, None)

    out = []
    for key in sorted(items.keys()):
        arr = sorted(items[key], key=lambda x: -x["i"])
        out.append({"date": key, "items": arr})
    return out


def write_web_data(days, upcoming, meta):
    """给「云版页面」用的数据文件，放在 docs/data/ 下随 GitHub Pages 发布。

    为什么需要它：云版页面部署在 WorkBuddy 域名（云服务要求请求来自本应用域名），
    而数据仍由 GitHub Actions 每天更新到 GitHub Pages。两边不同域，
    所以云版页面不能内嵌数据，必须运行时加载。
    用 <script> 而不是 fetch：script 标签不受跨域限制，省掉 CORS 的麻烦。
    """
    d = os.path.join(ROOT, "docs", "data")
    os.makedirs(d, exist_ok=True)
    total = 0
    for name, obj in (("history", days), ("upcoming", upcoming), ("meta", meta)):
        p = os.path.join(d, name + ".js")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"window.MC_{name.upper()}=")
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
            f.write(";\n")
        total += os.path.getsize(p)
    print(f"[✓] 网页数据包：docs/data/*.js  {total/1024:.0f}KB（云版页面运行时加载）")


def compact_cal_dicts(days):
    """财经日历的两张字典表按「实际被引用」裁剪。

    源表来自全量抓取（含已被 _cal_keep 过滤掉的展会/国事访问等条目），
    过滤后 2809 个名字里只有 600+ 个真被引用，其余是纯占体积的死数据
    （小程序主包按字节计费，网页端也一样要下载）。
    做法：扫一遍真正用到的索引，重建紧凑表，再把 days 里的索引改写过去。
    """
    used_c, used_n = {}, {}
    for v in days.values():
        for row in (v.get("c") or []):
            used_c[row[1]] = used_c.get(row[1], 0) + 1
            used_n[row[2]] = used_n.get(row[2], 0) + 1
    # 按使用频次降序排：高频指标排前面，便于人工检查表头是否合理
    c_old = sorted(used_c, key=lambda x: -used_c[x])
    n_old = sorted(used_n, key=lambda x: -used_n[x])
    cmap = {old: i for i, old in enumerate(c_old)}
    nmap = {old: i for i, old in enumerate(n_old)}
    src_c, src_n = CAL.get("countries", []), CAL.get("names", [])
    countries = [src_c[o] for o in c_old if 0 <= o < len(src_c)]
    names = [src_n[o] for o in n_old if 0 <= o < len(src_n)]
    for v in days.values():
        for row in (v.get("c") or []):
            row[1] = cmap.get(row[1], 0)
            row[2] = nmap.get(row[2], 0)
    return countries, names


def main():
    sector_path = os.path.join(HERE, "data", "sector_daily.json")
    sector = {}
    if os.path.exists(sector_path):
        with open(sector_path, encoding="utf-8") as f:
            sector = json.load(f)
    print(f"[i] 载入板块行情 {len(sector)} 个交易日")

    days, stats = build_history(sector)
    stats["yearRange"] = [min(days).split("-")[0], max(days).split("-")[0]] if days else None

    # 必须在写 history.js **之前**裁剪字典表：days 里存的是表索引，
    # 若先写文件再裁剪，落盘的索引就会指向已经被裁短的新表，客户端必然越界。
    cal_countries, cal_names = compact_cal_dicts(days)
    print(f"[i] 日历字典表裁剪：国家 {len(CAL.get('countries', []))} → "
          f"{len(cal_countries)}，指标名 {len(CAL.get('names', []))} → {len(cal_names)}")

    # ⚠️ 不再往 miniprogram/data/ 写按年分片 JSON。
    # 那些文件与 history.js 内容完全重复，而代码只 require history.js，
    # 结果白占主包 869KB（上限 2048KB，一度只剩 27KB 余量）。
    # 将来真要做分包时，再单独生成到项目外的目录。

    # 小程序可直接 require 的 JS 模块（小程序不支持动态路径 require，必须静态导出）
    with open(os.path.join(OUT, "history.js"), "w", encoding="utf-8") as f:
        f.write("// 自动生成，勿手改 —— 精确到日的资本市场数据（按 YYYY-MM-DD 索引，稀疏）\n")
        f.write("module.exports = ")
        json.dump(days, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    upcoming = build_upcoming()
    # 同样只产出 .js：小程序端没有动态 require，.json 副本只会白占主包体积
    with open(os.path.join(OUT, "upcoming.js"), "w", encoding="utf-8") as f:
        f.write("// 自动生成，勿手改 —— 未来三个月事件预告\n")
        f.write("module.exports = ")
        json.dump(upcoming, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    _now = dt.datetime.now(CN_TZ)          # 北京时间，见文件上方 CN_TZ 的说明
    meta = {
        "version": _now.strftime("%Y%m%d%H%M"),
        "generatedAt": _now.strftime("%Y-%m-%d %H:%M:%S"),
        "today": TODAY.isoformat(),
        "horizonDays": HORIZON,
        "sectorRange": [min(sector.keys()), max(sector.keys())] if sector else None,
        "stats": stats,
        "indicators": INDICATORS,          # 指标键 -> {n 名称, u 单位}
        # 财经日历的两张字典表：条目只存索引，避免同一个指标名重复存几百次
        "calCountries": cal_countries,
        "calNames": cal_names,
        "cadence": {"cn": CN_DATA_CADENCE, "us": US_DATA_CADENCE},
        "upcomingCount": len(upcoming),
        "upcomingEventCount": sum(len(x["items"]) for x in upcoming),
    }
    with open(os.path.join(OUT, "meta.js"), "w", encoding="utf-8") as f:
        f.write("// 自动生成，勿手改 —— 数据元信息\nmodule.exports = ")
        json.dump(meta, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    write_web_data(days, upcoming, meta)

    total = os.path.getsize(os.path.join(OUT, "history.js"))
    yrs = stats.get("yearRange") or ["-", "-"]
    print(f"[✓] 历史：{stats['days']} 天（{yrs[0]} ~ {yrs[1]}）/ {stats['events']} 条事件 / "
          f"{stats['macro_days']} 天数值 / {stats['sector_days']} 天板块 → {total/1024:.0f}KB")
    print(f"[✓] 财经日历：{stats['cal_items']} 条 / 覆盖 {stats['cal_days']} 天 / "
          f"{len(cal_names)} 个指标名")
    print(f"[!] 日历挂上实际值：{stats['cal_linked']} 条 "
          f"（这些不再重复出现在数值卡片里）")
    # 映射校验：CAL2MACRO 里对不上的键说明名字写错了，必须显式报出来
    # （CAL2MACRO_SPARE 是明知当前日历里没有的备用映射，不算错，跳过）
    cal_pairs = set()
    for arr in (CAL.get("days") or {}).values():
        for tm, ci, ni, im, kd, pd in arr:
            if kd == 0:
                cal_pairs.add((_canon_cal(CAL["countries"][ci]),
                               _canon_cal(CAL["names"][ni])))
    bad = [k for k in CAL2MACRO_N
           if k not in cal_pairs and k not in CAL2MACRO_SPARE]
    if bad:
        print(f"[!] CAL2MACRO 有 {len(bad)} 条对不上日历名称（名字写错或该指标未收录）：")
        for c, n in bad[:12]:
            print(f"      {c} / {n}")
    miss = [k for k in CAL2MACRO_N.values() if k not in INDICATORS]
    if miss:
        print(f"[!] CAL2MACRO 指向了不存在的宏观指标键：{miss}")
    print(f"[✓] UP 主观点：{stats['up_videos']} 个视频 / 覆盖 {stats['up_days']} 天")
    # 有转写但没总结的视频要明确提示：否则会静默漏掉内容
    missing = [b for b in UP_RAW if b not in UP_SUM]
    if missing:
        print(f"[!] 以下 {len(missing)} 个视频已转写但尚未总结，"
              f"需写入 data/up_summary.json 后重建：")
        for b in missing:
            print(f"      {b}  {UP_RAW[b].get('d','')}  {str(UP_RAW[b].get('t',''))[:34]}")
    print(f"[✓] 未来：{meta['upcomingCount']} 天 / {meta['upcomingEventCount']} 条预告")
    print(f"[✓] 输出目录：{OUT}")


if __name__ == "__main__":
    main()
