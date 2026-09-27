// services/notes.js —— 我的笔记（某一天的个人思考）
//
// 设计原则：
//   1. 本地优先 —— 写入立刻落 storage，断网、未配云环境都能用，绝不丢字。
//   2. 云端只做同步 —— 联网后静默双向同步，冲突按 updatedAt 取新（后写胜出）。
//   3. 隐私 —— 云函数按 openid 隔离，只能读自己的笔记；未开云环境则完全不出设备。
//
// 数据结构：
//   { id, date:'YYYY-MM-DD', text, tags:[], createdAt, updatedAt, synced }

const KEY = 'mc_notes_v1'
const cloudSvc = require('./cloud.js')

let notes = null          // { id: note }
let syncing = false

/** 标签预设：交易场景下最常用的四类，也可不选 */
const TAGS = ['复盘', '计划', '观察', '灵感']

function ensure() {
  if (notes) return
  try {
    notes = wx.getStorageSync(KEY) || {}
  } catch (e) {
    notes = {}            // 存储不可用（游客模式）时退化为内存态
  }
}

function persist() {
  try {
    wx.setStorageSync(KEY, notes)
  } catch (e) {
    // 写失败不阻断交互，下次启动会重试
  }
}

function genId() {
  return 'n' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6)
}

/** 某一天的笔记（按创建时间正序） */
function listByDate(ymd) {
  ensure()
  return Object.keys(notes)
    .map((k) => notes[k])
    .filter((n) => n.date === ymd)
    .sort((a, b) => a.createdAt - b.createdAt)
}

/** 全部笔记（按日期倒序，同日按创建倒序） */
function listAll() {
  ensure()
  return Object.keys(notes)
    .map((k) => notes[k])
    .sort((a, b) => (a.date === b.date ? b.createdAt - a.createdAt
      : (a.date < b.date ? 1 : -1)))
}

function get(id) {
  ensure()
  return notes[id] || null
}

/**
 * 新增或更新
 * @param {Object} n {id?, date, text, tags}
 */
function upsert(n) {
  ensure()
  const now = Date.now()
  const id = n.id || genId()
  const old = notes[id]
  notes[id] = {
    id,
    date: n.date,
    text: (n.text || '').trim(),
    tags: n.tags || [],
    createdAt: old ? old.createdAt : now,
    updatedAt: now,
    synced: false
  }
  persist()
  return notes[id]
}

function remove(id) {
  ensure()
  if (!notes[id]) return false
  const tomb = {
    id, date: notes[id].date, text: '', tags: [],
    createdAt: notes[id].createdAt, updatedAt: Date.now(),
    deleted: true, synced: false
  }
  // 软删除：保留墓碑，这样云端同步时才知道"这条要删掉"，
  // 否则下次 pull 会把它又拉回来。
  notes[id] = tomb
  persist()
  return true
}

/** 真正从本地抹除（用于清空墓碑） */
function purge(id) {
  ensure()
  delete notes[id]
  persist()
}

/** 搜索 + 标签筛选 */
function search(keyword, tag) {
  ensure()
  const kw = (keyword || '').trim().toLowerCase()
  return listAll().filter((n) => {
    if (n.deleted) return false
    if (tag && n.tags.indexOf(tag) < 0) return false
    if (!kw) return true
    return (n.text || '').toLowerCase().indexOf(kw) >= 0
  })
}

/** 某月哪些天有笔记（用于日历打点） */
function noteDaysInMonth(y, m) {
  ensure()
  const prefix = y + '-' + (m < 10 ? '0' + m : '' + m) + '-'
  const set = {}
  Object.keys(notes).forEach((k) => {
    const n = notes[k]
    if (n.deleted) return
    if (n.date && n.date.indexOf(prefix) === 0) set[n.date] = true
  })
  return set
}

function countUndeleted() {
  ensure()
  return Object.keys(notes).filter((k) => !notes[k].deleted).length
}

/** 未同步条数（含墓碑） */
function pendingCount() {
  ensure()
  return Object.keys(notes).filter((k) => !notes[k].synced).length
}

/**
 * 与云端双向同步：先推本地未同步的，再拉云端全量合并。
 * @returns {Promise<{ok:Boolean, pushed:Number, pulled:Number}>}
 */
function sync() {
  ensure()
  const app = getApp()
  if (syncing) return Promise.resolve({ ok: false, pushed: 0, pulled: 0 })
  if (!app || !app.globalData.useCloud || !app.globalData.cloudEnv || !wx.cloud) {
    return Promise.resolve({ ok: false, pushed: 0, pulled: 0 })
  }
  syncing = true
  try {
    wx.cloud.init({ env: app.globalData.cloudEnv, traceUser: true })
  } catch (e) {
    syncing = false
    return Promise.resolve({ ok: false, pushed: 0, pulled: 0 })
  }

  const pending = Object.keys(notes).filter((k) => !notes[k].synced).map((k) => notes[k])

  const pushStep = pending.length
    ? wx.cloud.callFunction({ name: 'notesSync', data: { action: 'push', notes: pending } })
    : Promise.resolve({ result: { ok: true, saved: 0 } })

  return pushStep.then((r) => {
    const saved = (r && r.result && r.result.saved) || 0
    if (saved || !pending.length) {
      // 推成功后标记已同步；墓碑推完就可以本地抹除
      pending.forEach((n) => {
        if (notes[n.id]) {
          notes[n.id].synced = true
          if (notes[n.id].deleted) delete notes[n.id]
        }
      })
      persist()
    }
    return wx.cloud.callFunction({ name: 'notesSync', data: { action: 'pull' } })
      .then((r2) => {
        const remote = (r2 && r2.result && r2.result.notes) || []
        let pulled = 0
        remote.forEach((n) => {
          const local = notes[n.id]
          // 冲突处理：后写胜出
          if (!local || (n.updatedAt || 0) > (local.updatedAt || 0)) {
            notes[n.id] = {
              id: n.id, date: n.date, text: n.text || '', tags: n.tags || [],
              createdAt: n.createdAt || Date.now(), updatedAt: n.updatedAt || Date.now(),
              synced: true, deleted: !!n.deleted
            }
            if (notes[n.id].deleted) delete notes[n.id]
            pulled++
          }
        })
        persist()
        syncing = false
        return { ok: true, pushed: saved, pulled }
      })
  }).catch(() => {
    syncing = false
    return { ok: false, pushed: 0, pulled: 0 }
  })
}

module.exports = {
  TAGS,
  listByDate, listAll, get, upsert, remove, purge,
  search, noteDaysInMonth, countUndeleted, pendingCount, sync
}
