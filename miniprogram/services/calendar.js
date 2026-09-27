// services/calendar.js —— 日历数据服务
// 数据分三层：内置离线包（基线） → 本地缓存（上次云端增量） → 云开发（联网增量）
// 任一层缺失都不影响可用性，永远优先保证「打开就能看」。
//
// 索引口径：**精确到 YYYY-MM-DD**。某年某月某日只呈现这一天真正发生过的事，
// 不做跨年份聚合（不再有"历史上的今天"这种把不同年份混在一起的展示）。

const HISTORY = require('../data/history.js')
const UPCOMING = require('../data/upcoming.js')
const META = require('../data/meta.js')
const dateUtil = require('../utils/date.js')

const CACHE_KEY_HIST = 'mc_delta_history_v1'
const CACHE_KEY_UP = 'mc_delta_upcoming_v1'

// 指标键 -> {n 名称, u 单位}
const INDICATORS = META.indicators || {}

// 财经日历的两张字典表（条目只存索引，避免同一指标名重复存几百次）
const CAL_COUNTRIES = META.calCountries || []
const CAL_NAMES = META.calNames || []

// 云端增量合并进来的数据
let deltaHistory = null    // { 'YYYY-MM-DD': { e:[], v:[], s:{} } }
let deltaUpcoming = null   // { 'YYYY-MM-DD': [items] }
let loaded = false

/** 读一次本地缓存（只做一次，避免每次 setData 都读 storage） */
function ensureLoaded() {
  if (loaded) return
  loaded = true
  try {
    const h = wx.getStorageSync(CACHE_KEY_HIST)
    if (h && typeof h === 'object') deltaHistory = h
    const u = wx.getStorageSync(CACHE_KEY_UP)
    if (u && typeof u === 'object') deltaUpcoming = u
  } catch (e) {
    // 存储不可用（如游客模式）时静默降级为纯离线包
  }
}

/**
 * 把紧凑数组 [指标键, 实际, 预期, 前值, 同比, 环比] 展开成展示用对象。
 * 存成数组是为了压体积——字典形式会把指标名重复存几千次，直接撑爆 2MB 主包。
 */
function expandValues(arr) {
  if (!arr || !arr.length) return []
  return arr.map(function (x) {
    const meta = INDICATORS[x[0]] || { n: x[0], u: '', i: 2 }
    return {
      k: x[0], n: meta.n, u: meta.u, i: meta.i || 2,
      a: x[1], f: x[2], p: x[3], y: x[4], m: x[5]
    }
  })
}

/**
 * 把一条「财经日历」记录展开成展示用对象。
 *
 * 两种形态都要支持，因为两个数据源格式不同：
 *   主包（紧凑数组，省体积）：[时间, 国家索引, 名称索引, 重要度, 类型, 报告期, 指标键]
 *   云端增量（直接给字符串，不必同步索引表）：{tm, co, n, i, k, pd, mk}
 * 类型：0 经济数据 / 1 事件 / 2 动态（央行讲话、报告、持仓等）
 *
 * 指标键（mk）是设计关键：这一天若确实收录了该指标的实际值，
 * 就直接显示在日历行下方，不必再去「关键数值」卡片里找，
 * 同时该指标会从「关键数值」卡片里剔除，避免同一读数出现两遍。
 */
function toCalItem(x, valByKey) {
  const isArr = Object.prototype.toString.call(x) === '[object Array]'
  const C = CAL_COUNTRIES || []
  const N = CAL_NAMES || []
  const mk = (isArr ? x[6] : x.mk) || ''
  const v = mk ? valByKey[mk] : null
  return {
    tm: (isArr ? x[0] : x.tm) || '',
    co: (isArr ? (C[x[1]] || '') : (x.co || '')),
    n: (isArr ? (N[x[2]] || '') : (x.n || '')),
    i: (isArr ? x[3] : x.i) || 1,
    k: (isArr ? x[4] : x.k) || 0,
    pd: (isArr ? x[5] : x.pd) || '',
    mk: mk,
    a: v ? v.a : null,
    f: v ? v.f : null,
    p: v ? v.p : null,
    u: v ? v.u : ''
  }
}

function calSig(x) { return x.tm + '|' + x.co + '|' + x.n }

/**
 * 取某一天的内容
 * @param {String} ymd 'YYYY-MM-DD'
 * @returns {{e:Array, v:Array, s:Object|null, u:Array, c:Array}}
 */
function getHistoryByYmd(ymd) {
  ensureLoaded()
  const base = HISTORY[ymd] || { e: [], v: [], s: null }
  const delta = deltaHistory && deltaHistory[ymd]
  let vals, sector, ups, cal

  if (!delta) {
    vals = expandValues(base.v)
    sector = base.s || null
    ups = base.u || []
    cal = base.c || []
  } else {
    // 云端数值与本地包按指标键去重合并，云端优先
    vals = expandValues(base.v)
    if (delta.v && delta.v.length) {
      const seen = {}
      expandValues(delta.v).forEach(function (x) { seen[x.k] = x })
      vals.forEach(function (x) { if (!seen[x.k]) seen[x.k] = x })
      vals = Object.keys(seen).map(function (k) { return seen[k] })
    }
    sector = delta.s || base.s || null
    ups = base.u || []
    cal = base.c || []
  }

  // 日历行要挂实际值，先建「指标键 -> 值」索引
  const valByKey = {}
  vals.forEach(function (x) { valByKey[x.k] = x })

  // 主包日历 + 云端增量日历：按「时间|国家|名称」去重，云端优先
  // （云函数每天补齐近端新排期的事件，主包只带发布那一刻的快照）
  let calList = (cal || []).map(function (x) { return toCalItem(x, valByKey) })
  const dCal = delta && delta.c
  if (dCal && dCal.length) {
    const seen = {}
    dCal.forEach(function (x) { seen[calSig(toCalItem(x, {}))] = 1 })
    calList = dCal.map(function (x) { return toCalItem(x, valByKey) })
      .concat(calList.filter(function (x) { return !seen[calSig(x)] }))
    calList.sort(function (a, b) {
      if (a.tm === b.tm) return b.i - a.i
      return a.tm < b.tm ? -1 : 1
    })
  }

  return {
    e: (base.e || []).concat(delta ? (delta.e || []) : []),
    v: vals,
    s: sector,
    u: ups,
    c: calList
  }
}

/**
 * 取某一天的未来预告
 * @param {String} ymd 'YYYY-MM-DD'
 */
function getUpcomingByYmd(ymd) {
  ensureLoaded()
  const items = (upcomingMap()[ymd] || []).slice()
  if (deltaUpcoming && deltaUpcoming[ymd]) {
    return items.concat(deltaUpcoming[ymd])
  }
  return items
}

let _upMap = null
function upcomingMap() {
  if (_upMap) return _upMap
  _upMap = {}
  UPCOMING.forEach(function (d) { _upMap[d.date] = d.items })
  if (deltaUpcoming) {
    Object.keys(deltaUpcoming).forEach(function (k) {
      _upMap[k] = (_upMap[k] || []).concat(deltaUpcoming[k])
    })
  }
  return _upMap
}

/** 未来预告全量（按日期升序），fromYmd 之后的日子 */
function getUpcomingList(fromYmd, limit) {
  ensureLoaded()
  const map = upcomingMap()
  const out = []
  Object.keys(map).sort().forEach(function (k) {
    if (k < fromYmd) return
    out.push({ date: k, items: map[k] })
  })
  return limit ? out.slice(0, limit) : out
}

/** 某月有哪些天存在预告（用于日历打点） */
function upcomingDaysInMonth(y, m) {
  ensureLoaded()
  const map = upcomingMap()
  const prefix = y + '-' + dateUtil.pad(m) + '-'
  const set = {}
  Object.keys(map).forEach(function (k) {
    if (k.indexOf(prefix) === 0) set[k] = true
  })
  return set
}

/** 某月哪些天有历史内容（用于日历打点） */
function historyDaysInMonth(y, m) {
  ensureLoaded()
  const prefix = y + '-' + dateUtil.pad(m) + '-'
  const set = {}
  Object.keys(HISTORY).forEach(function (k) {
    if (k.indexOf(prefix) === 0) set[k] = true
  })
  if (deltaHistory) {
    Object.keys(deltaHistory).forEach(function (k) {
      if (k.indexOf(prefix) === 0) set[k] = true
    })
  }
  return set
}

/**
 * 判断某月是否完全落在数据覆盖范围之外。
 * 用于给"翻到没有数据的月份"一个明确提示，而不是让用户以为漏了什么。
 */
function monthHasAnyData(y, m) {
  ensureLoaded()
  const prefix = y + '-' + dateUtil.pad(m) + '-'
  for (const k in HISTORY) {
    if (k.indexOf(prefix) === 0) return true
  }
  return false
}

/** 合并云端增量并落缓存 */
function mergeDelta(historyDelta, upcomingDelta) {
  ensureLoaded()
  if (historyDelta && typeof historyDelta === 'object') {
    deltaHistory = Object.assign({}, deltaHistory || {}, historyDelta)
    try { wx.setStorageSync(CACHE_KEY_HIST, deltaHistory) } catch (e) {}
  }
  if (upcomingDelta && typeof upcomingDelta === 'object') {
    deltaUpcoming = Object.assign({}, deltaUpcoming || {}, upcomingDelta)
    _upMap = null
    try { wx.setStorageSync(CACHE_KEY_UP, deltaUpcoming) } catch (e) {}
  }
}

function getMeta() {
  return META
}

module.exports = {
  getHistoryByYmd,
  getUpcomingByYmd,
  getUpcomingList,
  upcomingDaysInMonth,
  historyDaysInMonth,
  monthHasAnyData,
  mergeDelta,
  getMeta
}
