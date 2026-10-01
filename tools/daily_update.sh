#!/bin/bash
# 每日数据更新：抓取 -> 转写 -> 重建数据包 -> 重新生成预览
#
# 用法：  bash tools/daily_update.sh
#
# 注意：脚本负责所有「机器能做」的环节。B 站视频要点优先由 AI 读转写后归纳
#       （写入 tools/data/up_summary.json，质量最好）；AI 没来得及写的新视频，
#       由 summarize_up.py 自动摘录兜底，保证日历上不空窗。
#       脚本末尾会打印待办清单，AI 润色后重跑 build 即可覆盖兜底版。
set -u
cd "$(dirname "$0")" || exit 1
ROOT="$(cd .. && pwd)"      # 仓库根目录，最后一步推送到 GitHub 用

VENV=/Users/jason/.workbuddy/binaries/python/envs/default/bin/python
SYS=/Users/jason/.workbuddy/binaries/python/versions/3.13.12/bin/python3
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_DISABLE_XET=1          # 不设会因 xet 传输 401 而下载失败

step() { echo; echo "──────────────── $1 ────────────────"; }

step "1/10 A 股板块行情"
"$SYS" fetch_sectors.py 2>&1 | tail -3 || echo "  [!] 板块抓取失败，沿用上次数据"

step "2/10 B 站 UP 主视频（下载音频 + 转写）"
"$VENV" fetch_bilibili.py 2>&1 | grep -v "^\[download\]" | tail -14 \
  || echo "  [!] B 站抓取失败"

step "3/10 B 站要点兜底摘录（新视频先自动入包，避免日历空窗）"
"$SYS" summarize_up.py 2>&1 | tail -6 || echo "  [!] 兜底摘录失败，仅影响新视频"

step "4/10 宏观数值与市场预期"
"$VENV" fetch_macro.py 2>&1 | grep -v "it/s" | tail -4 \
  || echo "  [!] 宏观抓取失败，沿用上次数据"

step "5/10 财经日历（东财，含未来排期与央行动态）"
"$SYS" fetch_calendar.py 2>&1 | tail -5 \
  || echo "  [!] 日历抓取失败，沿用上次数据"

step "6/10 重建数据包"
"$SYS" build_dataset.py

step "7/10 重新生成预览版"
"$SYS" build_preview.py

step "8/10 生成 iPhone 日历订阅源（.ics）"
"$SYS" build_ics.py

step "9/10 推送今日摘要到微信（PushPlus）"
# 未配置 token 时脚本会打印配置方法并退出，不影响前面已完成的更新
"$SYS" push_daily.py || true

step "待总结的 B 站视频（需 AI 阅读转写后写入 up_summary.json）"
"$SYS" up_pending.py --brief

step "10/10 同步到 GitHub（让云端发布也拿到最新数据）"
# Mac 侧多了「B 站视频要点」，推上去之后 GitHub Pages 的内容才和本地一致。
# 未配置远程仓库时自动跳过，不影响前面已完成的工作。
if git -C "$ROOT" remote 2>/dev/null | grep -q .; then
  git -C "$ROOT" add -A >/dev/null 2>&1 || true
  if git -C "$ROOT" diff --staged --quiet; then
    echo "  没有变化，跳过提交"
  else
    git -C "$ROOT" commit -q -m "每日更新 $(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M')" \
      && git -C "$ROOT" push -q && echo "  ✓ 已推送到 GitHub"
  fi
else
  echo "  未配置远程仓库，跳过（按『云端部署指南.md』配好后会自动启用）"
fi

echo
echo "[✓] 每日更新流程结束"
