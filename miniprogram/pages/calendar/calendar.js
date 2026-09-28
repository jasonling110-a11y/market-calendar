// pages/calendar/calendar.js —— 市场日历主页面
const dateUtil = require('../../utils/date.js')
const cal = require('../../services/calendar.js')
const cloudSvc = require('../../services/cloud.js')
const notes = require('../../services/notes.js')

// 分类 → 中文标签 / 样式
const CAT = {
  macro_us: { label: '美国数据', cls: 'us' },
  macro_cn: { label: '中国数据', cls: 'cn' },
  macro_eu: { label: '欧洲数据', cls: 'eu' },
  macro_jp: { label: '日本数据', cls: 'jp' },
  macro_kr: { label: '韩国数据', cls: 'kr' },
  shock: { label: '突发事件', cls: 'shock' },
  tech: { label: '技术突破', cls: 'tech' },
  policy: { label: '政策制度', cls: 'policy' },
  market: { label: '市场里程碑', cls: 'market' }
}
// 地区角标：一眼看出这条事件属于哪个资本市场
const REG = { US: '美国', CN: '中国', EU: '欧洲', JP: '日本', KR: '韩国', GLOBAL: '全球' }
const CONF = {
  confirmed: { label: '已官宣', cls: 'confirmed' },
  estimated: { label: '规律推算', cls: 'estimated' },
  rumored: { label: '待官宣', cls: 'rumored' }
}

function fmtPct(p) {
  const n = Number(p)
  const s = Math.abs(n).toFixed(2)
  return (n > 0 ? '+' : (n < 0 ? '-' : '')) + s + '%'
}

/** 数值格式化：整数不带小数，小数最多 2 位，带单位 */
function fmtVal(v, unit) {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  const abs = Math.abs(n)
  let s
  if (abs % 1 === 0) {
    s = String(abs)
  } else {
    // 最多 2 位小数，去掉无意义的尾随 0（0.30 → 0.3）
    s = abs.toFixed(2).replace(/0+$/, '').replace(/\.$/, '')
  }
  return (n < 0 ? '-' : '') + s + (unit || '')
}

/**
 * 实际值 vs 市场预期 的偏离。
 * 只做中性描述（高于/低于），不判断利好利空——
 * 同一个"高于预期"对 CPI 和失业率方向相反，判断交给使用者。
 */
function biasOf(a, f) {
  if (a === null || a === undefined || f === null || f === undefined) return null
  const d = Number(a) - Number(f)
  if (isNaN(d)) return null
  if (Math.abs(d) < 1e-6) return { text: '符合预期', cls: 'flat' }
  return d > 0 ? { text: '高于预期', cls: 'up' } : { text: '低于预期', cls: 'down' }
}

Page({
  data: {
    mode: 'history',                 // history | upcoming
    weekdays: ['日', '一', '二', '三', '四', '五', '六'],
    year: 2026, month: 9,
    slots: [], swiperIndex: 1,
    selYmd: '', selLabel: '', selWeek: '',
    // 初始化为完整结构，避免首帧 WXML 访问 null 属性
    hist: { e: [], v: [], s: null, ups: [], c: [],
            calTotal: 0, calKeyCount: 0, calValCount: 0, empty: true },
    calFilter: 'key',        // 财经日历过滤：key=只看重点(all>=2星) / all=全部
    up: [],               // 选中日预告
    notes: [],            // 选中日的个人笔记
    upcomingList: [],     // 未来清单
    meta: null,
    horizon: 90,
    synced: false,        // 是否成功拉到云端增量
    syncTime: ''          // 云端数据更新时间，点它可手动刷新
  },

  onLoad() {
    const now = new Date()
    const todayYmd = dateUtil.ymd(now)
    const meta = cal.getMeta()

    this.todayYmd = todayYmd
    this.setData({
      todayYmd,
      year: now.getFullYear(),
      month: now.getMonth() + 1,
      selYmd: todayYmd,
      meta,
      horizon: (meta && meta.horizonDays) || 90,
      yearRange: (meta && meta.stats && meta.stats.yearRange)
        ? meta.stats.yearRange[0] + '–' + meta.stats.yearRange[1] : '—'
    })

    this.refreshSlots()
    this.loadDay(now.getFullYear(), now.getMonth() + 1, now.getDate())
    this.loadUpcomingList()

    // 云端增量：失败静默，不影响首屏
    this.doCloudSync(false)
  },

  /**
   * 云端同步。定时触发器每天 18:00 已把当天数据落库，
   * 默认命中 30 分钟内快照直接返回；force=true 强制重抓。
   */
  doCloudSync(force) {
    if (force) wx.showLoading({ title: '刷新中', mask: true })
    const p = force ? cloudSvc.forceRefresh() : cloudSvc.syncDelta()
    return p.then((r) => {
      if (force) wx.hideLoading()
      if (!r || !r.ok) {
        if (force) wx.showToast({ title: '刷新失败，已保留本地数据', icon: 'none' })
        return
      }
      this.setData({ synced: true, syncTime: this.fmtTime(r.updatedAt) })
      this.refreshSlots()
      this.loadUpcomingList()
      const s = this.data.selYmd.split('-')
      this.loadDay(+s[0], +s[1], +s[2])
      if (force) wx.showToast({ title: '已更新', icon: 'success' })
    })
  },

  onRefreshTap() {
    const app = getApp()
    if (!app || !app.globalData.useCloud || !app.globalData.cloudEnv) {
      wx.showModal({
        title: '数据更新说明',
        content: '未配置云开发环境，当前所有数据来自内置离线包。\n\n'
          + '要开启每日自动更新，需要：\n'
          + '1. 开通云开发并填写环境 ID\n'
          + '2. 部署 syncCalendar 云函数\n'
          + '3. 建立 market_daily 等集合\n\n'
          + '未配置时，数据随新版本一起发布。',
        showCancel: false,
        confirmText: '知道了'
      })
      return
    }
    this.doCloudSync(true)
  },

  // ---------- 日历网格 ----------
  buildSlot(y, m) {
    const cells = dateUtil.buildMonthGrid(y, m, this.todayYmd)
    const histSet = cal.historyDaysInMonth(y, m)      // 精确到年月，不再跨年聚合
    const upSet = cal.upcomingDaysInMonth(y, m)
    const noteSet = notes.noteDaysInMonth(y, m)       // 我写过笔记的日子
    const sel = this.data.selYmd
    for (const c of cells) {
      c.hasHist = !!histSet[c.ymd]
      c.hasUp = !!upSet[c.ymd]
      c.hasNote = !!noteSet[c.ymd]
      c.isSel = c.ymd === sel
    }
    return {
      key: y + '-' + m, y, m, cells,
      noData: !cal.monthHasAnyData(y, m)               // 整月都没有收录内容
    }
  },

  refreshSlots() {
    const { y, m } = this.data
    const p = dateUtil.addMonth(y, m, -1)
    const n = dateUtil.addMonth(y, m, 1)
    this.setData({
      slots: [this.buildSlot(p.y, p.m), this.buildSlot(y, m), this.buildSlot(n.y, n.m)]
    })
  },

  onSwipe(e) {
    const cur = e.detail.current
    if (cur === this.data.swiperIndex) return
    const base = dateUtil.addMonth(this.data.year, this.data.month, cur - 1)
    this.setData({ year: base.y, month: base.m, swiperIndex: 1 }, () => {
      this.refreshSlots()
    })
  },

  onPrev() {
    const b = dateUtil.addMonth(this.data.year, this.data.month, -1)
    this.setData({ year: b.y, month: b.m, swiperIndex: 1 }, () => this.refreshSlots())
  },

  onNext() {
    const b = dateUtil.addMonth(this.data.year, this.data.month, 1)
    this.setData({ year: b.y, month: b.m, swiperIndex: 1 }, () => this.refreshSlots())
  },

  goToday() {
    const t = new Date()
    this.setData({
      year: t.getFullYear(), month: t.getMonth() + 1, swiperIndex: 1
    }, () => {
      this.refreshSlots()
      this.loadDay(t.getFullYear(), t.getMonth() + 1, t.getDate())
    })
  },

  onMode(e) {
    const m = e.currentTarget.dataset.m
    if (m === this.data.mode) return
    this.setData({ mode: m })
  },

  onTapDay(e) {
    const { y, m, d } = e.currentTarget.dataset
    const ymd = y + '-' + dateUtil.mdOf(+y, +m, +d)
    // 点到非本月格子时，先把视图切到该月
    if (+m !== this.data.month || +y !== this.data.year) {
      this.setData({ year: +y, month: +m, swiperIndex: 1 }, () => {
        this.refreshSlots()
        this.selectDay(+y, +m, +d, ymd)
      })
    } else {
      this.selectDay(+y, +m, +d, ymd)
    }
  },

  selectDay(y, m, d, ymd) {
    this.setData({ selYmd: ymd }, () => {
      this.refreshSlots()
      this.loadDay(y, m, d)
    })
  },

  // ---------- 某日内容 ----------
  loadDay(y, m, d) {
    const md = dateUtil.mdOf(y, m, d)
    const ymd = y + '-' + md
    const raw = cal.getHistoryByYmd(ymd)

    const events = (raw.e || []).map((x) => {
      const c = CAT[x.c] || { label: '事件', cls: 'market' }
      return {
        t: x.t, d: x.d, i: x.i || 2,
        label: c.label, cls: 'tag-' + c.cls,
        r: (x.r || '').toLowerCase(), region: REG[x.r] || ''
      }
    })

    let sector = null
    if (raw.s && raw.s.up && raw.s.up.length) {
      sector = {
        date: raw.s.date || ymd,
        up: raw.s.up.map((x) => ({ n: x.n, p: fmtPct(x.p) })),
        down: raw.s.down.map((x) => ({ n: x.n, p: fmtPct(x.p) })),
        bt: raw.s.bt, bf: raw.s.bt - raw.s.br, br: raw.s.br
      }
    }

    // 这一天真实发布过的数据（实际值 / 预期 / 前值 / 同比 / 环比）
    // 一天最多可能十几项，用重要度区分主次：★★★ 高 / ★★ 中 / ★ 低
    const vals = (raw.v || []).map((x) => {
      const b = biasOf(x.a, x.f)
      const hasF = !(x.f === null || x.f === undefined)
      const hasP = !(x.p === null || x.p === undefined)
      const imp = x.i || 2
      return {
        k: x.k,                        // 同一天多个指标，用指标键做唯一 key
        n: x.n,
        imp,
        stars: imp >= 3 ? '★★★' : (imp === 2 ? '★★' : '★'),
        hot: imp >= 3,
        // 中国统计局口径没有公开市场预期，此时只展示实际值，不摆空列
        onlyActual: !hasF && !hasP,
        a: fmtVal(x.a, x.u),
        f: hasF ? fmtVal(x.f, x.u) : '—',
        p: hasP ? fmtVal(x.p, x.u) : '—',
        y: x.y === null || x.y === undefined ? '' : '同比 ' + fmtVal(x.y, x.u),
        m: x.m === null || x.m === undefined ? '' : '环比 ' + fmtVal(x.m, x.u),
        bias: b ? b.text : '', biasCls: b ? b.cls : '',
        hasActual: x.a !== null && x.a !== undefined
      }
    })

    const up = this.decorate(cal.getUpcomingByYmd(ymd), ymd)

    // 这一天的个人笔记
    const dayNotes = notes.listByDate(ymd).map((n) => ({
      id: n.id,
      text: n.text,
      tags: n.tags || [],
      time: this.fmtTime(n.updatedAt)
    }))

    // 财经日历：当天全部发布项（含时间/国家/报告期）
    // 这是密度来源——一个月 200+ 条，东方财富日历就是这个粒度。
    // 已经挂上实际值的行不再重复出现在「数值」卡片里，去重在这里做。
    // 每次加载都递增：让日历条目的 wx:key 变化，节点重建 → 入场动画重新播放
    // （如果 key 不变，切换日期时节点复用，CSS 动画不会重跑）
    const seq = (this.animSeq = (this.animSeq || 0) + 1)
    const linkedKeys = {}
    const calAll = (raw.c || []).map((x, cidx) => {
      const b = biasOf(x.a, x.f)
      const hasVal = x.a !== null && x.a !== undefined
      if (x.mk) linkedKeys[x.mk] = true
      let pd = ''
      if (x.pd) {
        const mm = +x.pd.slice(2)
        pd = x.pd.slice(0, 2) === String(y).slice(2)
          ? mm + ' 月'
          : x.pd.slice(0, 2) + '年' + mm + '月'
      }
      return {
        k: seq + '|' + x.tm + '|' + x.co + '|' + x.n,
        // 只给前 18 条入场动画：一次动画上百个节点会掉帧
        anr: cidx < 18,
        tm: x.tm, co: x.co, n: x.n, i: x.i, kind: x.k,
        hot: x.i >= 3,
        pd: pd,
        hasVal: hasVal,
        a: hasVal ? fmtVal(x.a, x.u) : '',
        f: (x.f === null || x.f === undefined) ? '' : fmtVal(x.f, x.u),
        p: (x.p === null || x.p === undefined) ? '' : fmtVal(x.p, x.u),
        bias: hasVal && b ? b.text : '',
        biasCls: hasVal && b ? b.cls : ''
      }
    })
    // 「重点」默认只看 ★★ 以上：一个月 200 条里真正影响定价的就那几十条
    const calKey = calAll.filter((x) => x.i >= 2)
    this.calAll = calAll
    this.calKey = calKey
    // 极端情况：这一天全是 ★ 级信息（如只有一条「央行讲话」）。
    // 此时若还按「重点」过滤就成了空白卡片，必须自动回落到全部。
    const calShown = () => (calKey.length
      ? (this.data.calFilter === 'all' ? calAll : calKey)
      : calAll)

    // 已被日历行带出实际值的指标，从「数值」卡片里剔除，避免同一读数出现两遍
    vals = vals.filter((x) => !linkedKeys[x.k])

    // B 站 UP 主观点（转写提炼，见 tools/fetch_bilibili.py + data/up_summary.json）
    // 只放要点，不放转写全文——全文几万字，主包放不下也不是给手机看的。
    const ups = (raw.u || []).map((x) => ({
      k: x.k,
      t: x.t || '',
      n: x.n || 'UP 主',
      pts: x.p || [],
      url: 'https://www.bilibili.com/video/' + x.k
    }))

    this.setData({
      hist: {
        e: events, v: vals, s: sector, ups,
        c: calShown(),
        calTotal: calAll.length,
        calKeyCount: calKey.length,
        calValCount: calAll.filter((x) => x.hasVal).length,
        empty: !events.length && !sector && !vals.length && !calAll.length
               && !dayNotes.length && !ups.length
      },
      up,
      notes: dayNotes,
      selLabel: y + '年' + m + '月' + d + '日',
      selWeek: '星期' + dateUtil.weekCn(ymd),
      selYmdText: ymd
    })
  },

  // 财经日历过滤：默认「重点」（★★ 以上），可切到「全部」
  // 理由：一个月 200+ 条里真正影响定价的就几十条，默认全量会淹掉关键读数
  setCalFilter(e) {
    const f = e.currentTarget.dataset.f
    if (f === this.data.calFilter) return
    const all = this.calAll || []
    const key = this.calKey || []
    this.setData({
      calFilter: f,
      'hist.c': key.length ? (f === 'all' ? all : key) : all
    })
  },

  // 小程序内无法直接打开 bilibili.com（非业务域名），复制链接是唯一可靠路径
  openVideo(e) {
    const url = e.currentTarget.dataset.url
    if (!url) return
    wx.setClipboardData({
      data: url,
      success: () => wx.showToast({ title: '链接已复制，到浏览器打开', icon: 'none' })
    })
  },

  fmtTime(ts) {

    if (!ts) return ''
    const t = new Date(ts)
    const p = (x) => (x < 10 ? '0' + x : '' + x)
    return p(t.getHours()) + ':' + p(t.getMinutes())
  },

  /** 供笔记编辑页返回时回调：重算打点并刷新当天面板 */
  refreshNotes() {
    this.refreshSlots()
    const s = (this.data.selYmd || '').split('-')
    if (s.length === 3) this.loadDay(+s[0], +s[1], +s[2])
  },

  goNotes() {
    wx.navigateTo({ url: '/pages/notes/notes' })
  },

  addNote() {
    wx.navigateTo({ url: '/pages/note/note?date=' + this.data.selYmd })
  },

  openNote(e) {
    wx.navigateTo({ url: '/pages/note/note?id=' + e.currentTarget.dataset.id })
  },

  decorate(items, ymd) {
    return (items || []).map((x) => {
      const c = CAT[x.c] || { label: '事件', cls: 'market' }
      const cf = CONF[x.cf] || CONF.estimated
      const days = dateUtil.diffDays(this.todayYmd, ymd)
      let cd = ''
      if (days === 0) cd = '今天'
      else if (days === 1) cd = '明天'
      else if (days > 1) cd = days + ' 天后'
      else cd = '已过去'

      // 数值锚点。语义必须分清：
      //   a = 上一期真实公布值（不是本期预期）
      //   f = 本期市场预期，只有云端明确同步到才有
      let val = null
      if (x.v) {
        const hasF = !(x.v.f === null || x.v.f === undefined)
        const hasA = !(x.v.a === null || x.v.a === undefined)
        if (hasF || hasA) {
          val = {
            n: x.v.n,
            hasF,
            hasA,
            txt: hasA ? fmtVal(x.v.a, x.v.u) : '',
            ftxt: hasF ? fmtVal(x.v.f, x.v.u) : '',
            date: x.v.d || '',
            prev: (x.v.p === null || x.v.p === undefined) ? '' : fmtVal(x.v.p, x.v.u),
            y: (x.v.y === null || x.v.y === undefined) ? '' : '同比 ' + fmtVal(x.v.y, x.v.u),
            m: (x.v.m === null || x.v.m === undefined) ? '' : '环比 ' + fmtVal(x.v.m, x.v.u)
          }
        }
      }

      return {
        t: x.t, d: x.d, tm: x.tm, i: x.i || 2,
        label: c.label, cls: 'tag-' + c.cls,
        r: (x.r || '').toLowerCase(), region: REG[x.r] || '',
        confLabel: cf.label, confCls: 'conf-' + cf.cls,
        cd, v: val
      }
    })
  },

  loadUpcomingList() {
    const list = cal.getUpcomingList(this.todayYmd)
    const out = []
    for (const g of list) {
      const days = dateUtil.diffDays(this.todayYmd, g.date)
      out.push({
        date: g.date,
        week: '周' + dateUtil.weekCn(g.date),
        cd: days === 0 ? '今天' : (days === 1 ? '明天' : days + ' 天后'),
        items: this.decorate(g.items, g.date)
      })
    }
    this.setData({ upcomingList: out })
  },

  // 从笔记页 / 汇总页返回时，笔记可能已改动，重新渲染
  onShow() {
    if (this.data.selYmd) {
      this.refreshSlots()
      const s = this.data.selYmd.split('-')
      if (s.length === 3) this.loadDay(+s[0], +s[1], +s[2])
    }
  },

  goAbout() {
    wx.navigateTo({ url: '/pages/about/about' })
  },

  onShareAppMessage() {
    return {
      title: '市场日历 · ' + this.data.selLabel,
      path: '/pages/calendar/calendar'
    }
  }
})
