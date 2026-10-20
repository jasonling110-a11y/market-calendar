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
- ✅ **`git push` 其实可用（2026-10-14 实测）** —— 之前的结论「永久不可用」是错的。
  失败的真实原因只是**本地与远端是两条平行历史**（`non-fast-forward`），不是网络。
  正确姿势（把新提交挂在远端 HEAD 上 → 变 fast-forward）：
  ```bash
  git fetch origin main:refs/remotes/origin/main   # 注意：不给 refspec 只会写 FETCH_HEAD
  git add -A && tree=$(git write-tree)
  c=$(git commit-tree $tree -p $(git rev-parse origin/main) -m "每日更新 <北京时间>")
  git -c http.postBuffer=524288000 push origin "${c}:refs/heads/main"   # zsh 必须 ${c}
  ```
  **关键优势：packfile 是 zlib 压缩的**，1.6MB 的 app.html 压完约 1/4，
  天然绕开「>256KB 原始请求体被丢弃」的坑 —— 比 `push_via_api.py` 逐 blob 重试稳得多。
  ⚠️ zsh 里 `"$c:refs/..."` 会被当成 `:r` 修饰符，务必写 `"${c}:refs/..."`。
- ✅ **`Error in the HTTP2 framing layer` 的解：加 `-c http.version=HTTP/1.1`（2026-10-19 实测）**。
  该报错连 `git fetch` 都会失败（看似网络挂），但换成 HTTP/1.1 后 fetch 与 push 都**一次成功**，
  不用换 token、也不用退到 `push_via_api.py`。建议把 fetch/push 两条命令都带上这个参数。
- ⚠️ **但「github.com 443 TCP 不可达」是另一种病，HTTP/1.1 治不了（2026-10-20 实测）**：
  `curl github.com` = 000（connect 超时 75s）而 `curl api.github.com` = **200** 时，
  git 通道已死、只剩 API 通道 → 直接 `push_via_api.py`（20 文件 / 8.59MB 一次全成功），别再调 git 参数。
  **判据顺序：先分别 curl 两个域名，再决定走哪条通道。**
- ⚠️ **macOS 没有 `timeout` 命令**：`timeout git fetch …` 会 `command not found` 且**静默不执行**，
  随后你看到的 `origin/main` 是旧值 —— 极易误判「fetch 成功 / 远端没变」。别用 `timeout` 包 git。
- 核验线上大文件必须 `curl --http1.1 --compressed`；否则 1.5MB 的 history.js 会**静默截断到 1.21MB**
  （仍返回 200）。判据用 `shasum -a 256` 与本地逐字节比，别看大小。
- 备用通道仍保留 `$PY tools/push_via_api.py`（token 在 `~/.market-calendar.github.json`）。
  但它**遇到第一个上传失败就 return 1（无自动重试）**，必须自己分批：
  小文件 ≤300KB 一批，大文件逐个重试；实测 ≥1.5MB 的文件（docs/app.html、preview/index.html）
  可能连续 19 次都过不去 → 此时直接用上面的 git packfile 通道。
- `webapp/index.html` 不在 `daily.yml` 的 `git add` 里 → 云端那份只能靠 `workbuddy_sites_deploy`
  单独发布（**须先征得用户同意**）。
- 收敛判据 = **全量逐字节比对（2026-10-14 起是 107 个）tracked 文件为 0 差异**，不是 `--dry`。
  判法：`git fetch origin main:refs/remotes/origin/main` 后，用 `git hash-object --stdin-paths`
  算本地 blob sha，与 `git ls-tree -r origin/main` 的 sha 逐一对齐。
  注意本地 `tools/data/*.json` 常比远端旧（远端 21:00 定时任务更新），此时**不要**推产物。

## ⚠️ 本机 workbench 会与自动化抢跑（2026-10-13 实测）
- `tools/workbench.py`（launchd `com.market-calendar.workbench`，KeepAlive 常驻 `127.0.0.1:8787`）
  持有 `tools/data/.full_ran.json` 标记，能触发「完整更新 + 同步到云端(GitHub)」。
- 后果：**你推完 HEAD 还可能再变**。本轮 21:37 推完 `bfead0d3`，21:41 workbench 又重建推了
  `dc672e9e`（内容与我的逐字节一致，无损失）。→ **别把这个当成推送失败/被覆盖**；
  判据永远是全量逐字节比对，不是 HEAD sha。
- ℹ️ `push_via_api.py` 的 commit message **取自本地 `git log -1`**（脚本第 182 行），
  不是推送时刻生成 —— 所以 workbench 推出来的 commit 会沿用你本地最新 commit 的文案，看着像"重推"。

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
   ✅ **2026-10-13 已根治：`HF_HUB_OFFLINE=1` 已写进 `tools/daily_update.sh`**（第 18 行），
   此后直接 `bash tools/daily_update.sh` 即可，不必再手动补 `--asr`。若哪天又 503，先确认这行还在。
   手动重跑写法（备用）：
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
3. **「能连上、但大请求体被丢弃」——比第 2 条更阴**（2026-10-10 实测）：
   小请求（GET、小 blob）全部正常，只有**上传**会挂。curl 打 `/git/blobs` 实测阈值：
   **≤256KB 请求体 → 稳定 201；512KB → 10 次成功 5 次；≥1MB → 基本全 000**。
   `git push`（哪怕推到新分支，无分叉问题）也会报
   `unable to rewind rpc post data` + `SSL ... bad record mac`，把 `http.postBuffer`
   调到 500MB 也无效；`--noproxy '*'` 与走 `127.0.0.1:1082` 两条路一样。
   ➡️ **不是仓库/token/代码问题，唯一解法 = 分文件反复重试**（1.5MB 文件往往第 3～5 次能过）。
   **判成功必须 `grep "推送成功"`**，不能用 `✓ <文件名>` —— 后者只是 blob 上传成功的输出，
   后面的建 tree / 建 commit / PATCH ref 失败它照样打印，会把失败误判成成功。
   收尾判据照旧：**全量逐字节比对 103 个 tracked 文件为 0 差异**。

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
