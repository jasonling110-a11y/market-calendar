// utils/date.js —— 日期工具（无依赖，纯本地计算）

function pad(n) {
  return n < 10 ? '0' + n : '' + n
}

/** 某月天数 */
function daysInMonth(y, m) {
  return new Date(y, m, 0).getDate()
}

/** 某月 1 号是周几（0=周日） */
function firstWeekday(y, m) {
  return new Date(y, m - 1, 1).getDay()
}

/** 月份加减，返回 {y, m} */
function addMonth(y, m, delta) {
  let t = y * 12 + (m - 1) + delta
  return { y: Math.floor(t / 12), m: (t % 12) + 1 }
}

/** 'YYYY-MM-DD' */
function ymd(d) {
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
}

/** 'MM-DD' */
function mdOf(y, m, d) {
  return pad(m) + '-' + pad(d)
}

function today() {
  return new Date()
}

/** 两个 'YYYY-MM-DD' 之间相差天数 */
function diffDays(a, b) {
  const da = new Date(a + 'T00:00:00')
  const db = new Date(b + 'T00:00:00')
  return Math.round((db - da) / 86400000)
}

/** 星期中文 */
const WEEK_CN = ['日', '一', '二', '三', '四', '五', '六']

function weekCn(dateStr) {
  return WEEK_CN[new Date(dateStr + 'T00:00:00').getDay()]
}

/**
 * 生成月视图格子（6 行 × 7 列，含前后补位）
 * 返回 [{y,m,d,md,ymd,cur,today,weekend}]
 */
function buildMonthGrid(y, m, todayYmd) {
  const total = daysInMonth(y, m)
  const lead = firstWeekday(y, m)
  const cells = []

  // 上月补位
  const prev = addMonth(y, m, -1)
  const prevTotal = daysInMonth(prev.y, prev.m)
  for (let i = lead - 1; i >= 0; i--) {
    const d = prevTotal - i
    cells.push(mk(prev.y, prev.m, d, false))
  }
  // 本月
  for (let d = 1; d <= total; d++) {
    cells.push(mk(y, m, d, true))
  }
  // 下月补位（补齐到 42 格，保证 6 行高度稳定）
  const next = addMonth(y, m, 1)
  let nd = 1
  while (cells.length < 42) {
    cells.push(mk(next.y, next.m, nd++, false))
  }
  return cells

  function mk(yy, mm, dd, cur) {
    const md = mdOf(yy, mm, dd)
    const s = yy + '-' + md
    const wd = new Date(s + 'T00:00:00').getDay()
    return {
      y: yy, m: mm, d: dd, md, ymd: s, cur,
      today: s === todayYmd,
      weekend: wd === 0 || wd === 6
    }
  }
}

module.exports = {
  pad, daysInMonth, firstWeekday, addMonth, ymd, mdOf,
  today, diffDays, weekCn, WEEK_CN, buildMonthGrid
}
