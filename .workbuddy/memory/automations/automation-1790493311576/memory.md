# 自动化 memory — 市场日历每日更新（automation-1790493311576）

## 执行摘要（最新：2026-10-08 · 全流程完成）
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
