// pages/notes/notes.js —— 我的笔记汇总（搜索 / 标签筛选 / 云同步）
const notes = require('../../services/notes.js')

Page({
  data: {
    list: [],
    keyword: '',
    tag: '',                 // '' 表示全部
    tagList: notes.TAGS,
    total: 0,
    shown: 0,
    syncText: '仅本地',
    syncing: false
  },

  onShow() {
    this.refreshNotes()
    this.refreshSyncState()
  },

  refreshNotes() {
    const list = notes.search(this.data.keyword, this.data.tag)
    const view = list.map((n) => ({
      id: n.id,
      date: n.date,
      dateLabel: n.date.slice(0, 4) + '.' + n.date.slice(5, 7) + '.' + n.date.slice(8, 10),
      week: '周' + '日一二三四五六'[new Date(n.date + 'T00:00:00').getDay()],
      text: n.text,
      // 列表只显示前 3 行，超出的在详情页看
      brief: n.text.length > 90 ? n.text.slice(0, 90) + '…' : n.text,
      tags: n.tags || [],
      time: this.fmtTime(n.updatedAt)
    }))
    this.setData({
      list: view,
      shown: view.length,
      total: notes.countUndeleted()
    })
  },

  fmtTime(ts) {
    if (!ts) return ''
    const d = new Date(ts)
    const p = (x) => (x < 10 ? '0' + x : '' + x)
    return p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes())
  },

  onSearch(e) {
    this.setData({ keyword: e.detail.value || '' }, () => this.refreshNotes())
  },

  clearSearch() {
    this.setData({ keyword: '' }, () => this.refreshNotes())
  },

  pickTag(e) {
    const t = e.currentTarget.dataset.t || ''
    this.setData({ tag: t }, () => this.refreshNotes())
  },

  openNote(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({ url: '/pages/note/note?id=' + id })
  },

  addNote() {
    const t = new Date()
    const p = (x) => (x < 10 ? '0' + x : '' + x)
    const d = t.getFullYear() + '-' + p(t.getMonth() + 1) + '-' + p(t.getDate())
    wx.navigateTo({ url: '/pages/note/note?date=' + d })
  },

  refreshSyncState() {
    const app = getApp()
    const on = app && app.globalData.useCloud && app.globalData.cloudEnv
    const pending = notes.pendingCount()
    this.setData({
      syncText: on ? (pending ? pending + ' 条待同步' : '已同步') : '仅本地存储'
    })
  },

  onSync() {
    if (this.data.syncing) return
    const app = getApp()
    if (!app || !app.globalData.useCloud || !app.globalData.cloudEnv) {
      wx.showToast({
        title: '未配置云开发环境，笔记保存在本机',
        icon: 'none', duration: 2200
      })
      return
    }
    this.setData({ syncing: true, syncText: '同步中…' })
    notes.sync().then((r) => {
      this.setData({ syncing: false })
      this.refreshNotes()
      this.refreshSyncState()
      if (r.ok) {
        wx.showToast({
          title: `已同步（上传 ${r.pushed} / 下载 ${r.pulled}）`,
          icon: 'none', duration: 2000
        })
      } else {
        wx.showToast({ title: '同步失败，已保存在本机', icon: 'none' })
      }
    })
  }
})
