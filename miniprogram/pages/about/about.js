// pages/about/about.js —— 数据来源与更新说明
const cal = require('../../services/calendar.js')

Page({
  data: {
    meta: null,
    range: '',
    sectorRange: '',
    cadence: { cn: [], us: [] }
  },

  onLoad() {
    const m = cal.getMeta()
    const cn = (m.cadence && m.cadence.cn || []).map((x) => ({ n: x[0], t: x[1], d: x[2] }))
    const us = (m.cadence && m.cadence.us || []).map((x) => ({ n: x[0], t: x[1], d: x[2] }))
    this.setData({
      meta: m,
      cadence: { cn, us },
      sectorRange: m.sectorRange ? (m.sectorRange[0] + ' ~ ' + m.sectorRange[1]) : '暂无',
      range: (m.stats && m.stats.yearRange)
        ? (m.stats.yearRange[0] + ' – ' + m.stats.yearRange[1]) : '—'
    })
  }
})
