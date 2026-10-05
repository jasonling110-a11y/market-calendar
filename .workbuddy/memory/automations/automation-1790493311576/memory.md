# 自动化 memory — 市场日历每日更新（automation-1790493311576）

## 执行摘要（最新：2026-10-04）
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
