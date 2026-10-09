# 市场日历 · 项目长期约定

> 发布/构建的**完整操作手册**在用户级技能 `market-calendar-release`（含踩坑与验证脚本）。
> 这里只记最容易记错、且每次都会用到的几条。

## 构建（唯一 UI 源头 = `tools/build_preview.py`）
```bash
PY=/Users/jason/.workbuddy/binaries/python/versions/3.13.12/bin/python3
$PY tools/build_preview.py          # → preview/index.html（数据内嵌）
$PY tools/build_preview.py --cloud  # → webapp/index.html（运行时取数 + 云笔记）
$PY tools/build_ics.py              # → docs/app.html + docs/market-calendar.ics + docs/index.html
```
改一处，三端（本机工作台 / GitHub Pages / 云端应用）同时变。

## 🚨 发布铁律（2026-10-05 实测确认）
- **push 不会重跑数据管线。** push 只触发 GitHub 内置的 `pages build and deployment`
  （`event=dynamic`，只把当前 tree 重新发布到 Pages，不回推 commit）。
  `daily.yml`（`每日更新市场日历`）**只在 21:00 cron 与 `workflow_dispatch` 上跑**。
- 所以**改完源码后必须显式 dispatch `daily.yml`**（或本地重建后自己推产物），
  否则 Pages 重新发布的仍是**仓库里的旧产物**。
- 判 `runs` 一定要看 **`name`**，别看 `event`、也别看 `run_number`（不同 workflow 各自编号）。
- **`git push` 在本机永久不可用**（无凭据 + 本地/远端是长期平行的双历史）→
  数据与源码一律走 `$PY tools/push_via_api.py`（token 在 `~/.market-calendar.github.json`）。
- `webapp/index.html` 不在 `daily.yml` 的 `git add` 里 → 云端那份只能靠 `workbuddy_sites_deploy`
  单独发布（**须先征得用户同意**）。
- 收敛判据 = **全量逐字节比对 92 个 tracked 文件为 0 差异**，不是 `--dry`。
  注意本地 `tools/data/*.json` 常比远端旧（远端 21:00 定时任务更新），此时**不要**推产物。

## 利润断层栏（易改错）
- 有**两组等价页卡**，`aria-selected` 由同一个 `setTab()` 同步：
  顶栏 `#tabCal`/`#tabGap`，覆盖层内 `#gapTabCal`/`#gapTabGap`。
- 层内那对是**必需**的：覆盖层整屏（z-index 60）会把顶栏整组盖住。
- **不要再加回 `#gapClose`**（2026-10-05 按用户要求删掉的「返回日历」按钮），自检有反向断言。
- 改它要跑两个自检 + 负向测试：`tools/check_profitgap_tab.js`（86 项）、
  `tools/browser_check_profitgap.js`（40 项，真实浏览器）、`git diff --numstat` 复核改动范围。

## 🚨 两个「看起来是代码 bug、其实是环境」的坑（2026-10-09 实测）
1. **whisper 加载报 `503 Service Unavailable`** → 不是模型缺失（`~/.cache/huggingface` 里有 145MB `model.bin`），
   而是 `huggingface_hub` 加载时会联网解析 revision，本机走系统代理 → 503。
   **解法：`HF_HUB_OFFLINE=1`** 强制读本地缓存。重跑写法：
   ```bash
   cd tools && HF_HUB_OFFLINE=1 /Users/jason/.workbuddy/binaries/python/envs/default/bin/python fetch_bilibili.py --asr
   ```
   （注意 whisper 装在 **venv** `/Users/jason/.workbuddy/binaries/python/envs/default/bin/python`，
   管理的 3.13.12 里**没有** faster_whisper。）
2. **GitHub 完全不可达时别怀疑仓库/token** → 本机全部流量走 `utun4`（Shadowrocket TUN，
   fake-IP `198.18.x.x`）。**国外站点（github/pypi/google/cloudflare）随代理节点状态集体超时**；
   系统代理 1082 对 github 返回 `503 tunnel failed`；直连 GitHub 真实 IP（api.github.com=20.205.243.168）
   TCP 能连但 TLS 被重置。此时 `git push` 报 `SSL_ERROR_SYSCALL`、`push_via_api.py` 报
   `UNEXPECTED_EOF_WHILE_READING` —— **先测 `curl https://www.google.com` 判断是不是节点挂了**，
   是就等节点恢复再补推，不要改代码/换 token。

## 时区
所有时间戳一律**显式东八区**。本机 CST / Actions UTC 差 8 小时，`date.today()` 甚至会差一天。

## 数据源
B 站视频要点目前**由本机完成**（抓音频 + whisper 转写 + AI 读语义提炼）。

### 「B 站环节能否上云」的实测结论（2026-10-08，探针 `tools/probe_bili_cloud.py`）
此前写的「Actions 没有 yt-dlp/whisper」是**误判** —— 那是「没装」，不是「装不了」。实测：
- **whisper 在 Actions 上完全能跑**（4 核 / 15.6GB）。模型 base 加载 3.0s，转写正常。
  ⚠️ 但必须 **`pip install "av<19"`**：`av 19.0.1` 删了 `metadata_errors` 参数，
  而 `faster-whisper 1.2.1` 仍在传它 → 报 `open() got an unexpected keyword argument
  'metadata_errors'`。本机用的是 `av 18.1.0`，所以本机正常、CI 报错，极易误判成「CI 跑不了」。
- **真正的堵点是 B 站的 IP 风控**：CI 的 Azure 数据中心 IP 拉视频页 **412**，
  且**连 `api.bilibili.com/x/web-interface/view` 也是 412**（换 API 通道绕不过）。
  但 `search/type` 搜索接口**不 412**（code=0）—— 所以风控是按接口分级的。
  本机（住宅 IP）**cookie 文件为空也能下**，故确认是 IP 维度而非 cookie 维度。
- 唯一已知解法：`SESSDATA` 登录态 cookie（=把账号凭据放进 Secrets，有安全风险且会过期）
  或走住宅代理（有成本）。
- ➡️ **结论：全上云不划算；要摆脱 WorkBuddy 就走本机 launchd 定时。**

本机跑完必须把 `tools/data/up_summary.json` + `up_raw.json` 推上去，否则云端日历留空窗。
