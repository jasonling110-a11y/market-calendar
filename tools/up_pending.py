# -*- coding: utf-8 -*-
"""
列出「已转写但尚未总结」的视频，并输出可读的转写全文。

为什么需要它：B 站视频的要点总结由 AI 阅读转写完成后写入 data/up_summary.json，
这一步机器做不了（需要理解语义）。所以抓取完要把待办清单明确打出来，
否则新视频会静默躺在 up_raw.json 里不进包。

用法：
    python3 up_pending.py          # 列出待总结的视频 + 转写全文
    python3 up_pending.py --brief  # 只列 bvid / 日期 / 标题，不打印全文
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "data", "up_raw.json")
SUM = os.path.join(HERE, "data", "up_summary.json")


def load(p):
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    raw, summ = load(RAW), load(SUM)
    pending = [b for b in raw if b not in summ]

    if not raw:
        print("[i] 还没有任何转写结果，先跑 fetch_bilibili.py")
        return
    if not pending:
        print(f"[✓] 全部 {len(raw)} 个视频都已有要点总结，无待办")
        return

    brief = "--brief" in sys.argv
    print(f"[!] {len(pending)} / {len(raw)} 个视频已转写但尚未总结")
    print(f"    总结后写入：{SUM}\n")
    for b in sorted(pending, key=lambda x: raw[x].get("d", ""), reverse=True):
        v = raw[b]
        print("=" * 68)
        print(f"{b}  {v.get('d','')}  {v.get('t','')}")
        print("=" * 68)
        if not brief:
            print(v.get("txt", ""))
        print()


if __name__ == "__main__":
    main()
