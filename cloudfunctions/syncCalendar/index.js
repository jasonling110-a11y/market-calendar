// 云函数 syncCalendar —— 增量数据同步
// 职责：
//   1) 服务端抓取东财板块排行（当日 A 股领涨/领跌板块），避开小程序端域名白名单限制
//   2) 把结果写入云数据库集合 market_calendar，并按需返回增量给客户端
// 定时触发：每天 18:00（收盘后），配置见同目录 config.json
const cloud = require('wx-server-sdk')
const https = require('https')

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV })
const db = cloud.database()

// ---- 板块噪音黑名单：打板/指数成分/资金标签类不算真板块 ----
const NOISE = ['昨日', '涨停', '跌停', '连板', '首板', '打板', '触板', '炸板', '竞价',
  '融资融券', 'GDR', 'QFII', '社保重仓', '基金重仓', '机构重仓', '券商重仓',
  'MSCI', '标普', '富时', '沪股通', '深股通', '北向', '养老金', '险资',
  '预盈预增', '预亏预减', '业绩', '扭亏', '破净', 'ST', '次新',
  '转债', '送转', '举牌', '增持', '回购', '减持', '解禁',
  '员工持股', '股权激励', '参股', '分拆', '重组', '壳资源',
  '低价股', '高价股', '大盘', '中盘', '小盘', '微盘', '上证', '深证',
  '中证', '沪深', '茅指数', '宁组合', '北交所', '科创板', '创业板综']

function isNoise(name) {
  for (const kw of NOISE) {
    if (name.indexOf(kw) >= 0) return true
  }
  return false
}

/**
 * 清洗板块名：东财行业板块会带层级罗马数字后缀（林业Ⅱ / 林业Ⅲ 是 林业 的细分），
 * 直接展示会和一级板块重复。统一去掉后缀，再按名称去重，只留一个。
 */
function cleanSectorName(raw) {
  return String(raw == null ? '' : raw).replace(/[ⅠⅡⅢⅣⅤ]+$/, '').trim()
}

/** 零依赖 HTTPS GET（云函数可用外网） */
function getJSON(url, referer) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36',
        'Referer': referer || 'https://quote.eastmoney.com/'
      },
      timeout: 15000
    }, (res) => {
      let buf = ''
      res.on('data', (c) => { buf += c })
      res.on('end', () => {
        try { resolve(JSON.parse(buf)) } catch (e) { reject(e) }
      })
    })
    req.on('error', reject)
    req.on('timeout', () => { req.destroy(new Error('timeout')) })
  })
}

/** 抓取当日行业板块涨跌排行（东财） */
async function fetchSectorToday() {
  const fs = encodeURIComponent('m:90+t:2+f:!50')
  const url = 'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&po=1&np=1' +
    '&fltt=2&invt=2&fid=f3&fs=' + fs + '&fields=f2,f3,f12,f14'
  const d = await getJSON(url)
  const diff = (d.data && d.data.diff) || []
  const list = []
  const seen = {}
  for (const it of diff) {
    const name = cleanSectorName(it.f14)
    if (!name || isNoise(name) || seen[name]) continue   // 分级重名的只留一个
    seen[name] = true
    const pct = Number(it.f3)
    if (isNaN(pct)) continue
    list.push({ name: name, pct: pct })
  }
  list.sort((a, b) => b.pct - a.pct)

  // 边界保护：板块数少于 10 个时，简单的 slice(0,5)/slice(-5) 会让同一条
  // 同时出现在领涨和领跌里。按半数切分可保证两组不重叠。
  const n = list.length
  const upN = Math.min(5, Math.max(1, Math.floor(n / 2)))
  const downN = Math.min(5, Math.max(0, n - upN))

  return {
    up: list.slice(0, upN).map((x) => ({ n: x.name, p: x.pct })),
    down: list.slice(n - downN).reverse().map((x) => ({ n: x.name, p: x.pct })),
    bt: n,
    br: list.filter((x) => x.pct > 0).length
  }
}

// ---- 金十数据中心：经济指标（日期 / 今值 / 预测值 / 前值）----
// 这是「本期市场预期」的来源。接口公开，需带 x-app-id。
// attr_id 与 fetch_macro.py 中的序列一一对应，新增指标时两处同步补。
const JIN10_HEADERS = {
  'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/107.0.0.0 Safari/537.36',
  'x-app-id': 'rU6QIu7JHe2gOUeR',
  'x-csrf-token': 'x-csrf-token',
  'x-version': '1.0.0'
}

const JIN10_INDICATORS = [
  // key,         attr_id, 名称,                 单位,   地区, 分类,      重要度
  ['us_cpi',    '9',  '美国 CPI 月率',      '%',     'US', 'macro_us', 3],
  ['us_ccpi',   '6',  '美国核心 CPI 月率',  '%',     'US', 'macro_us', 3],
  ['us_nfp',    '33', '美国非农就业人数',   '万人',  'US', 'macro_us', 3],
  ['us_unemp',  '47', '美国失业率',         '%',     'US', 'macro_us', 3],
  ['us_ism',    '28', '美国 ISM 制造业 PMI', '',     'US', 'macro_us', 2],
  ['us_gdp',    '53', '美国 GDP',           '%',     'US', 'macro_us', 3],
  ['us_ppi',    '37', '美国 PPI 月率',      '%',     'US', 'macro_us', 2],
  ['us_cppi',   '7',  '美国核心 PPI 月率',  '%',     'US', 'macro_us', 2],
  ['us_retail', '39', '美国零售销售月率',   '%',     'US', 'macro_us', 2],
  ['us_pce',    '80', '美国核心 PCE',       '%',     'US', 'macro_us', 3],
  ['us_claims', '44', '美国初请失业金人数', '万人',  'US', 'macro_us', 1],
  ['cn_cpi',    '72', '中国 CPI 月率',      '%',     'CN', 'macro_cn', 3],
  ['cn_ppi_y',  '60', '中国 PPI 年率',      '%',     'CN', 'macro_cn', 3],
  ['cn_gdp',    '57', '中国 GDP 年率',      '%',     'CN', 'macro_cn', 3],
  ['cn_trade',  '61', '中国贸易帐',         '亿美元', 'CN', 'macro_cn', 2]
]

/** 拉取单个指标的 [日期, 今值, 预测值, 前值] 序列 */
function fetchJin10(attrId) {
  const url = 'https://datacenter-api.jin10.com/reports/list_v2' +
    `?max_date=&category=ec&attr_id=${attrId}&_=${Date.now()}`
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: JIN10_HEADERS, timeout: 15000 }, (res) => {
      let buf = ''
      res.on('data', (c) => { buf += c })
      res.on('end', () => {
        try {
          const j = JSON.parse(buf)
          const values = (j.data && j.data.values) || []
          resolve(values.map((v) => ({
            date: v[0], actual: v[1], forecast: v[2], prev: v[3]
          })))
        } catch (e) { reject(e) }
      })
    })
    req.on('error', reject)
    req.on('timeout', () => { req.destroy(new Error('jin10 timeout')) })
  })
}

/**
 * 抓取各指标排期，产出：
 *   upcoming —— 未来每一期，只要数据源给了预测值就带上（这才是真正的「市场预期」）
 *   history  —— 已公布期次的真实数值，按 MM-DD 归档回填
 */
async function fetchMacroCalendar(todayStr) {
  const upcoming = {}
  const history = {}
  const errors = []

  for (const [key, attr, name, unit, region, cat, imp] of JIN10_INDICATORS) {
    let rows
    try {
      rows = await fetchJin10(attr)
    } catch (e) {
      errors.push(`${key}: ${e.message || e}`)
      continue
    }
    let lastActual = null
    for (const r of rows) {
      if (!r.date) continue
      if (r.date < todayStr && r.actual !== null && r.actual !== undefined) {
        if (!lastActual || r.date > lastActual.date) lastActual = r
        // 回填历史：按精确公布日归档，同一天多个指标各自保留
        history[r.date] = history[r.date] || { e: [], v: [], s: null }
        history[r.date].v.push([key, r.actual, r.forecast, r.prev, null, null])
        continue
      }
      // 未来排期：只有数据源明确给了预测值才写入，绝不拿历史值冒充
      if (r.date >= todayStr && r.forecast !== null && r.forecast !== undefined) {
        const anchor = lastActual ? {
          n: name, u: unit, d: lastActual.date, a: lastActual.actual, p: lastActual.prev
        } : null
        ;(upcoming[r.date] = upcoming[r.date] || []).push({
          t: name, c: cat, r: region,
          d: `${name}：市场预期 ${r.forecast}${unit}${r.prev !== null && r.prev !== undefined ? `，前值 ${r.prev}${unit}` : ''}。`,
          tm: '待定', cf: 'confirmed', i: imp,
          v: { n: name, u: unit, d: anchor ? anchor.d : '', a: anchor ? anchor.a : null,
               p: r.prev, f: r.forecast, y: null, m: null }
        })
      }
    }
  }
  return { upcoming, history, errors }
}

// ---- 财经日历：东方财富 RPT_CPH_FECALENDAR ----
// 为什么需要它：主包里的日历是「发布那一刻」的快照，而东财会持续新增排期
// （央行讲话、发布会时间确认、临时安排）。云函数每天补齐近端日历，
// 这样「上线后日历自动更新」才成立，不必重新提审。
//
// 注意：这里的筛选规则是本地的精简副本（云函数零依赖、不共享文件）。
// 权威版本在 tools/fetch_calendar.py，改那边时要同步这里。
const CAL_CITY = ['美国', '中国', '中国香港', '欧盟', '欧元区', '日本', '英国',
  '德国', '法国', '意大利', '加拿大', '澳大利亚', '韩国', '新加坡', '瑞士',
  '俄罗斯', 'OPEC', '中国台湾', '西班牙', '荷兰', '印度', '巴西', '墨西哥']
const CAL_KW3 = ['CPI', 'PPI', 'PCE', 'GDP', 'PMI', '非农', '失业率', '利率决议',
  'M2', '货币供应', '社融', '社会融资', '新增信贷', 'LPR', 'MLF',
  '工业增加值', '社会消费品零售', '固定资产投资', '进出口', '贸易帐',
  '贸易差额', '外汇储备', '房价', '工业企业利润']
const CAL_KW2 = ['ISM', '初请', 'ADP', '耐用品', '工业产出', '新屋', '成屋', '营建',
  '产能利用率', '零售销售', '消费者信心', '景气', '职位空缺', '时薪',
  '制造业', '服务业', '综合', '经济展望', '就业', '工业订单',
  'EIA原油库存', 'EIA汽油库存', 'EIA精炼油库存', '库欣原油库存',
  '出口', '进口', '利率', '汇率', '收入', '支出', '信贷', '贷款', '存款']
const CAL_DROP = ['新股申购', '新股上市', '限售解禁', '分红', '送转', '股东大会',
  '增持', '减持', '回购', '股权激励', '停牌', '复牌',
  '人口数', '现价', '折年数', '期末汇率', '人民币汇率', '战略储备', '预测年度']
const CAL_EVENT3 = ['美联储议息会议', '欧洲央行议息会议', '日本央行议息会议',
  '英国央行议息会议', '国民经济运行情况发布会', '中国共产党中央全会',
  '中央经济工作会议', '政府工作报告', '全国人民代表大会', '政治局会议',
  '瑞士央行议息会议', '加拿大央行议息会议', '澳洲联储议息会议', '新西兰联储议息会议']
const CAL_LOW = ['展览会', '博览会', '展会', '交易会', '糖酒会', '车展',
  '高峰论坛', '交流会议', '研讨会', '大会', '论坛']

// 东财日历条目 -> 宏观指标键（让日历行能直接带出实际值）。
// 权威版本在 tools/build_dataset.py 的 CAL2MACRO，改那边时要同步。
const CAL2MACRO = {
  '美国|CPI:环比': 'us_cpi',
  '美国|核心CPI:环比': 'us_ccpi',
  '美国|PPI:环比': 'us_ppi',
  '美国|非农就业人数': 'us_nfp',
  '美国|失业率': 'us_unemp',
  '美国|ISM:PMI:制造业': 'us_ism',
  '美国|ISM:服务业PMI': 'us_ism_svc',
  '美国|零售销售月率': 'us_retail',
  '美国|EIA原油库存:变动值': 'us_eia',
  '中国|CPI:同比': 'cn_cpi_y',
  '中国|CPI:环比': 'cn_cpi',
  '中国|PPI:全部工业品:同比': 'cn_ppi_y',
  '中国|GDP:不变价:同比': 'cn_gdp',
  '中国|M2:同比': 'cn_m2_y',
  '中国|制造业PMI': 'cn_pmi_off',
  '中国|非制造业PMI': 'cn_pmi_nonm',
  '中国|贷款市场报价利率(LPR):1年': 'cn_lpr',
  '中国|外汇储备': 'cn_fxres',
  '中国|工业增加值:同比': 'cn_indprod'
}

function calCanon(s) {
  let v = String(s || '').replace(/：/g, ':').replace(/（/g, '(').replace(/）/g, ')')
  ;['季调', '非季调', '初值', '终值', '修正值', '预估值', '折年率', '年化',
    '当月', '总计', '总值', '数据', '报告'].forEach((w) => { v = v.split(w).join('') })
  return v.replace(/:+/g, ':').replace(/^:|:$/g, '').trim()
}

function fetchEastCalendar(dateStr) {
  // 只取近端：往前 7 天（补当天已发生但主包快照里缺的）+ 往后 21 天（新排期）
  const base = new Date(dateStr + 'T00:00:00Z')
  const from = new Date(base.getTime() - 7 * 86400000).toISOString().slice(0, 10)
  const to = new Date(base.getTime() + 22 * 86400000).toISOString().slice(0, 10)
  const flt = encodeURIComponent(
    "(START_DATE>='" + from + "')(START_DATE<'" + to + "')")
  const url = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
    + '?reportName=RPT_CPH_FECALENDAR'
    + '&columns=START_DATE,FE_NAME,FE_TYPE,STD_TYPE_CODE,CITY'
    + '&pageSize=500&pageNumber=1&sortColumns=START_DATE&sortTypes=1'
    + '&filter=' + flt

  return getJSON(url, 'https://data.eastmoney.com/').then((d) => {
    const out = {}
    const rows = ((d && d.result && d.result.data) || [])
    for (const r of rows) {
      const name = String(r.FE_NAME || '').replace(/\[同传\]|（同传）|\(同传\)/g, '').trim()
      if (!name || name.length > 40) continue
      if (CAL_DROP.some((k) => name.indexOf(k) >= 0)) continue
      if (/:值$/.test(name)) continue
      const city = r.CITY || ''
      const ftype = r.FE_TYPE || ''
      const std = String(r.STD_TYPE_CODE || '')
      const dd = String(r.START_DATE || '')
      const ymd = dd.slice(0, 10)
      const tm = dd.slice(11, 16)
      const low = CAL_LOW.some((k) => name.indexOf(k) >= 0)

      let imp, kind, baseName = name, period = ''
      const pm = name.match(/^(.*?)\s*[（(]报告期[:：]([^）)]*)[)）]\s*$/)
      if (pm) {
        baseName = pm[1].trim()
        const ym = pm[2].match(/(\d{4})\s*年\s*(\d{1,2})\s*月/)
        if (ym) period = ym[1].slice(2) + String(ym[2]).padStart(2, '0')
      }

      if (ftype && ftype !== '经济数据') {
        imp = CAL_EVENT3.indexOf(ftype) >= 0 ? 3 : (low ? 1 : 2)
        kind = 1
      } else if (std === '1' || std === '3') {
        imp = low ? 1 : 2; kind = 1
      } else if (!ftype) {
        imp = 1; kind = 2                       // 央行动态 / 报告 / 持仓
      } else {
        if (CAL_CITY.indexOf(city) < 0) continue
        if (CAL_KW3.some((k) => baseName.indexOf(k) >= 0)) imp = 3
        else if (CAL_KW2.some((k) => baseName.indexOf(k) >= 0)) imp = 2
        else continue
        kind = 0
        // 剥国家前缀：「美国:CPI」和「美国EIA原油库存」都要处理，
        // 否则界面会出现「美国 美国EIA原油库存」这种重复。与本地规则一致。
        if (city && baseName.indexOf(city + ':') === 0) {
          baseName = baseName.slice(city.length + 1)
        } else if (city && baseName.indexOf(city) === 0 && baseName.length > city.length) {
          const nx = baseName.charAt(city.length)
          if (/[0-9A-Za-z._-]/.test(nx)) baseName = baseName.slice(city.length)
        }
        // 报告期与发布日差太远的丢掉（东财偶有远期口径）
        if (period) {
          const py = 2000 + Number(period.slice(0, 2))
          const pmo = Number(period.slice(2))
          const ey = Number(ymd.slice(0, 4)), emo = Number(ymd.slice(5, 7))
          const gap = (ey * 12 + emo) - (py * 12 + pmo)
          if (gap < 0 || gap > 4) period = ''
        }
      }

      const mk = kind === 0
        ? (CAL2MACRO[city + '|' + calCanon(baseName)] || '')
        : ''
      ;(out[ymd] = out[ymd] || []).push([tm, city, baseName, imp, kind, period, mk])
    }
    // 与本地管线保持一致的去重：同一天同一基础指标排了多行时，
    // 丢掉没有口径的「裸名」（如「核心CPI」），避免同一天出现两条 CPI
    for (const k in out) {
      const rows = out[k]
      const kouOf = (n) => {
        const c = calCanon(n)
        if (/同比$/.test(c)) return '同比'
        if (/环比$/.test(c)) return '环比'
        return ''
      }
      const baseOf = (n) => {
        const c = calCanon(n); const ko = kouOf(n)
        return ko ? c.slice(0, -2).replace(/:$/, '') : c
      }
      const groups = {}
      rows.forEach((e, idx) => {
        if (e[4] !== 0) return
        const key = e[1] + '|' + baseOf(e[2])
        ;(groups[key] = groups[key] || []).push({ idx, ko: kouOf(e[2]) })
      })
      const drop = {}
      for (const key in groups) {
        const g = groups[key]
        if (g.length <= 1) continue
        if (g.some((x) => x.ko)) g.forEach((x) => { if (!x.ko) drop[x.idx] = 1 })
      }
      const seen = {}
      out[k] = rows.filter((e, idx) => {
        if (drop[idx]) return false
        if (e[4] === 0) {
          const sig = e[1] + '|' + baseOf(e[2]) + '|' + kouOf(e[2])
          if (seen[sig]) return false
          seen[sig] = 1
        }
        return true
      })
      out[k].sort((a, b) => (a[0] < b[0] ? -1 : 1))
    }
    return out
  }).catch(() => ({}))
}

// ---- 每日快照：抓取结果必须落库，否则定时触发等于白跑 ----
// 之前的实现把抓取结果只放进返回值，而定时触发的返回值没人接收，
// 客户端后续 pull 读的是空集合，永远拿不到当天数据。这是"每日更新"失效的根因。

const DAILY_COL = 'market_daily'
const FRESH_MS = 30 * 60 * 1000        // 快照 30 分钟内视为新鲜，直接复用

function todayStr() {
  return new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 10)
}

async function loadSnapshot(date) {
  try {
    const r = await db.collection(DAILY_COL).where({ date }).limit(1).get()
    return (r.data && r.data[0]) || null
  } catch (e) {
    return null               // 集合未建时返回空，主流程继续
  }
}

async function saveSnapshot(date, snap) {
  try {
    const col = db.collection(DAILY_COL)
    const data = Object.assign({}, snap, {
      date, updatedAt: Date.now(), _updated: db.serverDate()
    })
    const exist = await col.where({ date }).limit(1).get()
    if (exist.data && exist.data.length) {
      await col.doc(exist.data[0]._id).update({ data })
    } else {
      await col.add({ data })
    }
    return true
  } catch (e) {
    return false
  }
}

/** 抓一份完整的当日数据 */
async function buildSnapshot(date) {
  const snap = { sector: null, history: {}, upcoming: {}, errors: [] }

  // 1) 当日 A 股板块
  try {
    const s = await fetchSectorToday()
    snap.sector = { date, ...s }
    // 历史归档按日期 upsert，避免每天 add 出重复记录
    try {
      const col = db.collection('market_sector')
      const exist = await col.where({ date }).limit(1).get()
      const row = { date, ...s, _updated: db.serverDate() }
      if (exist.data && exist.data.length) await col.doc(exist.data[0]._id).update({ data: row })
      else await col.add({ data: row })
    } catch (e) { /* 集合不存在不影响主流程 */ }
  } catch (e) {
    snap.errors.push('sector: ' + String(e && e.message || e))
  }

  // 2) 宏观数值 + 本期市场预期（金十）
  try {
    const mc = await fetchMacroCalendar(date)
    snap.upcoming = mc.upcoming || {}
    snap.history = mc.history || {}
    snap.errors = snap.errors.concat(mc.errors || [])
  } catch (e) {
    snap.errors.push('macro: ' + String(e && e.message || e))
  }

  // 3) 中国宏观数据（东财，数据源实时）
  try {
    const cn = await fetchCnMacro(date)
    Object.keys(cn.history).forEach((k) => {
      const cur = snap.history[k] || { e: [], v: [], s: null }
      // 同一天可能有多个指标，按指标键去重后合并
      const seen = {}
      const merged = []
      cn.history[k].v.concat(cur.v || []).forEach((x) => {
        if (!seen[x[0]]) { seen[x[0]] = 1; merged.push(x) }
      })
      snap.history[k] = { e: cur.e || [], v: merged, s: cur.s || null }
    })
    snap.errors = snap.errors.concat(cn.errors)
  } catch (e) {
    snap.errors.push('cnmacro: ' + String(e && e.message || e))
  }

  // 4) 财经日历（近端补齐：主包快照之后新排期的事件）
  try {
    const cal = await fetchEastCalendar(date)
    Object.keys(cal).forEach((k) => {
      const cur = snap.history[k] || { e: [], v: [], s: null }
      // 与主包日历按「时间|国家|名称」去重，云端条目优先
      const old = cur.c || []
      const seen = {}
      cal[k].forEach((x) => { seen[x[0] + '|' + x[1] + '|' + x[2]] = 1 })
      const merged = cal[k].concat(
        old.filter((x) => !seen[x[0] + '|' + x[1] + '|' + x[2]]))
      snap.history[k] = { e: cur.e || [], v: cur.v || [], s: cur.s || null, c: merged }
    })
    snap.errors = (snap.errors || []).concat(cal.errors || [])
  } catch (e) {
    snap.errors.push('calendar: ' + String(e && e.message || e))
  }

  // 5) 人工维护 / 外部写入的预告（优先级最高，覆盖抓取结果）
  try {
    const res = await db.collection('market_upcoming')
      .where({ date: db.command.gte(date) })
      .orderBy('date', 'asc')
      .limit(200)
      .get()
    for (const row of (res.data || [])) {
      const k = row.date
      ;(snap.upcoming[k] = snap.upcoming[k] || []).push({
        t: row.title, c: row.category, r: row.region,
        d: row.desc, tm: row.time || '待定',
        cf: row.conf || 'estimated', i: row.imp || 2
      })
    }
  } catch (e) { /* 集合不存在忽略 */ }

  return snap
}

// ---- 中国宏观数据：东财数据中心（数据源实时，可真正每日更新）----
// 与金十的区别：金十的经济日历数据只更新到 2025-09（滞后一年），
// 而东财这个接口的 CPI/PPI/PMI 都是当月最新的，所以中国部分走这条路。
// 注意：东财没有美国宏观数据报表，美国数据仍受限。
const CN_MACRO = [
  { rep: 'RPT_ECONOMY_CPI', key: 'cn_cpi_y', field: 'NATIONAL_SAME', rule: 'next9' },
  { rep: 'RPT_ECONOMY_PPI', key: 'cn_ppi_y', field: 'BASE_SAME', rule: 'next9' },
  { rep: 'RPT_ECONOMY_PMI', key: 'cn_pmi_off', field: 'MAKE_INDEX', rule: 'monthend' }
]

/** 公布日推算：数据所属月份 -> 实际公布日期 */
function pubDate(y, m, rule) {
  const p = (x) => (x < 10 ? '0' + x : '' + x)
  if (rule === 'monthend') {
    return `${y}-${p(m)}-${new Date(y, m, 0).getDate()}`
  }
  // next9：次月 9 日（统计局物价数据发布窗口）
  const ny = m === 12 ? y + 1 : y
  const nm = m === 12 ? 1 : m + 1
  return `${ny}-${p(nm)}-09`
}

async function fetchCnMacro(todayStr) {
  const history = {}
  const errors = []
  for (const cfg of CN_MACRO) {
    try {
      const url = 'https://datacenter-web.eastmoney.com/api/data/v1/get' +
        `?reportName=${cfg.rep}&columns=ALL&pageSize=24` +
        '&sortColumns=REPORT_DATE&sortTypes=-1'
      const d = await getJSON(url)
      const rows = (d.result && d.result.data) || []
      for (const r of rows) {
        const a = Number(r[cfg.field])
        if (!isFinite(a)) continue
        const rd = String(r.REPORT_DATE || '').slice(0, 10)      // YYYY-MM-01
        const y = +rd.slice(0, 4)
        const m = +rd.slice(5, 7)
        if (!y || !m) continue
        const pub = pubDate(y, m, cfg.rule)
        if (pub >= todayStr) continue                            // 只回填已公布的
        history[pub] = history[pub] || { e: [], v: [], s: null }
        // 紧凑数组 [指标键, 实际, 预期, 前值, 同比, 环比]
        history[pub].v.push([cfg.key, a, null, null, a, null])
      }
    } catch (e) {
      errors.push(`${cfg.key}: ${e.message || e}`)
    }
  }
  return { history, errors }
}

exports.main = async (event = {}) => {
  const date = todayStr()

  // 定时触发（Type=Timer）或显式 refresh 时强制重抓；客户端普通调用命中新鲜缓存直接返回
  const isTimer = event.Type === 'Timer' || !!event.TriggerName
  const force = isTimer || event.action === 'refresh' || event.action === 'cron'

  let snap = force ? null : await loadSnapshot(date)
  let fromCache = false
  if (snap && (Date.now() - (snap.updatedAt || 0)) < FRESH_MS) {
    fromCache = true
  } else {
    snap = await buildSnapshot(date)
    await saveSnapshot(date, snap)
  }

  // 组装返回：把当日板块并入 history（按精确日期，不跨年聚合）
  const history = Object.assign({}, snap.history || {})
  if (snap.sector && snap.sector.up && snap.sector.up.length) {
    const d = snap.sector.date || date
    history[d] = Object.assign({ e: [], v: [] }, history[d], { s: snap.sector })
  }

  return {
    ok: true,
    date,
    fromCache,
    updatedAt: snap.updatedAt || Date.now(),
    sector: snap.sector || null,
    history,
    upcoming: snap.upcoming || {},
    errors: snap.errors || []
  }
}
