// pages/note/note.js —— 笔记编辑（新增 / 修改）
// 入参：?date=YYYY-MM-DD（从日历某天进来） 或 ?id=xxx（编辑已有笔记）
const notes = require('../../services/notes.js')

Page({
  data: {
    isEdit: false,
    id: '',
    date: '',
    dateLabel: '',
    text: '',
    tags: [],
    tagList: notes.TAGS,
    maxLen: 5000,
    canSave: false
  },

  onLoad(query) {
    const tagList = notes.TAGS
    // 编辑已有笔记
    if (query.id) {
      const n = notes.get(query.id)
      if (n) {
        this.setData({
          isEdit: true, id: n.id, date: n.date,
          dateLabel: this.fmtDate(n.date),
          text: n.text, tags: n.tags || [],
          tagList, canSave: !!(n.text || '').trim()
        })
        wx.setNavigationBarTitle({ title: '编辑笔记' })
        return
      }
    }
    // 新建：日期必传，兜底用今天
    const d = query.date || this.todayStr()
    this.setData({
      date: d, dateLabel: this.fmtDate(d), tagList
    })
    wx.setNavigationBarTitle({ title: '写点想法' })
  },

  todayStr() {
    const t = new Date()
    const p = (x) => (x < 10 ? '0' + x : '' + x)
    return t.getFullYear() + '-' + p(t.getMonth() + 1) + '-' + p(t.getDate())
  },

  fmtDate(s) {
    if (!s) return ''
    const p = s.split('-')
    return p[0] + '年' + (+p[1]) + '月' + (+p[2]) + '日'
  },

  onInput(e) {
    const v = e.detail.value || ''
    this.setData({ text: v, canSave: !!v.trim() })
  },

  toggleTag(e) {
    const t = e.currentTarget.dataset.t
    const tags = this.data.tags.slice()
    const i = tags.indexOf(t)
    if (i >= 0) tags.splice(i, 1)
    else tags.push(t)
    this.setData({ tags })
  },

  onSave() {
    const text = (this.data.text || '').trim()
    if (!text) {
      wx.showToast({ title: '写点什么吧', icon: 'none' })
      return
    }
    notes.upsert({
      id: this.data.id || undefined,
      date: this.data.date,
      text,
      tags: this.data.tags
    })
    wx.showToast({ title: this.data.isEdit ? '已更新' : '已保存', icon: 'success' })
    this.goBack()
  },

  onDelete() {
    if (!this.data.isEdit) return
    wx.showModal({
      title: '删除这条笔记？',
      content: '删除后无法恢复',
      confirmColor: '#ff3b30',
      success: (r) => {
        if (!r.confirm) return
        notes.remove(this.data.id)
        wx.showToast({ title: '已删除', icon: 'none' })
        this.goBack()
      }
    })
  },

  goBack() {
    // 通知上一页刷新（日历页 / 列表页都会监听）
    const pages = getCurrentPages()
    const prev = pages[pages.length - 2]
    if (prev && typeof prev.refreshNotes === 'function') {
      prev.refreshNotes()
    }
    setTimeout(() => wx.navigateBack(), 320)
  }
})
