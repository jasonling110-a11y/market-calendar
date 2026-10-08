# -*- coding: utf-8 -*-
"""云端可行性探针：GitHub Actions 能否完成 B 站抓取 + whisper 转写。

目的：在**不改动现有管线**的前提下，逐项验证把 B 站环节整体上云的可行性。
    [1] 运行环境（CPU / 内存 / 磁盘）
    [2] B 站搜索接口是否被数据中心 IP 风控拦截（最关键的不确定项）
    [3] yt-dlp 能否下载音频
    [4] faster-whisper 能否在 workflow 时限内完成转写

本脚本是**只读探针**：音频与模型都落在临时目录，不写任何仓库数据文件。
所有步骤都不抛出异常，逐项打印 PASS/FAIL，便于一次跑完看清全部结论。

用法：
    python3 tools/probe_bili_cloud.py
环境变量：
    WHISPER_MODEL   默认 base
    PROBE_MAX_VIDEOS 默认 1，探针只转写 1 条
"""
import http.cookiejar
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "data", "up_raw.json")

UP_NAME = "艾丽的无废话财经"
UP_MID = "3461575253953366"
MODEL = os.environ.get("WHISPER_MODEL", "base")
MAX_VIDEOS = int(os.environ.get("PROBE_MAX_VIDEOS", "1"))

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

RESULTS = []


def step(n, msg):
    print(f"\n{'=' * 62}\n[{n}] {msg}\n{'=' * 62}", flush=True)


def verdict(n, name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    RESULTS.append((n, name, ok, detail))
    print(f"\n  >>> [{tag}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    return ok


def _opener():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(cj),
        urllib.request.HTTPSHandler(context=CTX))


def _warmup(op):
    try:
        op.open(urllib.request.Request(
            "https://www.bilibili.com/",
            headers={"User-Agent": UA, "Accept": "text/html"}), timeout=25).read()
        return True
    except Exception as e:
        print(f"  [warn] 主站预热失败：{str(e)[:90]}")
        return False


def _json(op, url, ref="https://www.bilibili.com/"):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": ref,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    return json.loads(op.open(req, timeout=25).read().decode("utf-8", "ignore"))


def dump_cookies(op, path):
    lines = ["# Netscape HTTP Cookie File"]
    for h in op.handlers:
        cj = getattr(h, "cookiejar", None)
        if cj is None:
            continue
        for c in cj:
            lines.append("\t".join([
                c.domain, "TRUE" if c.domain.startswith(".") else "FALSE",
                c.path or "/", "TRUE" if c.secure else "FALSE",
                str(int(c.expires or 0)), c.name, c.value or ""]))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def probe_env():
    step(1, "运行环境")
    try:
        import multiprocessing
        print(f"  CPU 核数：{multiprocessing.cpu_count()}")
    except Exception:
        pass
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    kb = int(re.findall(r"\d+", line)[0])
                    print(f"  内存总量：{kb / 1024 / 1024:.1f} GB")
                    break
    except Exception:
        print("  内存总量：（非 Linux，跳过）")
    try:
        du = shutil.disk_usage("/")
        print(f"  磁盘可用：{du.free / 1024 ** 3:.1f} GB")
    except Exception:
        pass
    print(f"  Python：{sys.version.split()[0]}")
    try:
        v = subprocess.run([sys.executable, "-m", "yt_dlp", "--version"],
                           capture_output=True, text=True, timeout=60)
        print(f"  yt-dlp：{v.stdout.strip() or v.stderr.strip()[:60]}")
    except Exception as e:
        print(f"  yt-dlp：检测失败 {str(e)[:60]}")
    print(f"  whisper 模型：{MODEL}")
    verdict(1, "运行环境可读", True)


def probe_search(max_tries=3):
    step(2, "B 站搜索接口（风控检查）— 最关键的不确定项")
    op = _opener()
    warm = _warmup(op)
    print(f"  主站预热（取 buvid3）：{'成功' if warm else '失败'}")
    kw = urllib.parse.quote(UP_NAME)
    for attempt in range(1, max_tries + 1):
        t0 = time.time()
        try:
            d = _json(op,
                      "https://api.bilibili.com/x/web-interface/search/type"
                      f"?search_type=video&keyword={kw}&page=1",
                      "https://search.bilibili.com/")
        except Exception as e:
            print(f"  第 {attempt} 次请求异常：{type(e).__name__} {str(e)[:90]}")
            time.sleep(3)
            continue
        code = d.get("code")
        msg = str(d.get("message") or "")
        print(f"  第 {attempt} 次：code={code} message={msg!r} "
              f"({time.time() - t0:.1f}s)")
        if code == 0:
            res = ((d.get("data") or {}).get("result")) or []
            mine = [v for v in res if str(v.get("mid")) == UP_MID]
            print(f"  返回结果 {len(res)} 条，其中属于该 UP 的 {len(mine)} 条")
            if mine:
                mine.sort(key=lambda x: x.get("pubdate") or 0, reverse=True)
                newest = mine[0]
                title = re.sub(r"<[^>]+>", "", str(newest.get("title") or "")).strip()
                print(f"  最新一条：{newest.get('bvid')} / {title[:40]}")
                cookie_file = dump_cookies(op, os.path.join(TMP, "_cookies.txt"))
                n_cookie = sum(1 for _ in open(cookie_file))
                print(f"  导出 cookie：{n_cookie - 1} 条 → {cookie_file}")
                return verdict(2, "搜索接口可达且未被风控", True,
                               f"code=0，命中 {len(mine)} 条"), mine, cookie_file
            return verdict(2, "搜索接口可达但未命中该 UP", False,
                           f"code=0 但 result 里没有 mid={UP_MID}"), [], None
        if code in (-352, -412, -509):
            print(f"  ⚠️ 命中风控码 {code}，换个姿势重试 …")
        time.sleep(4)
    return verdict(2, "搜索接口被风控/不可达", False,
                   f"连续 {max_tries} 次未拿到 code=0"), [], None


def probe_download(videos, cookie_file):
    step(3, "yt-dlp 下载音频")
    done = {}
    if os.path.exists(RAW):
        try:
            with open(RAW, encoding="utf-8") as f:
                done = json.load(f)
        except Exception:
            pass
    print(f"  仓库里已转写 {len(done)} 个视频（根据 up_raw.json）")
    todo = [v for v in videos if v["bvid"] not in done][:MAX_VIDEOS]
    if not todo:
        print("  没有未入库的新视频可测，改为用已知能下的 bvid 试下")
        todo = [{"bvid": v["bvid"], "d": v.get("d", ""),
                 "t": re.sub(r"<[^>]+>", "", str(v.get("title") or "")).strip()}
                for v in videos[:1]]
    if not todo:
        return verdict(3, "yt-dlp 下载音频", False, "没有可试的 bvid"), []

    jobs = []
    for v in todo:
        bvid = v["bvid"]
        target = os.path.join(TMP, bvid)
        cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--quiet",
               "--proxy", ""]
        if cookie_file and os.path.exists(cookie_file):
            cmd += ["--cookies", cookie_file]
        cmd += ["-f", "ba", "-o", target + ".%(ext)s",
                f"https://www.bilibili.com/video/{bvid}"]
        t0 = time.time()
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            print(f"  ✗ {bvid} 下载超时（>900s）")
            continue
        el = time.time() - t0
        if r.returncode != 0:
            print(f"  ✗ {bvid} 下载失败：{(r.stderr or '').strip()[:140]}")
            continue
        hit = [os.path.join(TMP, f) for f in os.listdir(TMP) if f.startswith(bvid)]
        if not hit:
            print(f"  ✗ {bvid} 返回 0 但找不到文件")
            continue
        size = os.path.getsize(hit[0]) / 1024 / 1024
        print(f"  ✓ {bvid} 下载成功：{os.path.basename(hit[0])} "
              f"{size:.1f} MB，{el:.1f}s")
        jobs.append({"bvid": bvid, "d": v.get("d", ""),
                     "t": v.get("t", ""), "path": hit[0]})
    if not jobs:
        return verdict(3, "yt-dlp 下载音频", False, "全部下载失败"), []
    return verdict(3, "yt-dlp 下载音频", True, f"{len(jobs)} 个成功"), jobs


def probe_whisper(jobs):
    step(4, f"faster-whisper 转写（模型 {MODEL}）")
    t_load0 = time.time()
    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        return verdict(4, "faster-whisper 转写", False, f"导入失败 {str(e)[:80]}")
    try:
        model = WhisperModel(MODEL, device="cpu", compute_type="int8")
    except Exception as e:
        return verdict(4, "faster-whisper 转写", False, f"模型加载失败 {str(e)[:90]}")
    print(f"  模型加载完成，{time.time() - t_load0:.1f}s")

    ok_any, notes = False, []
    for j in jobs:
        t0 = time.time()
        try:
            segs, info = model.transcribe(
                j["path"], language="zh", vad_filter=True, beam_size=5,
                initial_prompt="以下是财经分析内容，涉及宏观经济、货币政策、美联储、A股市场。")
            parts = [s.text.strip() for s in segs if s.text.strip()]
            txt = "".join(parts)
            el = time.time() - t0
            dur = getattr(info, "duration", 0) or 0
            ratio = (el / dur) if dur else 0
            print(f"  ✓ {j['bvid']} 转写 {len(txt)} 字，耗时 {el:.0f}s"
                  f"（音频 {dur:.0f}s，实时率 {ratio:.2f}x）")
            print(f"    开头：{txt[:100]}")
            ok_any = True
            notes.append(f"{len(txt)}字/{el:.0f}s")
        except Exception as e:
            print(f"  ✗ {j['bvid']} 转写失败：{str(e)[:110]}")
    if ok_any:
        return verdict(4, "faster-whisper 转写", True, "；".join(notes))
    return verdict(4, "faster-whisper 转写", False, "全部失败")


def main():
    global TMP
    TMP = tempfile.mkdtemp(prefix="bili_probe_")
    print("B 站抓取 + whisper 云端可行性探针")
    print(f"临时目录：{TMP}")
    t_all = time.time()

    probe_env()
    ok2, videos, cookie_file = probe_search()
    jobs = probe_download(videos, cookie_file) if videos else ([], None)
    if isinstance(jobs, tuple):
        _ok3, jobs = jobs
    if jobs:
        probe_whisper(jobs)

    step(5, "结论汇总")
    for n, name, ok, detail in RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] ({n}) {name}"
              + (f" — {detail}" if detail else ""))
    print(f"\n  总耗时：{time.time() - t_all:.0f}s")

    critical = [r for r in RESULTS if r[0] in (2, 3, 4)]
    all_ok = bool(critical) and all(r[2] for r in critical)
    missing = [r[1] for r in critical if not r[2]]
    if all_ok:
        print("\n  ✅ 结论：B 站抓取 + 转写在云端跑通，方案 2（全上云）可行。")
    else:
        print("\n  ❌ 结论：以下环节未通过 —— " + "、".join(missing))
        print("     → 需针对性处理（见上方日志），否则应回退方案 1（本机 launchd）。")
    try:
        shutil.rmtree(TMP, ignore_errors=True)
    except Exception:
        pass


if __name__ == "__main__":
    TMP = ""
    main()
