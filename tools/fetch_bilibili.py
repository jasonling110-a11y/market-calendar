# -*- coding: utf-8 -*-
"""
B 站 UP 主视频抓取 + 语音转写

为什么要转写：实测该 UP 主的视频**没有 CC 字幕、简介也是空的**，
B 站自带的 AI 摘要接口需要登录（返回 -403）。所以只能走
「yt-dlp 下载音频 → faster-whisper 本地转写」这条路。

流程：
  1. 用 B 站搜索接口按 UP 主名搜索，过滤出属于该 UP 的视频（空间接口有 wbi 风控，搜索接口可用）
  2. 对没处理过的视频：yt-dlp 下载音频 → faster-whisper 转写
  3. 转写全文落 data/up_raw.json，等 AI 总结后再并入数据包

依赖：
  pip install yt-dlp faster-whisper
  首次运行会自动下载 whisper 模型；国内建议设 HF_ENDPOINT=https://hf-mirror.com
  且必须设 HF_HUB_DISABLE_XET=1（否则 xet 传输会 401）

输出：data/up_raw.json
  { "<bvid>": { "d": "YYYY-MM-DD", "t": 标题, "dur": 秒, "txt": 转写全文, "at": 抓取时间 } }
"""
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import http.cookiejar

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RAW = os.path.join(DATA, "up_raw.json")
AUDIO_DIR = os.path.join(DATA, "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

# ---- 目标 UP 主 ----
UP_NAME = "艾丽的无废话财经"
UP_MID = "3461575253953366"

MAX_NEW = int(os.environ.get("MAX_NEW", "6"))   # 单次最多处理几个新视频，避免跑太久
# 用 base 而非 small：下载与转写若同进程会 OOM（实测 exit 137），
# base 内存占用约一半，中文财经内容识别质量仍可用
MODEL = os.environ.get("WHISPER_MODEL", "base")
PENDING = os.path.join(DATA, "_pending.json")
ASR_PROMPT = "以下是财经分析内容，涉及宏观经济、货币政策、美联储、A股市场。"

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")   # 不设会因 xet 401 下载失败

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _opener():
    """⚠️ 必须显式禁用环境代理。
    实测本机与 CI 环境都挂着 HTTP(S)_PROXY，走代理访问 B 站会
    「Tunnel connection failed: 502」，而直连完全正常 —— 一开始被误判成 B 站改版。
    """
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(cj),
        urllib.request.HTTPSHandler(context=CTX))


def _warmup(op):
    """先访问一次主站拿到 buvid3。
    不带这个 cookie 调 api.bilibili.com 会直接返回 412（风控），
    预热一次即可，无需登录态。"""
    try:
        op.open(urllib.request.Request(
            "https://www.bilibili.com/",
            headers={"User-Agent": UA, "Accept": "text/html"}), timeout=20).read()
    except Exception:
        pass


def _json(op, url, ref="https://www.bilibili.com/"):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": ref,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    return json.loads(op.open(req, timeout=20).read().decode("utf-8", "ignore"))


def fetch_video_list(op):
    """按 UP 主名搜索并过滤出该 UP 的视频（多页，按发布时间倒序）"""
    seen, out = set(), []
    kw = urllib.parse.quote(UP_NAME)
    for page in range(1, 6):
        try:
            d = _json(op,
                      f"https://api.bilibili.com/x/web-interface/search/type"
                      f"?search_type=video&keyword={kw}&page={page}",
                      "https://search.bilibili.com/")
        except Exception as e:
            print(f"  [warn] 搜索第 {page} 页失败：{str(e)[:50]}")
            continue
        res = ((d.get("data") or {}).get("result")) or []
        if not res:
            break
        for v in res:
            if str(v.get("mid")) != UP_MID:
                continue
            bv = v.get("bvid")
            if not bv or bv in seen:
                continue
            seen.add(bv)
            ts = v.get("pubdate") or 0
            title = re.sub(r"<[^>]+>", "", str(v.get("title") or "")).strip()
            out.append({
                "bvid": bv,
                "d": time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else "",
                "t": title,
            })
        time.sleep(0.6)
    out.sort(key=lambda x: x["d"], reverse=True)
    return out


def dump_cookies(op, path):
    """把预热拿到的 cookie 写成 Netscape 格式给 yt-dlp 用。
    yt-dlp 没有 buvid3 同样会被 412 挡掉。"""
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


def download_audio(bvid, cookie_file=None):
    """下载音频，返回文件路径"""
    target = os.path.join(AUDIO_DIR, bvid)
    for f in os.listdir(AUDIO_DIR):
        if f.startswith(bvid) and not f.endswith(".part"):
            return os.path.join(AUDIO_DIR, f)
    cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--quiet",
           # 同样必须绕开环境代理，否则 yt-dlp 走代理访问 B 站会失败
           "--proxy", ""]
    if cookie_file and os.path.exists(cookie_file):
        cmd += ["--cookies", cookie_file]
    cmd += ["-f", "ba", "-o", target + ".%(ext)s",
            f"https://www.bilibili.com/video/{bvid}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "")[:120])
    for f in os.listdir(AUDIO_DIR):
        if f.startswith(bvid):
            return os.path.join(AUDIO_DIR, f)
    raise RuntimeError("下载后找不到音频文件")


_model = [None]


def transcribe(path):
    """faster-whisper 转写（模型只加载一次）"""
    from faster_whisper import WhisperModel
    if _model[0] is None:
        print(f"      加载 whisper {MODEL} 模型 ...", flush=True)
        _model[0] = WhisperModel(MODEL, device="cpu", compute_type="int8")
    segs, _info = _model[0].transcribe(
        path, language="zh", vad_filter=True, beam_size=5,
        initial_prompt=ASR_PROMPT)
    parts = []
    for s in segs:
        t = s.text.strip()
        if t:
            parts.append(t)
    return "".join(parts)


def _asr_worker():
    """子进程入口：批量转写 _pending.json 里的音频，结果并入 up_raw.json
    独立进程的意义：whisper 模型常驻内存约 1GB，与下载流程同进程会 OOM。"""
    with open(PENDING, encoding="utf-8") as f:
        jobs = json.load(f)
    done = {}
    if os.path.exists(RAW):
        with open(RAW, encoding="utf-8") as f:
            done = json.load(f)
    for i, j in enumerate(jobs, 1):
        print(f"  ({i}/{len(jobs)}) 转写 {j['d']} {j['t'][:26]}", flush=True)
        try:
            t0 = time.time()
            txt = transcribe(j["path"])
            if not txt:
                raise RuntimeError("转写结果为空")
            done[j["bvid"]] = {"d": j["d"], "t": j["t"], "txt": txt, "at": int(time.time())}
            print(f"        ✓ {len(txt)} 字，{time.time()-t0:.0f}s", flush=True)
        except Exception as e:
            print(f"        ✗ {str(e)[:80]}", flush=True)
    with open(RAW, "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[✓] 转写完成，累计 {len(done)} 个视频 → {RAW}", flush=True)


def main():
    if "--asr" in sys.argv:
        _asr_worker()
        return

    print(f"[1/3] 抓取 UP 主「{UP_NAME}」视频列表 ...")
    op = _opener()
    _warmup(op)
    cookie_file = dump_cookies(op, os.path.join(DATA, "_bili_cookies.txt"))
    vids = fetch_video_list(op)
    print(f"      找到 {len(vids)} 个视频，最新：{vids[0]['d'] if vids else '-'}")

    done = {}
    if os.path.exists(RAW):
        with open(RAW, encoding="utf-8") as f:
            done = json.load(f)

    todo = [v for v in vids if v["bvid"] not in done][:MAX_NEW]
    if not todo:
        print("[✓] 没有新视频，无需处理")
        return
    print(f"[2/3] 下载 {len(todo)} 个新视频的音频（跳过已转写的 {len(done)} 个）")

    jobs = []
    for i, v in enumerate(todo, 1):
        try:
            p = download_audio(v["bvid"], cookie_file)
            jobs.append({"bvid": v["bvid"], "d": v["d"], "t": v["t"], "path": p})
            print(f"  ({i}/{len(todo)}) ✓ {v['d']} {v['t'][:28]}")
        except Exception as e:
            print(f"  ({i}/{len(todo)}) ✗ 下载失败 {v['bvid']}: {str(e)[:60]}")

    if not jobs:
        print("[!] 没有成功下载的音频")
        return
    with open(PENDING, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False)

    print(f"[3/3] 启动独立进程转写 {len(jobs)} 个音频 ...")
    # 独立进程：主进程此时已释放下载相关内存，whisper 单独占用
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--asr"])
    if r.returncode != 0:
        print(f"[!] 转写子进程退出码 {r.returncode}")


if __name__ == "__main__":
    main()
