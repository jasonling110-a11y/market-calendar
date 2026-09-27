// 云函数 notesSync —— 我的笔记双向同步
//
// 安全要点：
//   1. 一切读写都绑定 cloud.getWXContext().OPENID，用户只能碰自己的笔记。
//   2. 客户端传入的笔记对象不可信：只取白名单字段，_openid 由服务端强制写入。
//   3. 软删除用 deleted 墓碑，避免 pull 时把已删的笔记又拉回客户端。

const cloud = require('wx-server-sdk')
cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV })
const db = cloud.database()
const COL = 'market_notes'
const MAX_TEXT = 5000        // 单条笔记字数上限，防止恶意灌爆数据库

/** 只保留可信字段，丢弃客户端塞的 _openid / _id 等 */
function sanitize(n, openid) {
  if (!n || typeof n !== 'object') return null
  const id = String(n.id || '').slice(0, 64)
  const date = String(n.date || '').slice(0, 10)
  if (!id || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return null
  const tags = Array.isArray(n.tags) ? n.tags.slice(0, 8).map((t) => String(t).slice(0, 16)) : []
  return {
    id,
    date,
    text: String(n.text || '').slice(0, MAX_TEXT),
    tags,
    createdAt: Number(n.createdAt) || Date.now(),
    updatedAt: Number(n.updatedAt) || Date.now(),
    deleted: !!n.deleted,
    _openid: openid
  }
}

exports.main = async (event = {}) => {
  const { OPENID } = cloud.getWXContext()
  if (!OPENID) return { ok: false, message: '无法获取用户身份' }
  const col = db.collection(COL)
  const action = event.action

  // ---------- 推送：客户端 -> 云端 ----------
  if (action === 'push') {
    const list = Array.isArray(event.notes) ? event.notes.slice(0, 200) : []
    let saved = 0
    for (const raw of list) {
      const n = sanitize(raw, OPENID)
      if (!n) continue
      try {
        const exist = await col.where({ _openid: OPENID, id: n.id }).limit(1).get()
        if (exist.data && exist.data.length) {
          await col.doc(exist.data[0]._id).update({ data: n })
        } else {
          await col.add({ data: n })
        }
        saved++
      } catch (e) {
        // 单条失败不影响整批
      }
    }
    return { ok: true, saved }
  }

  // ---------- 拉取：云端 -> 客户端 ----------
  if (action === 'pull') {
    try {
      const res = await col.where({ _openid: OPENID }).limit(1000).get()
      const notes = (res.data || []).map((x) => ({
        id: x.id, date: x.date, text: x.text, tags: x.tags,
        createdAt: x.createdAt, updatedAt: x.updatedAt, deleted: x.deleted
      }))
      return { ok: true, notes }
    } catch (e) {
      // 集合还没建时返回空，不让客户端报错
      return { ok: true, notes: [] }
    }
  }

  // ---------- 清空（危险操作，仅删自己的）----------
  if (action === 'clear') {
    try {
      await col.where({ _openid: OPENID }).remove()
      return { ok: true }
    } catch (e) {
      return { ok: false, message: String(e.message || e) }
    }
  }

  return { ok: false, message: '未知操作' }
}
