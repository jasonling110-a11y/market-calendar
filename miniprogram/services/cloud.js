// services/cloud.js —— 云开发增量同步
// 设计原则：云端是「增强」不是「依赖」。未配置云环境 / 断网 / 云函数报错，
// 一律静默回退到内置离线数据包，界面不做任何阻断式提示。

const calendar = require('./calendar.js')

let syncing = false
let lastSyncAt = 0

function todayYmd() {
  const d = new Date()
  const p = (x) => (x < 10 ? '0' + x : '' + x)
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
}

/**
 * 拉取云端增量并合并到本地
 * 云函数在定时触发（每天 18:00）时会把当天数据落库，
 * 客户端这里命中 30 分钟内的快照会直接返回，不会重复抓取。
 *
 * @returns {Promise<{ok:Boolean, updatedAt:Number, fromCache:Boolean}>}
 */
function syncDelta() {
  const app = getApp()
  const none = { ok: false, updatedAt: 0, fromCache: false }
  if (!app || !app.globalData.useCloud || !app.globalData.cloudEnv) {
    return Promise.resolve(none)
  }
  if (syncing) return Promise.resolve(none)
  syncing = true

  if (!wx.cloud) {
    syncing = false
    return Promise.resolve(none)
  }

  try {
    wx.cloud.init({ env: app.globalData.cloudEnv, traceUser: true })
  } catch (e) {
    syncing = false
    return Promise.resolve(none)
  }

  return wx.cloud.callFunction({
    name: 'syncCalendar',
    // 精确日期口径下传 ymd；云函数自己会按 UTC+8 再确认一次
    data: { ymd: todayYmd(), action: 'sync' }
  }).then(function (res) {
    syncing = false
    const r = (res && res.result) || {}
    if (!r.ok) return none
    calendar.mergeDelta(r.history || null, r.upcoming || null)
    lastSyncAt = r.updatedAt || Date.now()
    return { ok: true, updatedAt: lastSyncAt, fromCache: !!r.fromCache }
  }).catch(function () {
    syncing = false
    return none
  })
}

/** 强制刷新（下拉或手动点击），跳过云端缓存 */
function forceRefresh() {
  const app = getApp()
  if (!app || !app.globalData.useCloud || !app.globalData.cloudEnv || !wx.cloud) {
    return Promise.resolve({ ok: false, updatedAt: 0, fromCache: false })
  }
  try {
    wx.cloud.init({ env: app.globalData.cloudEnv, traceUser: true })
  } catch (e) {
    return Promise.resolve({ ok: false, updatedAt: 0, fromCache: false })
  }
  return wx.cloud.callFunction({
    name: 'syncCalendar',
    data: { ymd: todayYmd(), action: 'refresh' }
  }).then(function (res) {
    const r = (res && res.result) || {}
    if (!r.ok) return { ok: false, updatedAt: 0, fromCache: false }
    calendar.mergeDelta(r.history || null, r.upcoming || null)
    lastSyncAt = r.updatedAt || Date.now()
    return { ok: true, updatedAt: lastSyncAt, fromCache: false }
  }).catch(function () {
    return { ok: false, updatedAt: 0, fromCache: false }
  })
}

function getLastSyncAt() {
  return lastSyncAt
}

module.exports = { syncDelta, forceRefresh, getLastSyncAt }
