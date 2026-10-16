# 自动化 memory — 市场日历每日更新（automation-1790493311576）

## 执行摘要（最新：2026-10-16 22:0x · **全流程收敛，推送成功**）
- **B 站要点：本次 0 新增**。今日视频 `BV1SSJX6EEAX` 2026-10-16「10.16 沃什今天在IMF上最想表达的是什么」
  **已在本轮之前入库**（commit `c2e0177` 21:35，12 条要点，无 `auto` 标记 = AI 正式版，非兜底）。
  我复核了 12 条与转写（1411 字）逐条对齐，准确无误 → 未改动。要点库维持 **39 条 / 32 天 / 474 要点**。
  主题：沃什借 IMF 年会公开为美联储改革做说明/辩护/动员——成立五个工作组、定性任务为「创造新的治理资本」、
  以外部视角「外包治理」绕开内部智库；批评内部文化（过度前瞻指引/点阵图依赖/沟通噪音）；主张主席「全机构 CEO 式」
  全面领导（点出 75% 员工不直接做货币政策）；用 2006—2011 任理事经历预扫「你不懂」的阻力；整合为改革必要性、
  沟通风格将变、权力与经验三条信息。**未回应通胀/就业/下次议息**。
- ⚠️ **本轮是「补跑 + 收尾」性质**：进入时本地已有 21:35/21:52 两次更早的提交，`up_summary` 已达 39 条。
  这与 10-13 记的「workbench 抢跑」吻合；**再次印证别拿 HEAD sha 当判据**。
- ✅ **推送成功**：`origin/main` 从 **f9c33f7（10-14）→ 498e3fe（今日 21:56，Actions/workbench）→ d6b7d60（我推）**。
  即**一次性补上了 10-15 那次未成功的推送**。packfile fast-forward 通道 3 秒完成，`http.lowSpeedLimit=4000 /
  lowSpeedTime=40` 足够兜住抖动。**本轮未出现「本次未抓到，沿用上次数据」**。
  收尾判据：109/109 tracked 文件 0 差异（`git diff origin/main` 为空）。
  ⚠️ 注意：`git hash-object` 对中文名 .md/.command **不经 clean 过滤器**，会误报 6 个「差异」
  （上线指南.md / 个人使用方案.md / 云端部署指南.md / 本地工作台.md / 两个 .command）。
  **必须用 `git diff origin/main` 复核**，为空即真收敛。
- 抓取：板块 3 天（10-14/15/16）/ 宏观 79 指标（成功 54、失败 0、19556 数据点）/ 日历 16541 → 7515 /
  ics 167 日程 / 本地 meta version=**202610162158**、up_videos=**39** / up_days=**32**。
- 线上已验证：Pages `data/meta.js` → version=**202610162158**、up_days=32 / up_videos=39；
  `data/history.js` 线上与本地 **sha256 完全一致**（`e52d11fc…`），含 BV1SSJX6EEAX 及其要点原文。
  ℹ️ Pages 首次请求返回过一次 GitHub「Unicorn!」500 页 —— **重试即 200，别误判未发布**。
  ℹ️ `data/up_summary.json` **不在 Pages 发布范围**（只有 docs/ 发布），线上核验要用 meta.js + history.js。
- 微信推送：无 PushPlus token → 未发送（预期内）。桌面 rsync 成功（39 条 / 474 要点 / 32 天）。
- 今日/明日：**10-16** 31 条、★★ 17 项、**★★★ 0**（重点：11:30 沃什 IMF 炉边谈话＝今日视频主题；
  17:00 欧元区 HICP/核心 CPI/贸易帐；21:15 美国工业产出/产能利用率）。
  **10-17（周六）** 6 条、★★ 1 项（李强访问乌兹别克斯坦）、无 ★★★。
- 💡 网络判据仍成立：`api.github.com=200` 即 API 通道可用（`github.com`、`google` 返 000 属正常分流）；
  本轮 `fred.stlouisfed.org` 也 **200**（10-15 那次是 000，导致宏观卡 8 分钟）。macOS **无 `timeout` 命令**。

## 执行摘要（历史：2026-10-15 23:0x · 数据/要点完成，**推送未成功（代理节点挂）**）
- **B 站要点：新增 2 个视频（22 条）** → 要点库 36 → **38 条**，覆盖 30 → **31 天**（总要点 440 → **462**）。
  两个都是我读转写后手写（**没有 auto 兜底残留**，up_pending 报「全部 38 个视频都已有要点总结」）：
  - `BV1SeJy64EFN` 2026-10-15「10.15 9月进出口 CPI PPI」13 条（转写 3279 字）
    主题：9 月出口 4471 亿美元、顺差 1335 亿创历史新高，但**靠价格不靠量**——集成电路出口 449 亿而数量仅 +0.9%、
    手机量 -12.5% 而单价 +31.5%（存储芯片占手机 BOM 由 10~15% 升到 30~40%）；原油日均进口 906 万桶、
    缺口 244 万桶/日、均价约 90 美元/桶（+32%）；CPI +0.9% 中汽油一项拉动 0.4pct（输入性通胀）；
    出厂 PPI +5% / 购进 PPI +6.9%、剪刀差 1.9pct、生活资料 -0.1%；结论「外强内弱」+ 必须加速提振内需。
  - `BV11jJr63E7E` 2026-10-15「10.15 Judy Shelton」9 条（转写 902 字）
    主题：贝森特请朱迪·谢尔顿（保守派／胡佛研究所／著《苏联的崩溃》《货币崩溃》／曾被提名美联储未过）
    当顾问**专责评估中国的金融与货币政策** → 判断中美货币汇率与金融博弈将由其主导、会加强提速全面升级。
- 管线 1~9 步全过：板块 3 天（含 10-15）/ 宏观 79 指标（成功 54、失败 0、19552 数据点）/ 日历 16519 → 7505 /
  ics 169 日程 / 预览 1572KB / 本地 meta version=**202610152219**、up_videos=**38** / up_days=**31**。
  **未出现**「本次未抓到，沿用上次数据」。
- 🚨 **代理节点挂（10-09、10-11 之后第 3 次）**：`baidu=200` 但 `google/github/raw.gh` 全 **000**，
  1082 在 LISTEN 但同样 000，DNS 解析到 fake-IP `198.18.0.49`。
  **影响面比前两次更广：FRED（fred.stlouisfed.org）也 000** → `fetch_macro.py` 的 15 个 FRED 序列
  各干等满 30s（`_fred_rows` 无代理 opener，TUN 下 TCP 能 ESTABLISHED 但无数据），第 4 步卡了约 8 分钟才过；
  **但结果仍是「成功 54 / 失败 0」，未触发沿用上次数据**。
- ⚠️ **`daily_update.sh` 第 10 步的 `git push` 没有任何超时 → 会无限挂住**（实测 git-remote-https 卡在 ESTABLISHED）。
  本轮处理：**只 kill 掉卡住的 `git push`**（脚本随后正常打印「流程结束」），把推送挪到网络恢复后自己做。
  → **建议给第 65 行的 `git push` 加超时**（如 `timeout 60 git ... push`，或设 `GIT_HTTP_LOW_SPEED_LIMIT/TIME`），
    否则每次代理挂都会让整条自动化无限期挂死。
- 推送：**未成功**。已连续探测约 1 小时（22:20 ~ 23:03，约 66 次）**全部 000**，节点始终未恢复。
  本地已 commit：`b0a5795`（脚本产物）、`c34df7e`（我重建后收尾）、`ac1453e`（记忆文件）；
  本地 `origin/main` 引用仍停在 **f9c33f7（2026-10-14 21:55）**。
  ➡️ **下次跑之前先补推**：网络恢复后按 packfile fast-forward 通道把当前 HEAD 推上去即可（数据已全部就绪）。
- 微信推送：无 PushPlus token → 未发送（预期内）。桌面 rsync 成功（38 条 / 462 要点 / 31 天）。
- 今日/明日：**10-15** 5 条、★★以上 5 项（★★★ 4：20:30 美国 PPI/核心 PPI；★★：22:30 EIA 原油库存）；
  关键数值：美国零售销售月率 **1.29%**（前值 -0.41%）。**10-16** 2 条、★★ 2 项（21:15 美国工业产出指数 环比／制造业环比）。

## 执行摘要（历史：2026-10-14 21:5x · **全流程收敛，推送成功**）
- **B 站要点：新增 2 个视频** → 要点库 34 → **36 条**，覆盖 29 → **30 天**（总要点 416 → **440**）。
  两个都是 `auto:true` 兜底入包的（up_pending 照旧报「无待办」，真待办仍看 auto 字段）：
  - `BV177pk63Emp` 2026-10-14「10.14 中期选举之前会不会有"黑天鹅"事件？」13 条（转写 2006 字）
    主题：判断 11/3 中期选举前特朗普很可能「提前动手」；压油价难度上升（打击原油走私/沙特胡塞战事/伊朗更强硬）；
    油价是决定动手时点的关键变量；中期选举≠选总统；马斯克捐 3.6 亿美元成共和党最大金主。
  - `BV1LXpm6QE5K` 2026-10-14「10.14  面对金融 首先是尊重」11 条（转写 665 字）
    主题：CPI/核心 CPI 双超预期（事前已判断不乐观）；一组小数据即引发美元/黄金/美债剧烈波动；
    金融影响力是几十年上百年形成的，要「尊重」、非一蹴而就。
- ✅ **重大发现：`git push` 其实可用**。之前判「永久不可用」是误判——真实原因只是本地/远端双历史的
  `non-fast-forward`。正解：`git fetch origin main:refs/remotes/origin/main` → `git write-tree` →
  `git commit-tree <tree> -p <remote_head>` → `git push origin "${c}:refs/heads/main"`（fast-forward）。
  **packfile 经 zlib 压缩，天然绕开「>256KB 原始请求体被丢弃」的坑**，比 push_via_api 逐 blob 重试稳得多。
  ⚠️ zsh 里必须写 `"${c}:refs/..."`（`$c:refs` 会被当 `:r` 修饰符）。
- 本轮 API 通道（对照）：小文件 7 个一批成功；大文件逐个重试——history.js 第2次、calendar.json 第3次、
  macro_series.json 第4次、up_raw.json 第2次、sector_daily.json 第1次成功；
  **docs/app.html / preview/index.html（各 1563KB）、miniprogram/data/history.js 屡推不过（app.html 连试 19 次全败）**
  → 最终全部由 git packfile 通道一次解决，main → **284b9e4**。
- 抓取：**未出现**「本次未抓到，沿用上次数据」。板块 3 天 / 宏观 79 指标(成功 54、失败 0) / 日历 16600 → 7505 / ics 175 日程。
- 线上已验证：Pages `data/meta.js` → version=**202610142134**、up_videos=**36** / up_days=**30**；
  `docs/app.html` 线上与本地 **sha256 完全一致**（`12e67512…`）。
  ⚠️ 最终 push 后 Pages 有 **1～2 分钟部署延迟**，首查拿到旧副本，等一会儿再查即一致 —— 别误判「没发布」。
- 收尾判据：**全量逐字节比对 107/107 tracked 文件 0 差异**（远程 tracked 由 88 增至 107）。
- 微信推送：**无 PushPlus token → 未发送**（预期内）。桌面 rsync 成功（36 条 / 440 要点）。
- 今日/明日：**10-14** 51 条、★★以上 21 项（★★★ 14：中国 CPI/PPI/进出口、美国 CPI/核心 CPI）；
  **10-15** 34 条、★★以上 12 项（★★★ 5：美国 PPI/核心 PPI；另有美联储褐皮书、EIA 库存、广交会）。

## 执行摘要（历史：2026-10-13 21:5x · **全流程收敛，推送成功**）
- **B 站要点：新增 1 个视频（13 条）** → 要点库 33 → **34 条**，覆盖 28 → **29 天**（总要点 416）。
  `BV1EupB6cExs` 2026-10-13「10.13 “Garbage Time”」（转写 1080 字）。
  主题：市场 Garbage Time、等美国中期选举转折点；沙特↔胡塞战事升级、第三艘航母 11 月中旬抵中东；
  特朗普不愿选举前出手（怕油价涨），11 月—次年 1 月是行动窗口；当下可靠的是国际原油价格 + 高位美元指数。
- ✅ **whisper 503 已根治**：`HF_HUB_OFFLINE=1` 这次**写进了 `tools/daily_update.sh`**（第 18 行），
  脚本原生一次转写成功，首次不再需要手动补 `--asr`。此改动已随产物推送。
- 🚨 **新坑：本机 workbench 会与自动化抢跑**。`tools/workbench.py`（launchd 常驻 :8787）持有
  `.full_ran.json`，能触发「完整更新 + 推 GitHub」。我在 21:37 推完 `bfead0d3` 后，
  **21:41 workbench 又重建并推了 `dc672e9e`**（内容与我逐字节一致，无损失）。
  → **别再拿 HEAD sha 当收敛判据**，只看全量逐字节比对。
- ℹ️ **`push_via_api.py` 的 commit message 取自本地 `git log -1`**（第 182 行），不是推送时刻生成 ——
  所以 workbench 推出来的 commit 会沿用你本地最新 commit 的文案（看着像"重复推送"）。
- 「auto 兜底」陷阱**照旧复现**：`up_pending.py` 报「无待办」，真待办 = `up_summary.json` 里 `auto==true`
  的条目（本次即 `BV1EupB6cExs`）。判断式：`auto==True` + `up_raw` 有转写但不在 summary 的 bvid。
- 推送：`git push` 被拒（双历史，预期）→ `push_via_api.py` **18 文件 / 8.26 MB 一次全成功**，main → `bfead0d3`；
  补推 `.full_ran.json` 后 → `3e9e823e`。**收尾全量比对 106/106 tracked 文件 0 差异**。
- 线上已验证：Pages `data/meta.js` → version=**202610132140**、up_videos=**34** / up_days=**29**。
  ⚠️ 大文件（history.js）用 curl 直连 Pages/raw 会**截断（exit 28）**，改用 **GitHub API blob/contents**
  核验更稳（contents 接口对 >1MB 文件返回空 content，须用 blobs 接口）。
- 抓取：**未出现**「本次未抓到，沿用上次数据」。板块 3 天 / 宏观 79 指标(成功 54、失败 0) / 日历 16575 → 7494 / ics 172 日程。
- 微信推送：无 PushPlus token → 未发送（预期内）。桌面 rsync 成功（34 条 / 416 要点）。
- 今日/明日：**10-13** 18 条、最高 ★★ 2 项（08:30 澳洲联储纪要、22:00 美国成屋销售）；
  **10-14** 42 条、最高 ★★★ 13 项（09:30 中国 CPI/PPI、20:30 美国 CPI/核心 CPI、00:00 进出口）。

## 执行摘要（历史：2026-10-12 21:5x · **全流程收敛，推送成功**）
- **B 站要点：新增 2 个视频（各 13 条）**，要点库 31 → **33 条**，覆盖 27 → **28 天**（共 403 条）。
  - `BV1HDp967E9C` 2026-10-12「10.12 接前一条视频」（1051 字）
  - `BV1d6pX6NEef` 2026-10-12「10.12 从看似蹊跷的『特普柴油协议』说开去...」（3491 字）
- ✅ **whisper 503 本次已提前规避**：`HF_HUB_OFFLINE=1 bash tools/daily_update.sh`，转写一次成功，未复现。
  **→ 建议把 `HF_HUB_OFFLINE=1` 写进 daily_update.sh，彻底免疫该坑。**
- ⚠️ **新现象：yt-dlp 单条下载会瞬时失败**。管线里 `BV1d6pX6NEef` 报 `✗ 下载失败 ... ERROR:`（stderr 为空），
  **手动重跑同一条命令即成功**（10.71MB/19s）。→ 遇「下载失败」先手动重试，别判定视频不可得。
  另：B 站列表搜索覆盖度不稳（本日先「找到 5 个」、后「找到 18 个」）——两个新视频都拿到了，但要留意。
- 抓取：**未出现**「本次未抓到，沿用上次数据」。板块 3 天 / 宏观 79 指标(成功 54、失败 0) / 日历 16550 → 7491 / ics 171 日程。
- 推送：`git push` 被拒（双历史，预期）→ `push_via_api.py` **17 文件 / 8.11 MB 一次全成功**，main → **aefd09e1**；
  `--dry` = 「没有可推送的改动」。**本轮顺带补推了 10-11 未成功的那批**（memory 文件等）。
- 线上已验证：Pages `data/meta.js` → version=**202610122148**、up_videos=**33** / up_days=**28**；
  `history.js` 与 `app.html` 线上/本地 **sha256 完全一致**。
  💡 **线上大文件核验必须加 cache-buster**（`?t=$(date +%s)`）——本次不加参数时 history.js 命中旧缓存、检索新 bvid 得 0，差点误判为未发布。
- 微信推送：无 PushPlus token → 未发送（预期内）。桌面 rsync 成功（33 条 / 28 天）。
- 今日/明日：10-12 共 14 条、最高 ★★ 2 项（小鹏巴黎发布会、博茨瓦纳总统访华）；10-13 共 12 条、最高 ★★ 2 项（08:30 澳洲联储纪要、22:00 美国成屋销售）。
- 💡 日历 `calendar.json` 的 `days` 是**数组格式** `[时间, 国家idx, 指标idx, 星级, 分类, 实际值]`（f3=星级，★★=2），
  用 `countries`/`names` 两个字典解码。

## 执行摘要（历史：2026-10-11 22:00 · 数据/要点完成，**推送推迟（代理挂）**）
- **B 站要点：新增 1 个视频** `BV14YpL6LE7m` 2026-10-11「10.11 从2009年"欧债危机"到当前的法国"财政风暴"」13 条
  → 要点库 30 → **31 条**，覆盖 26 → **27 天**。
- 🚨 **whisper 又报 503**（daily_update.sh 里 fetch_bilibili 转写失败，只下了音频）。**解法：`HF_HUB_OFFLINE=1` 重跑 `--asr`**，
  84s 转写 6430 字成功。⚠️ **脚本缺陷**：daily_update.sh 只设 `HF_ENDPOINT=hf-mirror`，**不设 HF_HUB_OFFLINE**，
  故 huggingface_hub 需联网解析 revision 时必 503 —— 每次遇到要手动补跑（见 10-09 同因）。
  好的一面：转写失败时新视频未进 up_raw，`up_pending.py` 本次**如实报出 1 条待办**，没被 auto 兜底遮住。
- 🚨 **推送失败 = 本机代理节点挂**（与 10-09 同因）：`git push` 报 `HTTP2 framing layer`；
  `push_via_api.py` 报 `SSL: UNEXPECTED_EOF_WHILE_READING`。实测 api.github.com / github.com /
  raw.githubusercontent.com / google.com **全 000**，baidu.com=200；7 个常见本地代理端口只有 1082 在 LISTEN 且全 000。
  有界重试 4 次 + 收尾 1 次均 000 → **改动已本地 commit `04e0ac2`，待代理恢复补跑 `push_via_api.py`**。
- 抓取：**未出现**「本次未抓到，沿用上次数据」。板块 3 天 / 宏观 79 指标(成功 54、失败 0) / 日历 16530 → 7485。
- 微信推送：无 PushPlus token → 未发送（预期内）。桌面 rsync 成功（31 条 / 27 天）。
- 今日/明日：10-11、10-12 东财日历**均无 ★★ 以上**。产物已含新视频，meta version=202610112149 / up_videos=31。

## 执行摘要（历史：2026-10-10 22:25 · **全流程收敛，推送成功**）
- **B 站要点：新增 4 个历史视频（各 13 条）**，要点库 26 → **30 条**，覆盖 22 → **26 天**。
  `fetch_bilibili.py` 报「没有新视频」，真待办来自 `build_dataset.py` 的「已转写但未总结」清单：
  - BV1RqCzBkEJE 2025-11-18（段永平／量化割韭菜）、BV1fbywBLEAM 2025-11-20（1—10 月财政收支）、
    BV1EpyuBvEaF 2025-11-21（房地产预期管理 + 十五五）、BV1xqEs6fEqJ 2026-06-07（DTCC 代币化清算）
  - 那 3 个 2025-11 视频的**真实标题就是「快来围观」占位标题**（已用 B 站 view 接口 code=0 复核），照原样入库。
- 抓取：**未出现**「本次未抓到，沿用上次数据」。板块 3 天 / 宏观 79 指标(成功 54、失败 0) / 日历 16530 → 7500。
- 🚨 **新坑：本机上行被掐，>256KB 的请求体常被丢弃**（详见下方专题）。`git push` 与 `push_via_api.py`
  双双报 `Broken pipe` / `RemoteDisconnected` / `bad record mac`，`http.postBuffer` 调大无效。
  **解法=分文件重试**（大文件第 3～5 次能过）；本轮 14 文件全部落地，远程 main → **dbc762cf**。
- ⚠️ **我踩的坑（已修）**：自写重试用 `grep "✓ <文件>"` 判成功是**错的** —— 那行只代表
  **blob 上传成功**，之后建 tree/commit/PATCH 失败也会打印它 → 误判 OK。
  **正确判据 = `grep "推送成功"`**。
- 收尾：**103/103 tracked 文件与远程逐字节 0 差异**；线上 `app.html` 与本地 **sha256 一致**
  （`7807c473…`），4 个新 bvid 均可在线上检索；Pages meta → version=**202610102141**、up_days=26 / up_videos=30。
- 微信推送：无 PushPlus token → 未发送（预期内）。桌面 rsync 成功（30 条 / 26 天）。
- 今日/明日：10-10、10-11 东财日历**均无 ★★ 以上安排**。

## 执行摘要（历史：2026-10-09 22:17 补跑 · 推送已成功，全流程收敛）
- 本日第二次跑同一套流程（首次 21:34-21:44 数据/要点已做完，仅推送失败；本次为**推送补跑**）。
- **B 站「没有新视频，无需处理」** → 要点库维持 **26 条 / 22 天**，未新增任何要点（本日 13 条要点已在首次跑时写入 `BV1hpp46QEkn` 2026-10-09「10.9 关于美债拍卖」）。
- 抓取：**未出现**「本次未抓到，沿用上次数据」。板块 3 天 / 宏观 79 指标(成功 54、失败 0) / 日历 16491 → 7467 条。
  ⚠️ B 站列表搜索第 5 页报 `HTTP Error 412`（IP 风控），只取到 6 个视频（页面覆盖不全，但不影响本次）。
- 推送：`git push` 报 `Error in the HTTP2 framing layer`（本地较 origin/main 领先 40 commit 的长期双历史，预期）→
  走 `tools/push_via_api.py`，**19 文件 / 8.00 MB 全部一次成功**，main → `f6e4a12a`；`--dry` = 「没有可推送的改动」（收敛）。
- 线上已验证：Pages `data/meta.js` → version=**202610092219**、up_videos=**26** / up_days=**22**。
- 微信推送：无 PushPlus token → 未发送（预期内）。桌面 rsync 成功，副本 26 条 / 22 天。
- 今日/明日：10-09 共 1 项 ★★（22:00 美国密歇根大学消费者信心指数:初值，实 46.3）；10-10（周六）无 ★★ 以上。
- 💡 **代理可用判据**：`curl --max-time 12 https://api.github.com` 返回 **200** 即代表 API 通道可用（google 仍 000 属正常分流，不代表代理挂）。
  10-09 首次跑判为「代理节点挂」的原因（google/github 全超时）本次已恢复。

## 执行摘要（历史：2026-10-09 · 数据/要点完成，**推送失败**）
- 新增 **1 个视频要点**：`BV1hpp46QEkn` 2026-10-09「10.9 关于美债拍卖」13 条 → 要点库 25 → **26 条**，覆盖 21 → **22 天**。
- 🚨 **`git push` 与 `tools/push_via_api.py` 本次双双失败**（近年首次）——**不是仓库/token 问题，是本机代理节点挂了**：
  全部流量走 `utun4`（Shadowrocket TUN，fake-IP `198.18.x.x`），国外站点（github/pypi/google/cloudflare）
  一律超时；系统代理 1082 对 github 返回 `503 tunnel failed`；直连 GitHub 真实 IP TCP 通但 TLS 被重置。
  → 改动已本地 commit（`f5be1c1` 数据 + `e3920e4` 要点），**待代理恢复后补跑 `push_via_api.py`**。
- 🚨 **新坑：whisper 加载报 `503 Service Unavailable`** —— 不是模型缺失（已缓存），而是
  huggingface_hub 联网解析 revision 走代理失败。**解法：`HF_HUB_OFFLINE=1`**（本次 47s 成功转写 3730 字）。
- 「auto 兜底」陷阱**本次未复现**（因为转写失败，新视频当时还没进 up_raw；转写补上后我直接手写要点）。
  待办信号仍按老规矩：`up_summary.json` 里 `auto==True` + `up_raw` 有转写但不在 summary 的 bvid。
- 抓取：**未出现**「本次未抓到，沿用上次数据」。板块 3 天（含 10-09）/ 宏观 79 指标(成功 54、失败 0) / 日历 16491 → 7467 条。
- 微信推送：无 PushPlus token → 未发送（预期内）。桌面 rsync 成功，副本 26 条 / 22 天。
- 今日/明日：10-09 共 1 项 ★★（22:00 美国密歇根大学消费者信心指数:初值）；10-10 无 ★★ 以上。

## 执行摘要（历史：2026-10-08 · 全流程完成）
- 新增 **1 个视频要点**：`BV199HD69EEZ` 2026-10-08「10.8」13 条 → 要点库 24 → **25 条**，覆盖 20 → **21 天**。
- 🚨 **「auto 兜底」陷阱第四次复现**（10-03/10-06/10-07 之后）：`summarize_up.py` 对新视频先以
  `auto:true` 塞 10 条原句碎片 → `up_pending.py` 报「无待办」。
  **可靠待办信号 = `up_summary.json` 里 `auto==True` 的条目**（本次即 BV199HD69EEZ）；
  `up_raw.json` 字段是 `txt`（`len(v['txt'])`）。
- 抓取：**未出现**「本次未抓到，沿用上次数据」。板块 3 天 / 宏观 79 指标(成功 54、失败 0) /
  日历 16467 → 7451 条。
- 推送：`git push` 443 **连接超时**（预期）→ 走 `tools/push_via_api.py`，
  14 文件 / 7.86 MB **一次全成功**，main → `bdf39843`；`--dry` 复查 = 无待推改动（收敛）。
- 线上已验证：Pages `data/meta.js` → version=202610082135、up_videos=25 / up_days=21。
  （`raw.githubusercontent.com` 偶发 connection reset，改用 Pages URL 核验更稳。）
- 微信推送：无 PushPlus token → 未发送（预期内）。桌面 rsync 成功，副本 25 条 / 21 天。
- 今日/明日：10-08 东财日历无 ★★ 以上（当日窗口已走完）；关键数值 1 项（美国初请失业金 19.7 万，前值 19.9 万）。
  10-09 共 1 项 ★★（22:00 美国密歇根大学消费者信心指数:初值）。
- ℹ️ **口径差异（非 bug）**：app「前瞻」用人工种子库 `seed_upcoming.py`（10-08 直接跳到 10-12，
  不含 10-09 密歇根）；push_daily「明天前瞻」用东财日历（含该条）。两个数据源，勿混用。
- 遗留：`webapp/index.html` 本次无改动；云端应用如需更新仍要单独发布（workbuddy_sites_deploy，须先征得用户同意）。

## 执行摘要（历史：2026-10-07 · 全流程完成）
- 新增 **1 个视频要点**（归档旧视频）：`BV1sQLy6gEgN` 2026-05-20「5.20 关于黄金的这个观点」13 条
  → 要点库 23 → **24 条**，覆盖 19 → **20 天**。
- 🚨 **「auto 兜底」陷阱第三次复现**：`fetch_bilibili.py` 把 2026-05-20 旧视频当新视频转写，
  `summarize_up.py` 立刻以 `auto:true` 塞 10 条原句碎片 → `up_pending.py` 报「无待办」。
  **可靠待办信号 = `up_summary.json` 里 `auto==True` 的条目**（本次即 BV1sQLy6gEgN）。
  `up_raw.json` 的字段是 `txt`（不是 text/transcript），长度用 `len(v['txt'])`。
- 抓取：**未出现**「本次未抓到，沿用上次数据」。板块 3 天（国庆休市）/ 宏观 79 指标(成功 54、失败 0) /
  日历 16348 → 7350 条。
- 推送：`git push` 报 `HTTP2 framing layer` 失败（预期，非分叉）→ 走 `tools/push_via_api.py`，
  16 文件 / 7.51 MB **一次全成功**，main → `033770ed`；`--dry` = 无待推改动（收敛）。
- 线上已验证：meta `version=202610072151`、`up_videos=24 / up_days=20`。
  ⚠️ 大文件（app.html）用 `curl` 直连 Pages 会 **exit=28 截断**，核验改用 `data/meta.js` +
  `raw.githubusercontent.../up_summary.json` 交叉验证更可靠。
- 微信推送：无 PushPlus token → 未发送（预期内）。桌面 rsync 成功，副本 24 条 / 20 天。
- 今日/明日安排：10-07 共 14 条（最高 ★★★ 16:00 央行外汇储备）；
  10-08 共 8 条（最高 ★★ 02:00 美联储公布货币政策会议纪要）。
- 遗留：`webapp/index.html` 无 diff（已与远端一致），云端应用如需更新仍要单独发布（workbuddy_sites_deploy，须先征得用户同意）。

## 执行摘要（历史：2026-10-06 · 全流程完成）
- 新增 **1 个视频要点**：`BV1xpHZ6FE5E` 2026-10-06「10.6 面对他们加速吸收、收紧流动性…」13 条
  → 要点库 22 → **23 条**，覆盖 19 天。
- 🚨 **陷阱复现（务必记住）**：`fetch_bilibili.py` 打印「没有新视频，无需处理」，
  但 `summarize_up.py` 照样把 10-06 视频以 `auto:true` 兜底塞进 `up_summary.json` ⇒
  `up_pending.py` 报「无待办」。**待办真正来源 = `up_summary.json` 里 `auto==True` 的条目**
  （本次即 BV1xpHZ6FE5E）+ `up_raw` 里有转写但不在 summary 的 bvid。别再只信 up_pending。
- 抓取：**未出现**「本次未抓到，沿用上次数据」。板块 3 天 / 宏观 79 指标（成功 54、失败 0）/
  日历 16348 → 7359 条。
- 推送：`git push` 仍 `non-fast-forward` 被拒（本地与远端长期双历史）→ 走 `tools/push_via_api.py`，
  17 文件 / 7.99 MB **一次全成功**，main → `05069cbc`；复查 `--dry` = 无待推改动（收敛）。
- 线上已验证：meta `version=202610062136`、`up_videos=23 / up_days=19`；`app.html` 含新视频标题。
- 微信推送：无 PushPlus token → 未发送（预期内）。
- 桌面 rsync：成功，副本含 23 条要点。
- 今日/明日安排：10-06 共 7 条（最高 ★★★ 20:30 美国贸易差额:季调）；
  10-07 共 14 条（最高 ★★★ 16:00 央行外汇储备）。
- 遗留：`webapp/index.html` 已在仓库，但**云端应用需单独发布**（workbuddy_sites_deploy，须先征得用户同意）——仍未执行。

## 执行摘要（历史：2026-10-06 · 非数据更新，纯答疑）
- 用户问「注册账号 / 手机⇄电脑同步是不是还没做」。本次**未跑数据管线**，只做代码+后端核查并作答。
- 结论：**网页端做了且已跑通；小程序端没账号体系；GitHub Pages 是设计上主动关闭。**
  证据：`build_preview.py` 有 `#loginSheet`(密码/验证码/注册 三 tab)+`cloudBtn`+`doSignOut`/`cloudPull`/`cloudPushAll`；
  云后端表 `mc_notes` RLS 开启；已有账号 `jasonling_tt@163.com`(2026-10-01 注册)；
  `cloudAllowed()` 只放行 localhost/127.0.0.1/[::1] 与 `*.workbuddy.host`，github.io 一律 false；
  `miniprogram/app.js` 是 `cloudEnv:''`+`useCloud:false`，全仓无 `signIn/signUp/手机号登录`；
  `#loginSheet` 那句「微信/手机号登录仅小程序可用」= 空承诺（真 bug）。
- 无产物文件产生 → 未调用 present_files（符合规范）。
- 遗留：云端应用是否需要重新发布（`webapp/index.html` 已含双页卡改动）——用户上次未答复，仍未执行。

## 执行摘要（2026-10-04）
- 流程同前；**今日无新视频**（UP 列表最新仍为 2026-10-03），要点库维持 **21 条**，未新增/修改任何条目。
- 已核查 `up_summary.json` 无 `auto:true` 兜底残留、`up_raw.json`(21) 与 `up_summary.json`(21) 完全对齐 → 确认无遗留待总结。
- 抓取：本次**未出现**「本次未抓到，沿用上次数据」。板块 3 天 / 宏观 79 指标(成功 54、失败 0) / 日历 1264 条。
- 微信推送：未配置 PushPlus token → 未发送（预期内）。
- 桌面 rsync：成功，副本 21 条要点齐全。
- 结果：远程 main → 24c8b278；全量比对**92/92 tracked 文件与本地逐字节一致**；线上 Pages version=202610042135、up_videos=21 / up_days=17（已核实）。
- 今日/明日安排：10-04（假期）2 项提示级；10-05 共 11 条，最高级别为 22:00 美国 ISM 服务业 PMI。

## ⚠️ 订正（2026-10-05 复核，10-04 的结论是错的）
- **那条「每次 push 都触发云端 run、云端重跑管线并回推」是误判。** 复核 `runs[].name` 后确认：
  `event=dynamic` 的 run 全是 **`pages build and deployment`** —— GitHub **内置**的 Pages 发布流程，
  只把当前 tree 重新发布到 Pages，**不重跑数据管线、也不回推任何 commit**。
- `daily.yml`（`每日更新市场日历`）**只在 `schedule`(21:00) 与 `workflow_dispatch` 上触发**。
- 10-04 那天 `--dry` 回涨的真凶是**定时任务同时在跑**（21:00 的 cron 当天拖到 21:30 之后落地），
  它用自己抓的新数据重建产物并提交 → 覆盖刚推的产物。等它跑完再推即收敛。
- 🚨 **更重要的推论：只推源码不会让线上产物更新。** 因为 push 不触发 `daily.yml`，
  改完 `build_preview.py` 之类源码后，Pages 重新发布的**仍是仓库里的旧产物**
  （2026-10-05 实测：只推 `build_preview.py` 后线上 `app.html` 里 `grep -c 'id="gapTabCal"'` = 0）。
  → 必须**显式 dispatch `daily.yml`**（204 = 成功）让它重建，或本地重建后自己推产物。
  另：`webapp/index.html` 不在 `daily.yml` 的 `git add` 里，任何情况下都要单独推/单独发布。
- 收尾判据不变：**全量逐字节比对**（92 个 tracked 文件），打印 0 差异才算收敛；`--dry` 只作参考。

## 执行摘要（历史：2026-10-03）
- 流程：daily_update.sh → 读转写提炼要点 → 写 up_summary.json → 三重建 → 推送 GitHub → rsync 桌面。
- 本机独有价值：B 站视频要点（转写需 whisper，要点提炼需读语义）。本次要点库 19 → **21 条**。
- 本次处理 4 个视频（全部 13 条要点、无 auto 兜底残留）：
  - 新转写 2 个（2026-10-03）：BV1TiHe6AEfF「10.3」、BV132HY6iEkC「10.3 基于当前现实…如何应对」
  - **新归档旧视频 2 个**：BV1TacLz6E5P（2026-02-13 美元体系）、BV14LKP6gEX9（2026-07-18 如何更完整理解美元）
    —— 这两个是 UP 列表里此前未入库的，fetch 时会一并下载转写，up_pending 才会列出，**容易漏**。
- ⚠️ 注意：summarize_up.py 的 auto 兜底会把新视频先塞进 up_summary.json，因此 `up_pending.py` 会显示「无待办」。
  真正待办要靠 `up_summary.json` 里 `auto==True` 的条目 + `up_raw.json` 中有转写但不在 up_summary 的 bvid 一起判断。
- 抓取：本次**未出现**「本次未抓到，沿用上次数据」，所有指标均抓取成功（板块 3 天、宏观 54/79 成功 0 失败、日历 7408 条）。
- 微信推送：未配置 PushPlus token → 未发送（预期内）。
- 桌面 rsync：成功，副本 21 条要点齐全。

## 推送通道（重要，沿用）
- **`git push` 不可用**，但失败原因会变：早期是 github.com 443 连不上；本次是能连上但 `non-fast-forward` 被拒
  （本地与远端历史分叉：远端常被 GitHub Actions 与 API 提交推进，本地是另一条历史）。
  → 不要试图 `git pull`/`--force`，直接走 API 通道。
- 正确通道 = `python3 tools/push_via_api.py`（token 于 `~/.market-calendar.github.json`）。
  它按**内容**与远端 tree 比对，与提交拓扑无关，不受分叉影响。
- 策略：小文件成批推（一次 5 个）；大文件（docs/app.html、preview/index.html、docs/data/history.js、
  miniprogram/data/history.js、tools/data/macro_series.json、tools/data/up_raw.json）逐个推 + 失败重试 2~3 次。
  本次 1 批小文件 + 6 个大文件 + 1 个补漏，**全部一次成功**。
- 收尾务必再跑一次 `--dry` 确认「没有可推送的改动」（本次补漏发现 `tools/data/sector_daily.json`）。
- 结果：远程 main → e987bba4；线上 Pages 已发布 version=202610032139、up_videos=21 / up_days=17（已核实）。
