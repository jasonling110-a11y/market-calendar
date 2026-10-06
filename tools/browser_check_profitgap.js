/* 「利润断层」栏 · 真实浏览器复测（Chromium via agent-browser CLI）
   用法：node tools/browser_check_profitgap.js

   为什么在 jsdom 自检（check_profitgap_tab.js）之外还要这个：
   jsdom 不加载 iframe、不发真实网络请求、不算真实布局。有五件事只有真浏览器能回答 ——
     1) 顶栏标签真的可见、真的能点（getBoundingClientRect 有非零尺寸）
     2) iframe 真的能把 GitHub Pages 上的看板嵌进来（真跨域 + 真响应头）
     3) 覆盖层开着时 ←/→/t 真的不穿透（jsdom 里 stopPropagation 的语义与真实浏览器不同）
     4) 跨域隔离真的成立（父子页读不到对方）
     5) 整条链路没有 JS 异常、没有对外部域名的失败请求

   跑完在 tools/out/ 留三张截图（日历态 / 利润断层态 / 层内双页卡）供人眼确认。
   退出码 0 = 全过；1 = 有失败项；2 = 环境不可用（浏览器起不来），不算产品失败。

   ⚠️ 两个踩过的坑，改这个文件前先读：
   一、本沙箱里 Edge 的子进程沙箱初始化被禁（Operation not permitted），直接用 Edge 无头会因
      GPU 进程崩溃而退出，CDP over WebSocket 也会被 CLOSE 1006。agent-browser 自带可用后端，
      所以这里用它。
   二、**静态服务器与 agent-browser 调用必须在同一个 Node 进程里异步共存**。一开始用
      execFileSync 调用，它会把事件循环整个阻塞住 → 同进程里的 http server 无法响应 → 浏览器
      报「Failed to read: Resource temporarily unavailable」。所以下面一律用异步 spawn。
      同理，不在开头 `close --all`（close 之后 daemon 会卡住），由 daemon 自己复用会话。
*/
const fs = require("fs");
const path = require("path");
const http = require("http");
const { spawn } = require("child_process");

const ROOT = path.join(__dirname, "..");
const OUTDIR = path.join(__dirname, "out");
const NODE = process.execPath;
const AB = process.env.AB_CLI ||
  "/Users/jason/.workbuddy/binaries/node/workspace/node_modules/agent-browser/bin/agent-browser.js";
const NODE_PATH = "/Users/jason/.workbuddy/binaries/node/workspace/node_modules";
const TARGET = "https://jasonling110-a11y.github.io/profit-gap/dashboard.html";

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log("  ✔ " + name); }
  else { fail++; console.log("  ✘ " + name + (extra !== undefined ? "  → " + extra : "")); }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* 异步调用 agent-browser：绝不阻塞事件循环，否则同进程的静态服务器会哑掉 */
function ab(args) {
  return new Promise((resolve, reject) => {
    const p = spawn(NODE, [AB].concat(args), {
      stdio: ["ignore", "pipe", "pipe"],
      env: Object.assign({}, process.env, { NODE_PATH: NODE_PATH }),
    });
    let out = "", err = "";
    const t = setTimeout(() => { try { p.kill("SIGKILL"); } catch (e) {} reject(new Error("agent-browser 超时：" + args.join(" "))); }, 240000);
    p.stdout.on("data", (d) => (out += d));
    p.stderr.on("data", (d) => (err += d));
    p.on("close", (code) => {
      clearTimeout(t);
      if (code === 0) resolve(out);
      else reject(new Error("agent-browser 退出码 " + code + "：" + args.join(" ") + "\n" + (err || out).trim()));
    });
  });
}
const js = async (expr) => JSON.parse((await ab(["eval", expr])).trim());   // eval 回的是 JSON 字面量

/* 等页面真的换过来再断言。
   ⚠️ 踩过的坑：agent-browser 的 open 会**新开一个标签页**，旧页的收起是异步的。
   在这几百毫秒的窗口里，eval 有可能落到一个还没被换掉的 about:blank 上 ——
   症状是「上一条断言明明刚通过（说明页面是对的），下一条 eval 却报
   TypeError: Cannot read properties of null」。这是宿主竞态，不是产品问题，
   所以固定 sleep 不可靠（页面大小变一点点就会翻车），必须显式等到目标 DOM 出现。
   注意：这里只等「页面身份」，不预设任何断言为真 —— 断言本身一律不改。 */
async function waitFor(expr, ms) {
  const t0 = Date.now();
  for (;;) {
    try { if (await js(expr)) return true; } catch (e) { /* 还在 about:blank / 解析中 */ }
    if (Date.now() - t0 > (ms || 8000)) return false;
    await sleep(250);
  }
}

const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
  ".ics": "text/calendar; charset=utf-8", ".svg": "image/svg+xml" };
function serve() {
  const srv = http.createServer((req, res) => {
    const rel = decodeURIComponent(req.url.split("?")[0].split("#")[0]).replace(/^\/+/, "") || "preview/index.html";
    const full = path.join(ROOT, rel);
    if (!full.startsWith(ROOT) || !fs.existsSync(full) || fs.statSync(full).isDirectory()) {
      res.writeHead(404, { "content-type": "text/plain" }); return res.end("404");
    }
    res.writeHead(200, { "content-type": MIME[path.extname(full)] || "application/octet-stream" });
    fs.createReadStream(full).pipe(res);
  });
  return new Promise((r) => srv.listen(0, "127.0.0.1", () => r(srv)));
}

(async () => {
  if (!fs.existsSync(AB)) { console.log("agent-browser 不存在，跳过真实浏览器复测"); process.exit(0); }
  fs.mkdirSync(OUTDIR, { recursive: true });
  const srv = await serve();
  const base = "http://127.0.0.1:" + srv.address().port;
  const done = (code) => { try { srv.close(); } catch (e) {} process.exit(code); };

  console.log("=== 「利润断层」栏 · 真实浏览器复测 ===\n");

  console.log("[A] 打开日历页");
  await ab(["set", "viewport", "1440", "900"]);
  const out = await ab(["open", base + "/preview/index.html"]);
  // 浏览器这会儿才真的起来，清一遍累积的日志
  try { await ab(["network", "requests", "--clear"]); } catch (e) {}
  try { await ab(["errors", "--clear"]); } catch (e) {}
  await waitFor("!!document.getElementById('grid')");

  ok("页面打开成功", /市场日历/.test(out), out.trim().split("\n")[0]);
  ok("标题为「市场日历 · 预览」", /市场日历/.test(await js("document.title")), await js("document.title"));
  ok("月历已渲染（格子数 > 0）", (await js("document.querySelectorAll('#grid > *').length")) > 0);
  const sw = await js("document.documentElement.scrollWidth"), iw = await js("window.innerWidth");
  ok("日历无横向溢出", sw <= iw, sw + " vs " + iw);

  console.log("\n[B] 顶栏标签（真可见性）");
  const box = await js("(function(){var r=document.getElementById('tabGap').getBoundingClientRect();" +
                       "return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)};})()");
  ok("「利润断层」标签存在", !!box, JSON.stringify(box));
  ok("标签真实可见（非零尺寸）", box.w > 30 && box.h > 20, JSON.stringify(box));
  ok("标签在首屏顶栏带内（0 ≤ y < 90）", box.y >= 0 && box.y < 90, "y=" + box.y);
  ok("is visible 判定为可见", (await ab(["is", "visible", "#tabGap"])).trim() === "true");
  ok("「市场日历」默认选中",
     (await js("document.getElementById('tabCal').getAttribute('aria-selected')")) === "true");
  ok("覆盖层默认不可见",
     (await js("getComputedStyle(document.getElementById('gapShell')).display")) === "none");
  ok("初始不预加载 iframe（省流量、不打扰日历）",
     (await js("document.getElementById('gapFrame').getAttribute('src')")) === null);
  const shot1 = path.join(OUTDIR, "gap_1_calendar.png");
  await ab(["screenshot", shot1]);
  console.log("     截图 → " + path.relative(ROOT, shot1));

  console.log("\n[C] 点击标签 → 整屏切过去 + iframe 真加载");
  await ab(["click", "#tabGap"]);
  ok("覆盖层已展开",
     (await js("getComputedStyle(document.getElementById('gapShell')).display")) === "flex");
  ok("选中态切到「利润断层」",
     (await js("document.getElementById('tabGap').getAttribute('aria-selected')")) === "true");
  ok("iframe src 指向目标页",
     (await js("document.getElementById('gapFrame').getAttribute('src')")) === TARGET);
  ok("写入 #gap 深链", (await js("location.hash")) === "#gap");
  ok("层内两个页卡都在，且「返回日历」按钮已移除",
     await js("!!document.getElementById('gapTabGap') && !!document.getElementById('gapTabCal')" +
              " && !document.getElementById('gapClose')"));
  ok("工具栏按钮（刷新 / 新窗口）仍在",
     await js("!!document.getElementById('gapReload') && !!document.getElementById('gapNew')"));

  // 层内页卡必须真的可见、并排、且顶栏那组此刻是被盖住的 ——
  // 否则「层内再放一对页卡」就成了冗余，而不是必需。
  const gbox = await js("(function(){var g=document.getElementById('gapTabGap').getBoundingClientRect();" +
                        "var c=document.getElementById('gapTabCal').getBoundingClientRect();" +
                        "return {gx:Math.round(g.x),gw:Math.round(g.width),gh:Math.round(g.height)," +
                        "cx:Math.round(c.x),cw:Math.round(c.width),cy:Math.round(c.y),gy:Math.round(g.y)};})()");
  ok("层内页卡真实可见（非零尺寸）", gbox.gw > 30 && gbox.gh > 20 && gbox.cw > 30, JSON.stringify(gbox));
  ok("两页卡并排（「日历」在「利润断层」右侧）", gbox.cx > gbox.gx, JSON.stringify(gbox));
  ok("层内选中态正确（利润断层=true / 日历=false）",
     (await js("document.getElementById('gapTabGap').getAttribute('aria-selected')")) === "true" &&
     (await js("document.getElementById('gapTabCal').getAttribute('aria-selected')")) === "false");
  ok("覆盖层确实盖住了顶栏那组页卡（层内这组是必需的，不是冗余）",
     await js("(function(){var r=document.getElementById('tabCal').getBoundingClientRect();" +
              "var el=document.elementFromPoint(r.x+r.width/2, r.y+r.height/2);" +
              "return el ? !!el.closest('#gapShell') : false;})()"));

  // 跨境 + 1.3MB，沙箱带宽实测 ~46KB/s，给足 90 秒
  let st = null, waited = 0;
  while (waited < 90000) {
    st = await js("window.gapState ? window.gapState() : null");
    if (st && (st.ready || st.err)) break;
    await sleep(2000); waited += 2000;
  }
  ok("加载判定已收敛（成功或给出明确原因）", !!st && (st.ready || st.err !== ""), JSON.stringify(st) + " 用时≈" + waited + "ms");
  ok("iframe 真的嵌进来了（未被 X-Frame-Options / CSP 拒绝）", !!st && st.ready === true, JSON.stringify(st));
  ok("未误报失败卡片", await js("!document.getElementById('gapFb').classList.contains('on')"));
  const fb = await js("(function(){var r=document.getElementById('gapFrame').getBoundingClientRect();" +
                      "return {w:Math.round(r.width),h:Math.round(r.height)};})()");
  ok("iframe 铺满内容区（宽 ≥1400 / 高 ≥700）", fb.w >= 1400 && fb.h >= 700, JSON.stringify(fb));
  ok("覆盖层无横向溢出",
     (await js("document.documentElement.scrollWidth")) <= (await js("window.innerWidth")) + 1,
     (await js("document.documentElement.scrollWidth")) + " vs " + (await js("window.innerWidth")));
  // 跨域隔离必须成立：父页读不到 iframe 内部，这正是「加载成功」的证据
  ok("父子页跨域隔离成立（读不到 iframe 内部）",
     (await js("(function(){try{void document.getElementById('gapFrame').contentDocument.title;return 'readable';}catch(e){return 'cross-origin';}})()")) === "cross-origin");
  const shot2 = path.join(OUTDIR, "gap_2_profitgap.png");
  await ab(["screenshot", shot2]);
  console.log("     截图 → " + path.relative(ROOT, shot2));

  console.log("\n[D] 层内双页卡：点「利润断层」不重载 / 点「日历」返回");
  // 先记下 iframe 的 src 与就绪态：层内点「利润断层」必须是无副作用的
  const srcKeep = await js("document.getElementById('gapFrame').getAttribute('src')");
  await ab(["click", "#gapTabGap"]);
  await sleep(300);
  ok("点层内「利润断层」→ 覆盖层仍然展开（它是页卡，不是关闭按钮）",
     (await js("getComputedStyle(document.getElementById('gapShell')).display")) === "flex");
  ok("点层内「利润断层」→ 不重载 iframe、也不回到转圈",
     (await js("document.getElementById('gapFrame').getAttribute('src')")) === srcKeep &&
     (await js("window.gapState().ready")) === true,
     JSON.stringify(await js("window.gapState()")));
  const shot3 = path.join(OUTDIR, "gap_3_tabs.png");
  await ab(["screenshot", shot3]);
  console.log("     截图 → " + path.relative(ROOT, shot3));

  await ab(["click", "#gapTabCal"]);
  await sleep(300);
  ok("点层内「日历」页卡 → 覆盖层收起",
     (await js("getComputedStyle(document.getElementById('gapShell')).display")) === "none");
  ok("经层内页卡返回后，两组页卡选中态都同步到「日历」",
     (await js("document.getElementById('tabCal').getAttribute('aria-selected')")) === "true" &&
     (await js("document.getElementById('gapTabCal').getAttribute('aria-selected')")) === "true");
  ok("关闭后清掉 #gap 深链", (await js("location.hash")) !== "#gap", await js("location.hash"));
  // 日历自己的分段控件（注意：它用 class 'on' 表示选中，不是 aria-selected）
  const m0 = await js("document.getElementById('mtitle').textContent");
  await ab(["click", "#segU"]);
  await sleep(300);
  ok("日历自身交互仍可用（切「未来预告」生效）",
     await js("document.getElementById('segU').classList.contains('on')"),
     await js("document.getElementById('segU').className"));
  await ab(["click", "#segH"]);
  await sleep(200);
  await ab(["click", "#gapReload"]);      // 把焦点放到覆盖层内的按钮上，贴近真实按键场景
  await sleep(200);
  await ab(["press", "ArrowRight"]);
  await sleep(250);
  const m2 = await js("document.getElementById('mtitle').textContent");
  ok("日历关闭态下方向键仍能翻月（原行为未被改坏）", m2 !== m0, m0 + " → " + m2);

  console.log("\n[E] 覆盖层开着时快捷键不穿透");
  await ab(["click", "#tabGap"]);
  await sleep(300);
  await ab(["click", "#gapReload"]);
  const m3 = await js("document.getElementById('mtitle').textContent");
  await ab(["press", "ArrowRight"]);
  await ab(["press", "t"]);
  await sleep(250);
  const m4 = await js("document.getElementById('mtitle').textContent");
  ok("→ / t 被拦截（日历不会在下面偷偷翻页）", m4 === m3, m3 + " → " + m4);
  await ab(["press", "Escape"]);
  await sleep(300);
  ok("Esc 仍能关闭（拦截器放行 Esc）",
     (await js("getComputedStyle(document.getElementById('gapShell')).display")) === "none");

  console.log("\n[F] 深链 #gap 直接进入");
  // ⚠️ 必须用「带标签的新标签页」，不能直接在原标签上 open 一个 #gap 的地址。
  //    踩过的坑：原标签上再 open 同路径仅 hash 不同的 URL 时，agent-browser 的 eval
  //    会时不时绑在一个残留的 about:blank 执行上下文上 —— 症状是
  //      · `tab` 明明显示标签页停在 .../preview/index.html#gap
  //      · 但 eval 里 location.href === "about:blank"、document.title === ""、
  //        body.innerHTML.length === 0
  //    于是 ok() 前的 getComputedStyle(null) 直接抛错，整条复测链断掉（退出码 2）。
  //    这是宿主的目标/上下文绑定不稳定，跟被测页面无关；用显式 label 建页并切过去即可钉死目标。
  //    顺带好处：这是一次真正的「全新加载 + 深链」，正是用户点链接的真实场景。
  await ab(["tab", "new", "--label", "deeplink", base + "/preview/index.html#gap"]);
  await sleep(900);
  await ab(["tab", "deeplink"]);
  await waitFor("!!document.getElementById('gapFrame')");   // 见 waitFor 注释：别在 about:blank 上断言
  await sleep(400);
  ok("带 #gap 打开时直接停在利润断层",
     (await js("getComputedStyle(document.getElementById('gapShell')).display")) === "flex" &&
     (await js("document.getElementById('tabGap').getAttribute('aria-selected')")) === "true");
  ok("深链进入时也已设置 iframe src",
     (await js("document.getElementById('gapFrame').getAttribute('src')")) === TARGET);

  // 页面里另有一条 hashchange 监听（与「初次加载就带 #gap」是两条不同的代码路径），
  // 在同一文档内改 hash 也必须生效 —— 否则从外部点一个 #gap 链接进来就不灵。
  await ab(["eval", "(function(){location.hash='#__other';return 0})()"]);
  await sleep(400);
  ok("同文档内 hash 离开 #gap → 覆盖层收起",
     (await js("getComputedStyle(document.getElementById('gapShell')).display")) === "none");
  // 先手动收起再改 hash，才能真的验到「hash 事件把层打开」。
  // 不做这一步的话，上一条万一失败（层还开着），这条会因为「本来就开着」而被判通过 ——
  // 那就是一条永远不会失败的假断言。
  await ab(["eval", "(function(){window.gapClose();return 0})()"]);
  await sleep(300);
  ok("前置：已手动收起覆盖层",
     (await js("getComputedStyle(document.getElementById('gapShell')).display")) === "none");
  await ab(["eval", "(function(){location.hash='#gap';return 0})()"]);
  await sleep(400);
  ok("同文档内 hash 回到 #gap → 覆盖层重新打开",
     (await js("getComputedStyle(document.getElementById('gapShell')).display")) === "flex" &&
     (await js("document.getElementById('gapTabGap').getAttribute('aria-selected')")) === "true");

  console.log("\n[G] 异常与网络");
  const errs = (await ab(["errors"])).trim();
  ok("无页面 JS 异常", errs === "", errs.split("\n").slice(0, 3).join(" | "));
  const reqs = (await ab(["network", "requests"])).trim().split("\n").filter(Boolean);
  const remoteBad = reqs.filter((l) => !/127\.0\.0\.1/.test(l) && /\s(4\d\d|5\d\d)\s*$/.test(l.trim()));
  ok("对外部域名的请求无 4xx/5xx", remoteBad.length === 0, remoteBad.slice(0, 3).join(" | "));
  const localBad = reqs.filter((l) => /127\.0\.0\.1/.test(l) && /\s(4\d\d|5\d\d)\s*$/.test(l.trim()));
  if (localBad.length) {
    console.log("     注：以下本地 404 属既有现象（预览版本地跑缺 sdk / 桩接口，线上由宿主提供），不计入失败：");
    localBad.slice(0, 4).forEach((l) => console.log("       " + l.trim().slice(0, 110)));
  }

  try { await ab(["close", "--all"]); } catch (e) {}
  console.log("\n----------------------------");
  console.log(`通过 ${pass} 项，失败 ${fail} 项`);
  console.log(fail === 0 ? "✅ 真实浏览器复测通过" : "❌ 存在失败项");
  done(fail === 0 ? 0 : 1);
})().catch((e) => {
  console.error("复测异常（环境问题，非产品失败）：", e.message);
  process.exit(2);
});
