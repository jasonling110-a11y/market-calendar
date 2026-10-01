#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场日历 · 本地工作台

把整套数据管线 + 界面跑成一个常驻的本地网站：

    http://127.0.0.1:8787/

提供的能力：
  - 网页界面：财经日历 / 关键数值 / 历史事件 / UP 主观点 / 复盘笔记
  - 每天定时自动抓取（默认 08:00 与 18:00）
  - 页面上可手动触发「快速刷新」与「完整更新」
  - 页面自动感知数据变化并重载，不需要手动按 F5

为什么不用现成的 Web 框架：
  整条数据管线本来就是纯标准库的，服务器也保持零依赖，
  这样它能在任何一台 Mac 上直接跑起来，不需要 pip install 任何东西。

用法：
    python3 tools/workbench.py                 # 前台运行
    python3 tools/workbench.py --port 9000
    python3 tools/workbench.py --schedule 07:30,12:00,20:00
"""

import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PREVIEW = os.path.join(ROOT, "preview")
DATA = os.path.join(ROOT, "miniprogram", "data")
TDATA = os.path.join(HERE, "data")            # 抓取脚本的原始数据目录
UP_RAW = os.path.join(TDATA, "up_raw.json")
UP_SUM = os.path.join(TDATA, "up_summary.json")
FULL_MARK = os.path.join(TDATA, ".full_ran.json")   # 上次「完整更新」的时间戳

# 两次「完整更新（含 B 站转写）」之间至少间隔的小时数。
# 为什么按小时而不是按自然日：早上开机补跑一次、晚上 21:30 再跑一次，
# 同一天需要跑两回（UP 主晚上才发视频）。按天会导致晚上那次被误跳过。
BILI_EVERY = 8.0
BILI_ENABLED = True

# 抓 B 站视频要点需要 whisper / yt-dlp，装在虚拟环境里；
# 其余脚本只用标准库，用当前解释器即可。
# 需要第三方包的脚本必须用虚拟环境跑：
#   fetch_bilibili.py → yt-dlp / faster-whisper
#   fetch_macro.py    → akshare（LPR / 社融 / M2 这三个指标只有 akshare 有源）
# 实测踩过：漏掉 fetch_macro.py，工作台跑一百次 LPR 也不会更新，
# 因为系统 python 没有 akshare，脚本会静默沿用旧数据。
VENV_SCRIPTS = {"fetch_bilibili.py", "fetch_macro.py"}
VENV_PY = os.path.expanduser("~/.workbuddy/binaries/python/envs/default/bin/python")
SYS_PY = sys.executable


def pick_py(script):
    if script in VENV_SCRIPTS and os.path.exists(VENV_PY):
        return VENV_PY
    return SYS_PY


# ---------------------------------------------------------------- 抓取任务
# 快速模式：只要数据源新鲜就够了，1～2 分钟
QUICK_STEPS = [
    ("财经日历（含未来排期）", "fetch_calendar.py"),
    ("A 股板块行情", "fetch_sectors.py"),
    # 广度与催化的顺序不能换：催化是拿「当天领涨板块」去匹配新闻的，
    # 必须排在 fetch_sectors.py 之后，否则匹配的是上一次的板块榜。
    ("个股涨跌家数（市场广度）", "fetch_breadth.py"),
    ("领涨板块的消息面催化", "fetch_catalysts.py"),
    ("宏观数值与市场预期", "fetch_macro.py"),
    # 新转写但还没提炼的视频先自动摘录入包，避免日历上出现空窗
    ("B 站要点兜底摘录", "summarize_up.py"),
    ("重建数据包", "build_dataset.py"),
    ("重新生成页面", "build_preview.py"),
    ("日历订阅源", "build_ics.py"),
]

# 完整模式：多出 B 站视频转写（要跑 whisper，5～10 分钟），
# 末尾再把结果推到 GitHub —— B 站这一步云端做不了（要 yt-dlp + whisper，
# 且 B 站不给字幕），只有本机能抓。不推上去，手机上打开的云版就看不到新视频。
# 只放在完整模式：每天 1 次提交，比每次快速刷新都推要干净得多。
FULL_STEPS = ([("B 站视频要点（语音转写）", "fetch_bilibili.py")] + QUICK_STEPS
              + [("同步到云端（GitHub）", "push_via_api.py")])


class State:
    """抓取状态。多线程读写，全部走锁。"""

    def __init__(self):
        self._lock = threading.Lock()
        self.updating = False
        self.mode = None
        self.started_at = None
        self.finished_at = None
        self.last_success = None
        self.error = None
        self.current = ""
        self.steps = []
        self.log = []
        self.trigger = ""            # manual / schedule
        self.ran_today = {}          # 'HH:MM' -> 'YYYY-MM-DD'

    def snapshot(self):
        with self._lock:
            return {
                "updating": self.updating,
                "mode": self.mode,
                "startedAt": self.started_at,
                "finishedAt": self.finished_at,
                "lastSuccess": self.last_success,
                "error": self.error,
                "current": self.current,
                "steps": list(self.steps),
                "log": self.log[-40:],
                "trigger": self.trigger,
                "dataVersion": data_version(),
                "pendingUP": len(pending_up()),
                "fullAgeH": full_age_hours(),
                "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

    def begin(self, mode, trigger):
        with self._lock:
            if self.updating:
                return False
            self.updating = True
            self.mode = mode
            self.trigger = trigger
            self.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.finished_at = None
            self.error = None
            self.current = ""
            self.log = []
            steps = FULL_STEPS if mode == "full" else QUICK_STEPS
            self.steps = [{"name": n, "state": "pending"} for n, _ in steps]
            return True

    def set_step(self, idx, state):
        with self._lock:
            if 0 <= idx < len(self.steps):
                self.steps[idx]["state"] = state
                self.current = self.steps[idx]["name"]

    def line(self, text):
        with self._lock:
            self.log.append(text.rstrip())

    def finish(self, ok, err=None):
        with self._lock:
            self.updating = False
            self.current = ""
            self.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if ok:
                self.last_success = self.finished_at
                self.error = None
            else:
                self.error = err or "未知错误"


STATE = State()

# 启动时用产出文件的修改时间作为「上次更新」的初值。
# 不这么做的话，每次重启状态栏都显示「上次更新 —」，看起来像从未更新过，
# 而实际上数据可能几分钟前才抓过。
try:
    _st = os.stat(os.path.join(PREVIEW, "index.html"))
    STATE.last_success = datetime.fromtimestamp(_st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
except OSError:
    pass


def data_version():
    """用产出文件的指纹表示数据版本，前端据此判断要不要重载"""
    try:
        f = os.path.join(PREVIEW, "index.html")
        st = os.stat(f)
        return f"{int(st.st_mtime)}-{st.st_size}"
    except OSError:
        return "0-0"


def data_age_hours():
    """页面数据距今多少小时。返回 None 表示还没有数据。"""
    try:
        st = os.stat(os.path.join(PREVIEW, "index.html"))
        return (time.time() - st.st_mtime) / 3600.0
    except OSError:
        return None


# ---------------------------------------------------------------- B 站这条链路
# 为什么要单独记账：转写（whisper）能在本机自动跑；「要点」现在有两条路——
# 优先用 AI 读转写后写进 up_summary.json（质量最好），AI 没顾上的由
# summarize_up.py 自动摘录兜底（界面会标注「自动摘录 · 待归纳」）。
# 所以这里负责判断「该不该再转写一次」，并把「转写了但还没要点」的缺口暴露出来。
# ⚠️ 这条链路云端（GitHub Actions）做不了：要 yt-dlp + whisper，且这些视频没有字幕，
#    只能靠本机跑，跑完再由 push_via_api.py 推上去。
def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def pending_up():
    """已转写但还没有要点总结的视频列表（B 站那一块真正缺的东西）"""
    raw = load_json(UP_RAW, {})
    summ = load_json(UP_SUM, {})
    if not isinstance(raw, dict) or not isinstance(summ, dict):
        return []
    return [b for b in raw if b not in summ]


def full_age_hours():
    """距上次完整更新（含 B 站）多少小时；None 表示从未跑过。
    没有标记文件时退回用 up_raw.json 的修改时间 —— 那正是上次转写成功的时刻，
    这样首次启用不会因为「没有标记」就立刻跑一次 10 分钟的转写。"""
    mark = load_json(FULL_MARK, {})
    ts = mark.get("ts") if isinstance(mark, dict) else None
    if ts is None:
        try:
            ts = os.stat(UP_RAW).st_mtime
        except OSError:
            return None
    try:
        return (time.time() - float(ts)) / 3600.0
    except (TypeError, ValueError):
        return None


def mark_full():
    """记录一次成功的完整更新（含 B 站步骤）"""
    try:
        with open(FULL_MARK, "w", encoding="utf-8") as f:
            json.dump({
                "ts": time.time(),
                "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }, f)
    except OSError:
        pass


def need_full():
    """要不要在本次抓取里带上 B 站转写。返回 (是否, 原因)"""
    if not BILI_ENABLED:
        return False, "已用 --no-bili 关闭 B 站自动转写"
    age = full_age_hours()
    if age is None:
        return True, "尚未做过完整更新"
    if age >= BILI_EVERY:
        return True, f"距上次完整更新已 {age:.1f} 小时"
    return False, f"{age:.1f} 小时前刚做过完整更新，跳过"


def run_pipeline(mode, trigger):
    """在后台线程里跑抓取流水线"""
    steps = FULL_STEPS if mode == "full" else QUICK_STEPS
    if not STATE.begin(mode, trigger):
        return

    ok = True
    err = None
    try:
        for idx, (name, script) in enumerate(steps):
            path = os.path.join(HERE, script)
            if not os.path.exists(path):
                STATE.set_step(idx, "skipped")
                STATE.line(f"[!] 找不到 {script}，跳过")
                continue
            STATE.set_step(idx, "running")
            STATE.line(f"── {name} ──")
            try:
                proc = subprocess.Popen(
                    # -u 关闭缓冲。子进程的 stdout 接到管道时是块缓冲（4~8KB），
                    # 不加这个，界面上会「卡在某一步好几分钟、一行日志都不出」，
                    # 明明是正常在跑，看起来像死了 —— 排查问题时最容易被误导。
                    [pick_py(script), "-u", script],
                    cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                )
                for raw in proc.stdout:
                    line = raw.rstrip()
                    # 进度条之类的输出太吵，丢掉
                    if line and "it/s" not in line and "it]" not in line:
                        STATE.line(line)
                rc = proc.wait()
            except Exception as e:                       # noqa: BLE001
                rc, err = 1, f"{script}: {type(e).__name__} {e}"
                STATE.line(f"[✗] {err}")
            if rc == 0:
                STATE.set_step(idx, "done")
            else:
                # 单个数据源失败不算致命（脚本内部会沿用上次数据），
                # 但要让用户看得见，不能静默跳过
                STATE.set_step(idx, "failed")
                STATE.line(f"[!] {name} 返回码 {rc}，沿用已有数据")
    except Exception as e:                               # noqa: BLE001
        ok, err = False, f"{type(e).__name__}: {e}"
        STATE.line(f"[✗] {err}")

    # B 站步骤成功才记账，否则下次仍会补跑（不会因为一次失败就哑掉）
    if mode == "full" and STATE.steps and STATE.steps[0]["state"] == "done":
        mark_full()

    miss = pending_up()
    if miss:
        STATE.line(f"[!] 有 {len(miss)} 个 B 站视频已转写但还没有要点："
                   f"{'、'.join(miss[:5])}{' 等' if len(miss) > 5 else ''}")
        STATE.line("    跑一次 summarize_up.py 会自动摘录兜底；AI 提炼的版本会覆盖它")

    STATE.finish(ok, err)
    stamp = datetime.now().strftime("%H:%M:%S")
    STATE.line(f"[✓] {stamp} 更新结束")


def start_refresh(mode="quick", trigger="manual"):
    t = threading.Thread(target=run_pipeline, args=(mode, trigger), daemon=True)
    t.start()


def scheduler_loop(schedule):
    """到点触发。每天每个时间点只跑一次（靠 ran_today 记录）。"""
    while True:
        time.sleep(20)
        now = datetime.now()
        hhmm = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")
        for slot, mode in schedule:
            if hhmm != slot or STATE.ran_today.get(slot) == today:
                continue
            STATE.ran_today[slot] = today
            if STATE.updating:
                continue
            if mode == "full":
                want, why = need_full()
                if not want:
                    STATE.line(f"[i] 定时任务 {slot} 跳过 B 站转写：{why}")
                    continue
                STATE.line(f"[i] 定时任务 {slot} 触发（完整更新 · {why}）")
                start_refresh("full", "schedule")
            else:
                STATE.line(f"[i] 定时任务 {slot} 触发（快速刷新）")
                start_refresh("quick", "schedule")


# ---------------------------------------------------------------- HTTP
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=PREVIEW, **kw)

    def log_message(self, fmt, *args):     # 静音默认访问日志
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _index_path_safe(self):
        """禁止路径穿越：只允许 preview/ 目录，以及透出的 webapp/sdk/"""
        p = urllib.parse.urlparse(self.path).path
        if p.startswith("/sdk/"):
            return os.path.normpath(os.path.join(ROOT, "webapp", p.lstrip("/"))).startswith(
                os.path.join(ROOT, "webapp", "sdk"))
        target = os.path.normpath(os.path.join(PREVIEW, p.lstrip("/")))
        return target.startswith(PREVIEW)

    def translate_path(self, path):
        """preview/ 里没有云 SDK。这里从 webapp/sdk/ 直接透出，而不是再复制一份 ——
        本机工作台也要能登录同步笔记，但同一份 62KB 代码不该在仓库里存两处。"""
        p = urllib.parse.urlparse(path).path
        if p.startswith("/sdk/"):
            return os.path.join(ROOT, "webapp", p.lstrip("/"))
        return super().translate_path(path)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        if path == "/api/status":
            return self._json(STATE.snapshot())

        if path == "/api/health":
            return self._json({"ok": True, "port": self.server.server_address[1]})

        if not self._index_path_safe():
            return self._json({"error": "forbidden"}, 403)

        # 静态文件不要缓存，否则数据更新后页面还是旧的
        return super().do_GET()

    def end_headers(self):
        if self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        elif self.path in ("/", "/index.html"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path

        if path == "/api/refresh":
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except ValueError:
                body = {}
            mode = body.get("mode", "quick")
            if mode not in ("quick", "full"):
                return self._json({"error": "mode 只能是 quick 或 full"}, 400)
            if STATE.updating:
                return self._json({"error": "已有更新在进行中", "status": STATE.snapshot()}, 409)
            start_refresh(mode, "manual")
            return self._json({"ok": True, "mode": mode}, 202)

        return self._json({"error": "not found"}, 404)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def parse_schedule(items):
    """把 ["08:30:quick","21:30:full","18:00"] 解析成 [("08:30","quick"), ...]"""
    out = []
    for it in items:
        parts = it.split(":")
        if len(parts) < 2:
            continue
        try:
            hhmm = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        except ValueError:
            continue
        mode = parts[2].strip() if len(parts) > 2 else "quick"
        out.append((hhmm, mode if mode in ("quick", "full") else "quick"))
    return out


def main():
    global BILI_EVERY, BILI_ENABLED

    port = 8787
    host = "127.0.0.1"
    # 默认排期：白天三次轻量刷新，晚上 21:30 做一次完整更新（含 B 站转写）。
    # 但真正保证「不卡点」的是下面的启动补跑 —— 定时只是锦上添花。
    schedule = parse_schedule(["08:30:quick", "12:30:quick", "18:00:quick", "21:30:full"])
    auto_fetch = True
    max_age = 10.0

    for a in sys.argv[1:]:
        if a.startswith("--port="):
            port = int(a.split("=", 1)[1])
        elif a.startswith("--host="):
            host = a.split("=", 1)[1]
        elif a.startswith("--schedule="):
            schedule = parse_schedule([x for x in a.split("=", 1)[1].split(",") if x.strip()])
        elif a == "--no-autofetch":
            auto_fetch = False
        elif a == "--no-bili":
            BILI_ENABLED = False
        elif a.startswith("--max-age="):
            max_age = float(a.split("=", 1)[1])
        elif a.startswith("--bili-every="):
            BILI_EVERY = float(a.split("=", 1)[1])

    if not os.path.exists(os.path.join(PREVIEW, "index.html")):
        print("[!] preview/index.html 不存在，先跑一次 build_preview.py")
        return 1

    threading.Thread(target=scheduler_loop, args=(schedule,), daemon=True).start()

    # 启动时补跑：这是「不必卡点开机」的关键。
    # 只要数据偏旧、或者距上次 B 站转写够久，就自动抓一次；
    # 因此你任何时候打开 Mac 双击启动，都会自动补齐，不需要正好 21:30 在场。
    age = data_age_hours()
    if auto_fetch:
        want_full, why = need_full()
        if want_full or age is None or age > max_age:
            mode = "full" if want_full else "quick"
            label = "完整更新（含 B 站转写，约 5-10 分钟）" if mode == "full" else "快速刷新"
            print(f"  启动后自动补跑一次 · {label} ｜ {why}", flush=True)
            if age is not None and age > max_age and not want_full:
                print(f"    （数据已 {age:.1f} 小时未更新）", flush=True)
            start_refresh(mode, "startup")
        else:
            print(f"  数据 {age:.1f} 小时前更新过，本次跳过抓取", flush=True)

    httpd = Server((host, port), Handler)
    print("")
    print("  市场日历 · 本地工作台")
    print("  " + "-" * 46)
    print(f"  地址：      http://{host}:{port}/")
    print(f"  定时抓取：  " + "、".join(
        f"{s}（{'完整' if m == 'full' else '快速'}）" for s, m in schedule))
    print(f"  启动补跑：  " + ("开启" if auto_fetch else "关闭")
          + "（数据超过 %.0f 小时未更新即抓）" % max_age)
    print(f"  B 站转写：  " + ("开启" if BILI_ENABLED else "关闭")
          + (f"，最短间隔 {BILI_EVERY:.0f} 小时" if BILI_ENABLED else ""))
    n_miss = len(pending_up())
    if n_miss:
        print(f"  [!] 有 {n_miss} 个 B 站视频已转写但还没有要点（需 AI 提炼）")
    print(f"  数据目录：  {DATA}")
    print("  " + "-" * 46)
    print("  按 Ctrl+C 停止")
    print("", flush=True)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止。")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
