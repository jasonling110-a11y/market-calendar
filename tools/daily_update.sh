#!/bin/bash
# 每日数据更新：抓取 -> 转写 -> 重建数据包 -> 重新生成预览
#
# 用法：  bash tools/daily_update.sh
#
# 注意：脚本负责所有「机器能做」的环节。唯一需要 AI 介入的是
#       B 站视频的要点总结（要读懂转写内容），脚本末尾会打印待办清单。
#       总结写入 tools/data/up_summary.json 后，再跑一次 build 即可入包。
set -u
cd "$(dirname "$0")" || exit 1

VENV=/Users/jason/.workbuddy/binaries/python/envs/default/bin/python
SYS=/Users/jason/.workbuddy/binaries/python/versions/3.13.12/bin/python3
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_DISABLE_XET=1          # 不设会因 xet 传输 401 而下载失败

step() { echo; echo "──────────────── $1 ────────────────"; }

step "1/8  A 股板块行情"
"$SYS" fetch_sectors.py 2>&1 | tail -3 || echo "  [!] 板块抓取失败，沿用上次数据"

step "2/8  B 站 UP 主视频（下载音频 + 转写）"
"$VENV" fetch_bilibili.py 2>&1 | grep -v "^\[download\]" | tail -14 \
  || echo "  [!] B 站抓取失败"

step "3/8  宏观数值与市场预期"
"$VENV" fetch_macro.py 2>&1 | grep -v "it/s" | tail -4 \
  || echo "  [!] 宏观抓取失败，沿用上次数据"

step "4/8  财经日历（东财，含未来排期与央行动态）"
"$SYS" fetch_calendar.py 2>&1 | tail -5 \
  || echo "  [!] 日历抓取失败，沿用上次数据"

step "5/8  重建数据包"
"$SYS" build_dataset.py

step "6/8  重新生成预览版"
"$SYS" build_preview.py

step "7/8  生成 iPhone 日历订阅源（.ics）"
"$SYS" build_ics.py

step "8/8  推送今日摘要到微信（PushPlus）"
# 未配置 token 时脚本会打印配置方法并退出，不影响前面已完成的更新
"$SYS" push_daily.py || true

step "待总结的 B 站视频（需 AI 阅读转写后写入 up_summary.json）"
"$SYS" up_pending.py --brief

echo
echo "[✓] 每日更新流程结束"
