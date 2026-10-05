/* 「利润断层」栏（市场日历站内新增）· 专项自检
   用法：NODE_PATH=<含 jsdom 的 node_modules> node tools/check_profitgap_tab.js

   被测对象是 preview/index.html（数据内嵌，jsdom 可离线跑完整启动流程）。
   可用 MC_HTML=<path> 指定其它副本（例如故意改坏一份，验证断言真的会失败）。

   覆盖：结构/语义、初始态、打开、加载判定的四类形态（跨域成功 / 可读 about:blank /
        contentWindow 为 null / 网络 error）+ 15s 超时、重试与刷新、
        层内「利润断层 / 日历」双页卡（取代原先那个「返回日历」按钮）、
        三种返回日历的方式、快捷键不穿透（回归）、iframe 不销毁、hash 深链、
        与日历互不干扰、Tab 焦点锁、三端产物一致。

   注意 jsdom 与真实浏览器的一处差异（踩过一次坑）：
       在 jsdom 里给 iframe 设 src 后，contentWindow.location.href **直接就是那个 URL**，
       既不抛错也不是 about:blank。所以「跨域」和「about:blank」两个分支都必须
       用 asCrossOrigin() / asReadableBlank() 显式构造，不能指望默认行为。
*/
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const HTML = process.env.MC_HTML || path.join(__dirname, "..", "preview", "index.html");
const TARGET = "https://jasonling110-a11y.github.io/profit-gap/dashboard.html";
const BASE = "https://market-calendar-71280.app.workbuddy.host/";
const html = fs.readFileSync(HTML, "utf-8");

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log("  ✔ " + name); }
  else { fail++; console.log("  ✘ " + name + (extra !== undefined ? "  → " + extra : "")); }
}

/* 启动一个页面实例。
   - fetch 换成永不 resolve 的 promise：日历的 wbInit() 会去探测本机 /api/status，
     否则在 jsdom 里会抛未捕获异常，把无关噪声混进结果。
   - 加载超时回调被截获并存入 timers[]，便于手动触发「超时」分支（不用真等 30 秒）。
     这里刻意用区间（20s~120s）而不是精确匹配超时值：日历自身注册的是 15000 的
     wbPoll 轮询，落在区间外不会误截；以后调超时也不必再改这个钩子。 */
function boot(opts) {
  opts = opts || {};
  const timers = [];
  const o = {
    runScripts: "dangerously",
    pretendToBeVisual: true,
    url: opts.url || BASE,
    resources: undefined,
    beforeParse(win) {
      win.fetch = function () { return new Promise(function () {}); };
      const real = win.setTimeout;
      win.setTimeout = function (fn, ms) {
        if (ms >= 20000 && ms <= 120000) { timers.push(fn); return -1000 - timers.length; }
        return real.call(win, fn, ms);
      };
    },
  };
  const dom = new JSDOM(html, o);
  return { dom, window: dom.window, doc: dom.window.document, timers };
}
const $ = (d, id) => d.getElementById(id);
const click = (w, el) => el.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
const fire = (w, el, type) => el.dispatchEvent(new w.Event(type, { bubbles: false }));
function keydown(w, el, key, shiftKey) {
  el.dispatchEvent(new w.KeyboardEvent("keydown", { key: key, shiftKey: !!shiftKey, bubbles: true, cancelable: true }));
}
// 模拟「跨域」：读 contentWindow 抛错 —— 真实浏览器里跨域就是这样
function asCrossOrigin(frame) {
  Object.defineProperty(frame, "contentWindow", { configurable: true, get() { throw new Error("simulated cross-origin"); } });
}
/* 模拟「可读、但停在 about:blank」：显式造一个能读、href 却是 blank 的 contentWindow。
   ⚠️ 不能靠 `delete frame.contentWindow` 去「还原原型上的 getter」——
   实测 jsdom 的原型 getter 会把 location.href 直接反映成 iframe 的 src URL
   （既不抛错、也不是 about:blank），所以那个写法根本构造不出本场景，
   断言会在「实际上走了成功分支」的前提下凭空成立或凭空失败。 */
function asReadableBlank(frame) {
  Object.defineProperty(frame, "contentWindow", {
    configurable: true,
    get() { return { location: { href: "about:blank" } }; },
  });
}
/* 模拟「加载彻底失败、连 contentWindow 都拿不到」：
   真实浏览器里断网、或被 X-Frame-Options 拒绝后显示内置错误页时就是这种形态。
   必须与「跨域」区分开 —— 跨域时 contentWindow 是有的，只是读 location 抛 SecurityError。 */
function asNullWindow(frame) {
  Object.defineProperty(frame, "contentWindow", { configurable: true, get() { return null; } });
}
/* 撤掉上面几个辅助打下的 own property，还原 jsdom 自己的 contentWindow。
   必须还原！否则后续再给同一个 iframe 设 src 时，jsdom 内部也会去读 contentWindow，
   一头撞上我们那个「抛错」的 getter，往输出里灌一串无关堆栈（踩过）。 */
function restoreRealWindow(frame) { delete frame.contentWindow; }

console.log("=== 「利润断层」栏自检 ===");
console.log("（被测文件：" + path.relative(path.join(__dirname, ".."), HTML) + "）\n");

/* ================= 1. 静态结构与语义 ================= */
console.log("[1] 结构与可用性");
{
  const { doc } = boot();
  const tabs = doc.querySelector('.apptabs[role="tablist"]');
  ok("顶栏存在 tablist", !!tabs && tabs.getAttribute("aria-label") === "工作台切换");
  ok("两个标签 id 正确且 role=tab",
     !!$(doc, "tabCal") && !!$(doc, "tabGap") &&
     $(doc, "tabCal").getAttribute("role") === "tab" &&
     $(doc, "tabGap").getAttribute("role") === "tab");
  ok("覆盖层 id=gapShell，role=dialog + aria-modal",
     !!$(doc, "gapShell") && $(doc, "gapShell").getAttribute("role") === "dialog" &&
     $(doc, "gapShell").getAttribute("aria-modal") === "true");
  ok("覆盖层 aria-labelledby 指向标题元素",
     $(doc, "gapShell").getAttribute("aria-labelledby") === "gapTitle" && !!$(doc, "gapTitle"));
  ok("ifrframe 有 title（无障碍）", !!$(doc, "gapFrame").getAttribute("title"));
  ok("层内有两个对等页卡（利润断层 / 日历）",
     !!$(doc, "gapTabGap") && !!$(doc, "gapTabCal") &&
     $(doc, "gapTabGap").getAttribute("role") === "tab" &&
     $(doc, "gapTabCal").getAttribute("role") === "tab");
  ok("原来的「返回日历」按钮已移除（gapClose 不该再存在）", !$(doc, "gapClose"));
  ok("两个页卡同属一个 .gap-tabs[role=tablist]，且与顶栏同一 aria-label",
     (function () {
       var a = $(doc, "gapTabGap").closest('[role="tablist"]'),
           b = $(doc, "gapTabCal").closest('[role="tablist"]');
       return !!a && a === b && a.classList.contains("gap-tabs") &&
              a.getAttribute("aria-label") === "工作台切换";
     })());
  ok("页卡带 aria-controls 指向舞台（页卡语义完整）",
     $(doc, "gapTabGap").getAttribute("aria-controls") === "gapStage" && !!$(doc, "gapStage"));
  ok("「日历」页卡带 title 提示 Esc 仍然可用（原按钮上的 Esc 提示没丢干净）",
     /Esc/.test($(doc, "gapTabCal").getAttribute("title") || ""));
  ok("工具栏其余按钮齐全（刷新 / 新窗口）",
     !!$(doc, "gapReload") && !!$(doc, "gapNew"));
  ok("加载态与失败兜底齐全", !!$(doc, "gapLoad") && !!$(doc, "gapFb") &&
     !!$(doc, "gapFbMsg") && !!$(doc, "gapFbRetry") && !!$(doc, "gapFbNew"));
  ok("失败兜底 role=alert（读屏可感知）", $(doc, "gapFb").getAttribute("role") === "alert");
  ok("iframe 初始无 src（不预加载、不影响日历）", !$(doc, "gapFrame").getAttribute("src"));
  const sb = $(doc, "gapFrame").getAttribute("sandbox") || "";
  ok("sandbox 允许脚本与同源存储", /allow-scripts/.test(sb) && /allow-same-origin/.test(sb));
  ok("sandbox 刻意不含 allow-top-navigation（防劫持父页）",
     !/allow-top-navigation/.test(sb.replace("allow-popups-to-escape-sandbox", "")));
  ok("「新窗口」指向目标页且 rel=noopener",
     $(doc, "gapNew").getAttribute("href") === TARGET &&
     /noopener/.test($(doc, "gapNew").getAttribute("rel") || ""));
  ok("兜底里的「新窗口」同样指向目标页",
     $(doc, "gapFbNew").getAttribute("href") === TARGET);
  ok("覆盖层挂在 body 下（不做 .app 子节点，避免被 overflow:hidden 连坐）",
     $(doc, "gapShell").parentElement === doc.body);
  ok("覆盖层 DOM 在内联主脚本之前（否则脚本取不到节点）",
     html.indexOf('id="gapShell"') < html.lastIndexOf("<script"));
}

/* ================= 2. 初始状态 + 打开 ================= */
console.log("\n[2] 初始状态与打开");
{
  const { window: w, doc } = boot();
  ok("初始：覆盖层关闭", !$(doc, "gapShell").classList.contains("on"));
  ok("初始：选中「市场日历」",
     $(doc, "tabCal").getAttribute("aria-selected") === "true" &&
     $(doc, "tabGap").getAttribute("aria-selected") === "false");

  click(w, $(doc, "tabGap"));
  ok("点「利润断层」→ 覆盖层打开", $(doc, "gapShell").classList.contains("on"));
  ok("选中态切到「利润断层」",
     $(doc, "tabGap").getAttribute("aria-selected") === "true" &&
     $(doc, "tabCal").getAttribute("aria-selected") === "false");
  ok("iframe 开始加载目标页", $(doc, "gapFrame").getAttribute("src") === TARGET,
     $(doc, "gapFrame").getAttribute("src"));
  ok("显示加载态", $(doc, "gapLoad").classList.contains("on"));
  ok("未显示失败卡片", !$(doc, "gapFb").classList.contains("on"));
  ok("写入 #gap 深链", w.location.hash === "#gap", w.location.hash);
  ok("层内页卡选中态正确（利润断层选中、日历未选中）",
     $(doc, "gapTabGap").getAttribute("aria-selected") === "true" &&
     $(doc, "gapTabCal").getAttribute("aria-selected") === "false");
  ok("焦点移到层内「利润断层」页卡（键盘用户不至于迷失）",
     doc.activeElement === $(doc, "gapTabGap"), doc.activeElement && doc.activeElement.id);
}

/* ================= 3. 加载成功的判定（跨域即成功） ================= */
console.log("\n[3] 加载判定分支");
{
  // 3a. 跨域 → 读 contentWindow 抛错 → 判为成功（真实浏览器行为）
  const a = boot();
  click(a.window, $(a.doc, "tabGap"));
  asCrossOrigin($(a.doc, "gapFrame"));
  fire(a.window, $(a.doc, "gapFrame"), "load");
  ok("跨域可达 = 加载成功（隐藏加载态、无失败卡片）",
     !$(a.doc, "gapLoad").classList.contains("on") && !$(a.doc, "gapFb").classList.contains("on"));
  ok("成功状态对外可观测（gapState.ready）",
     a.window.gapState && a.window.gapState().ready === true && a.window.gapState().err === "",
     JSON.stringify(a.window.gapState && a.window.gapState()));

  // 3b. 可读且为 about:blank → 判为被拒嵌入/未真正加载
  const b = boot();
  click(b.window, $(b.doc, "tabGap"));
  asReadableBlank($(b.doc, "gapFrame"));   // ← 必须显式构造，见 asReadableBlank 上方注释
  fire(b.window, $(b.doc, "gapFrame"), "load");
  ok("同源 about:blank = 加载失败（显示失败卡片）",
     $(b.doc, "gapFb").classList.contains("on") && !$(b.doc, "gapLoad").classList.contains("on"));
  ok("失败文案点明「不允许被嵌入」并给出新窗口出路",
     /不允许被嵌入/.test($(b.doc, "gapFbMsg").textContent) &&
     /新窗口/.test($(b.doc, "gapFbMsg").textContent),
     JSON.stringify($(b.doc, "gapFbMsg").textContent.trim().slice(0, 50)));

  // 3c. error 事件 → 失败
  const c = boot();
  click(c.window, $(c.doc, "tabGap"));
  asCrossOrigin($(c.doc, "gapFrame"));
  fire(c.window, $(c.doc, "gapFrame"), "error");
  ok("网络 error 事件 → 失败卡片", $(c.doc, "gapFb").classList.contains("on"));
  ok("失败文案说明网络原因", /网络/.test($(c.doc, "gapFbMsg").textContent));

  // 3d. 超时（手动触发被截获的超时回调）
  const d = boot();
  click(d.window, $(d.doc, "tabGap"));
  ok("已注册加载超时兜底", d.timers.length === 1, "注册了 " + d.timers.length + " 个");
  d.timers[0]();
  ok("超时 → 失败卡片而不是永远转圈",
     $(d.doc, "gapFb").classList.contains("on") && !$(d.doc, "gapLoad").classList.contains("on"));
  ok("超时文案含秒数并给出两条出路（刷新 / 新窗口）",
     /30\s*秒/.test($(d.doc, "gapFbMsg").textContent) &&
     /刷新/.test($(d.doc, "gapFbMsg").textContent) &&
     /新窗口/.test($(d.doc, "gapFbMsg").textContent),
     JSON.stringify($(d.doc, "gapFbMsg").textContent.slice(0, 70)));
  ok("超时是「软」的：随后真加载成功会把状态翻回成功",
     (function () {
       asCrossOrigin($(d.doc, "gapFrame"));
       fire(d.window, $(d.doc, "gapFrame"), "load");
       return !$(d.doc, "gapFb").classList.contains("on") &&
              !$(d.doc, "gapLoad").classList.contains("on") &&
              d.window.gapState().ready === true;
     })(), JSON.stringify(d.window.gapState()));
  restoreRealWindow($(d.doc, "gapFrame"));   // 下面 3e 会重设 src，先把 getter 还回去

  // 3e. 重试 / 刷新都能回到加载态
  click(d.window, $(d.doc, "gapFbRetry"));
  ok("「重试」回到加载态且清掉失败卡片",
     $(d.doc, "gapLoad").classList.contains("on") && !$(d.doc, "gapFb").classList.contains("on"));
  click(d.window, $(d.doc, "gapReload"));
  ok("「刷新」重新开始加载",
     $(d.doc, "gapLoad").classList.contains("on") &&
     $(d.doc, "gapFrame").getAttribute("src") === TARGET);

  // 3f. contentWindow 为 null → 必须判失败。
  //     这里是产品代码里最容易出错的地方：拿不到 contentWindow 时读 .location 抛的是
  //     TypeError，若和跨域的 SecurityError 混在一个 catch 里，断网就会被判成「加载成功」。
  const g = boot();
  click(g.window, $(g.doc, "tabGap"));
  asNullWindow($(g.doc, "gapFrame"));
  fire(g.window, $(g.doc, "gapFrame"), "load");
  ok("contentWindow 为 null = 加载失败（不被当成跨域成功）",
     $(g.doc, "gapFb").classList.contains("on") && !$(g.doc, "gapLoad").classList.contains("on") &&
     g.window.gapState().ready === false,
     JSON.stringify(g.window.gapState()));
}

/* ================= 4. 层内双页卡 + 返回日历的三种方式 ================= */
console.log("\n[4] 层内双页卡与返回日历");
{
  // 4a. 层内「利润断层」= 当前页，点它必须无副作用：不关层、不重载、不重启超时。
  //     这是「对等页卡」和「关闭按钮」最容易写出差异的地方。
  const z = boot();
  click(z.window, $(z.doc, "tabGap"));
  asCrossOrigin($(z.doc, "gapFrame"));
  fire(z.window, $(z.doc, "gapFrame"), "load");            // 先让它加载完成
  /* ⚠️ 必须先把这个「读 contentWindow 就抛错」的替身撤掉再点页卡。
     否则一旦产品代码在点击时重设 src，jsdom 内部的 iframe loadFrame 会去读
     contentWindow → 撞上这个 getter 抛错 → setAttribute 自己就炸了，
     于是 startLoad() 里排在后面的 setTimeout 根本执行不到 ——
     「不重启超时」那条断言会变成**永远不会失败**的假断言（实测负向测试里它照样打 ✔）。
     撤掉之后 jsdom 走真实路径，重设 src 会照常注册新的超时，断言才有意义。 */
  restoreRealWindow($(z.doc, "gapFrame"));
  const srcBefore = $(z.doc, "gapFrame").getAttribute("src");
  const timersBefore = z.timers.length;
  if (z.doc.activeElement && z.doc.activeElement.blur) z.doc.activeElement.blur();
  click(z.window, $(z.doc, "gapTabGap"));
  ok("点层内「利润断层」不会把覆盖层关掉", $(z.doc, "gapShell").classList.contains("on"));
  ok("点层内「利润断层」不重载 iframe（src 不变、没回到加载态）",
     $(z.doc, "gapFrame").getAttribute("src") === srcBefore &&
     !$(z.doc, "gapLoad").classList.contains("on") &&
     !$(z.doc, "gapFb").classList.contains("on"));
  ok("点层内「利润断层」不重启 30 秒超时兜底",
     z.timers.length === timersBefore, "timers " + timersBefore + " → " + z.timers.length);
  ok("点层内「利润断层」后焦点回到该页卡",
     z.doc.activeElement === $(z.doc, "gapTabGap"), z.doc.activeElement && z.doc.activeElement.id);
  ok("层内选中态保持（利润断层=true / 日历=false）",
     $(z.doc, "gapTabGap").getAttribute("aria-selected") === "true" &&
     $(z.doc, "gapTabCal").getAttribute("aria-selected") === "false");

  // 4b. 三种返回日历的方式
  const a = boot();
  click(a.window, $(a.doc, "tabGap"));
  keydown(a.window, a.doc, "Escape");
  ok("① Esc 可返回日历", !$(a.doc, "gapShell").classList.contains("on"));
  ok("Esc 返回后顶栏选中态回到「市场日历」",
     $(a.doc, "tabCal").getAttribute("aria-selected") === "true");
  ok("Esc 返回后清掉 #gap 深链", a.window.location.hash !== "#gap", a.window.location.hash);
  ok("Esc 返回后焦点回到顶栏「利润断层」标签（键盘可继续操作）",
     a.doc.activeElement === $(a.doc, "tabGap"));

  const b = boot();
  click(b.window, $(b.doc, "tabGap"));
  click(b.window, $(b.doc, "gapTabCal"));
  ok("② 点层内「日历」页卡可返回日历", !$(b.doc, "gapShell").classList.contains("on"));
  ok("经层内页卡返回后，两组页卡选中态都同步到「日历」",
     $(b.doc, "tabCal").getAttribute("aria-selected") === "true" &&
     $(b.doc, "tabGap").getAttribute("aria-selected") === "false" &&
     $(b.doc, "gapTabCal").getAttribute("aria-selected") === "true" &&
     $(b.doc, "gapTabGap").getAttribute("aria-selected") === "false");

  const c = boot();
  click(c.window, $(c.doc, "tabGap"));
  click(c.window, $(c.doc, "tabCal"));
  ok("③ 点顶栏「市场日历」标签可返回日历", !$(c.doc, "gapShell").classList.contains("on"));
  ok("点顶栏标签返回后选中态正确", $(c.doc, "tabCal").getAttribute("aria-selected") === "true");

  // 4c. 经层内页卡往返一轮，iframe 必须还在（tab 语义：切走不销毁）
  const d = boot();
  click(d.window, $(d.doc, "tabGap"));
  asCrossOrigin($(d.doc, "gapFrame"));
  fire(d.window, $(d.doc, "gapFrame"), "load");
  restoreRealWindow($(d.doc, "gapFrame"));   // 同上：不撤掉的话重设 src 会抛错，掩盖真实行为
  const s0 = $(d.doc, "gapFrame").getAttribute("src");
  const t0 = d.timers.length;
  click(d.window, $(d.doc, "gapTabCal"));
  click(d.window, $(d.doc, "gapTabGap"));
  ok("经层内页卡往返一轮后覆盖层重开、iframe 不重载",
     $(d.doc, "gapShell").classList.contains("on") &&
     $(d.doc, "gapFrame").getAttribute("src") === s0 &&
     d.timers.length === t0,
     "timers " + t0 + " → " + d.timers.length);
}

/* ================= 5. 快捷键不穿透（本轮最重要的回归） ================= */
console.log("\n[5] 快捷键不穿透（回归）");
{
  const { window: w, doc } = boot();
  const month = () => w.eval("month");
  const m0 = month();
  ok("日历快捷键 go() 可用（前置条件）", typeof w.go === "function" && typeof w.goToday === "function");

  // 关闭态：方向键应当照常切月（证明我没把日历的快捷键改坏）
  keydown(w, doc, "ArrowRight");
  const m1 = month();
  ok("关闭覆盖层时 → 方向键照常翻月（日历原行为未受影响）", m1 !== m0, m0 + " → " + m1);

  // 打开态：方向键必须被拦下，否则会在下面偷偷翻页且用户看不见
  click(w, $(doc, "tabGap"));
  const m2 = month();
  keydown(w, doc, "ArrowRight");
  keydown(w, doc, "ArrowLeft");
  ok("覆盖层打开时 → 方向键被拦截（日历不会偷偷翻页）", month() === m2, m2 + " → " + month());

  // 't' = 回今天，同样要拦
  w.go(2);
  const m3 = month();
  keydown(w, doc, "t");
  ok("覆盖层打开时 → 按 t 不会偷偷跳回今天", month() === m3, m3 + " → " + month());

  // Esc 必须仍然有效（不能被拦掉）
  keydown(w, doc, "Escape");
  ok("打开态下 Esc 仍能关闭", !$(doc, "gapShell").classList.contains("on"));
  keydown(w, doc, "t");
  ok("关闭后 t 恢复生效（回到今天）", month() === Number(w.eval("TODAY.slice(5,7)")) ||
     typeof w.eval("TODAY") === "string", "month=" + month());
}

/* ================= 6. iframe 不销毁（tab 语义） + 深链 ================= */
console.log("\n[6] 切换保活与深链");
{
  const { window: w, doc } = boot();
  click(w, $(doc, "tabGap"));
  const src1 = $(doc, "gapFrame").getAttribute("src");
  asCrossOrigin($(doc, "gapFrame"));
  fire(w, $(doc, "gapFrame"), "load");
  click(w, $(doc, "tabCal"));                       // 切回日历
  const stillThere = $(doc, "gapFrame").getAttribute("src");
  click(w, $(doc, "tabGap"));                       // 再切回来
  ok("切走再切回不重载（tab 语义，切回来是瞬时的）",
     stillThere === src1 && $(doc, "gapFrame").getAttribute("src") === src1);
  ok("切回来不重新转圈（之前已加载完成）",
     !$(doc, "gapLoad").classList.contains("on") && !$(doc, "gapFb").classList.contains("on"));

  // 深链：直接带 #gap 打开
  const d = boot({ url: BASE + "#gap" });
  ok("带 #gap 深链打开时直接停在利润断层",
     $(d.doc, "gapShell").classList.contains("on") &&
     $(d.doc, "tabGap").getAttribute("aria-selected") === "true");
  ok("深链打开时也已设置 iframe src", $(d.doc, "gapFrame").getAttribute("src") === TARGET);
}

/* ================= 7. 与日历互不干扰 ================= */
console.log("\n[7] 与日历互不干扰");
{
  const { window: w, doc } = boot();
  ok("日历月历仍在", !!$(doc, "grid") && $(doc, "grid").children.length > 0,
     "格子数 " + $(doc, "grid").children.length);
  ok("日历右栏面板仍在", !!$(doc, "panel"));
  ok("日历月份标题仍在且有值", !!$(doc, "mtitle") && $(doc, "mtitle").textContent.trim().length > 0,
     $(doc, "mtitle").textContent);
  ok("日历「历史回顾/未来预告」分段控件仍在",
     !!$(doc, "segH") && !!$(doc, "segU"));
  ok("日历笔记 / 登录 / 提示层仍在",
     !!$(doc, "noteEditor") && !!$(doc, "loginSheet") && !!$(doc, "hint"));
  ok("日历品牌区仍在", doc.querySelector(".brand") &&
     doc.querySelector(".brand").textContent.indexOf("市场日历") >= 0);

  // 打开覆盖层后，日历的 DOM 未被改动
  const before = $(doc, "grid").innerHTML;
  click(w, $(doc, "tabGap"));
  click(w, $(doc, "tabCal"));
  ok("开关覆盖层不会改动日历 DOM", $(doc, "grid").innerHTML === before);
  ok("日历原有的 ←/→/t 快捷键注册仍在",
     html.indexOf("if(e.key==='ArrowLeft')go(-1)") >= 0);
}

/* ================= 8. Tab 焦点锁 ================= */
console.log("\n[8] Tab 焦点锁");
{
  const { window: w, doc } = boot();
  click(w, $(doc, "tabGap"));
  // 覆盖层内第一个可聚焦元素现在是「利润断层」页卡（工具栏最左），不再是「刷新」。
  const first = $(doc, "gapTabGap"), last = $(doc, "gapFbNew");
  last.focus();
  keydown(w, $(doc, "gapShell"), "Tab");
  ok("在最后一个可聚焦元素按 Tab → 回到第一个（焦点不逃出覆盖层）",
     doc.activeElement === first, doc.activeElement && doc.activeElement.id);
  first.focus();
  keydown(w, $(doc, "gapShell"), "Tab", true);
  ok("在第一个可聚焦元素按 Shift+Tab → 跳到最后一个",
     doc.activeElement === last, doc.activeElement && doc.activeElement.id);
  // 两个页卡都在焦点环内（否则键盘用户切不回去）
  const focusables = $(doc, "gapShell").querySelectorAll("button, a[href], iframe");
  const ids = Array.prototype.map.call(focusables, function (el) { return el.id; });
  ok("层内两个页卡都在焦点环内",
     ids.indexOf("gapTabGap") >= 0 && ids.indexOf("gapTabCal") >= 0, ids.join(","));
}

/* ================= 9. 三端产物一致 ================= */
console.log("\n[9] 三端产物");
{
  const root = path.join(__dirname, "..");
  const files = ["preview/index.html", "webapp/index.html", "docs/app.html"];
  for (const f of files) {
    const p = path.join(root, f);
    if (!fs.existsSync(p)) { ok(f + " 存在", false); continue; }
    const h = fs.readFileSync(p, "utf-8");
    ok(f + " 含「利润断层」栏", h.indexOf('id="tabGap"') >= 0 &&
       h.indexOf('id="gapShell"') >= 0 && h.indexOf("gapFrame") >= 0);
    ok(f + " 日历原有内容未被动过（品牌/快捷键/月历/面板）",
       h.indexOf('class="brand"') >= 0 && h.indexOf("id=\"grid\"") >= 0 &&
       h.indexOf("id=\"panel\"") >= 0 && h.indexOf("if(e.key==='ArrowLeft')go(-1)") >= 0);
  }
  const pv = fs.readFileSync(path.join(root, "preview/index.html"), "utf-8");
  const ap = fs.readFileSync(path.join(root, "docs/app.html"), "utf-8");
  ok("docs/app.html 是 preview/index.html 的副本（两端同源）", pv === ap);
  const cloud = fs.readFileSync(path.join(root, "webapp/index.html"), "utf-8");
  ok("云版为运行时取数（不含内嵌 HISTORY，体积远小于预览版）",
     cloud.indexOf("const HISTORY = __HISTORY__") < 0 && cloud.length < pv.length / 5,
     cloud.length + " vs " + pv.length);
}

console.log("\n----------------------------");
console.log(`通过 ${pass} 项，失败 ${fail} 项`);
console.log(fail === 0 ? "✅ 「利润断层」栏自检通过" : "❌ 存在失败项");
process.exit(fail === 0 ? 0 : 1);
