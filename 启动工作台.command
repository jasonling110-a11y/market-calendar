#!/bin/bash
# 市场日历 · 本地工作台 —— 双击本文件即可启动
#
# 启动后会做三件事：
#   1. 起一个本地网站 http://127.0.0.1:8787/
#   2. 自动打开浏览器
#   3. 如果数据超过 10 小时没更新，后台自动抓一次
#
# 关闭方式：回到这个终端窗口按 Control + C
# 想让它开机自动启动：双击「设为开机自启.command」

cd "$(dirname "$0")/tools" || exit 1

PY="/Users/jason/.workbuddy/binaries/python/versions/3.13.12/bin/python3"
URL="http://127.0.0.1:8787/"

if [ ! -x "$PY" ]; then
  echo "找不到 Python：$PY"
  echo "请把本文件里的 PY 改成你机器上可用的 python3 路径。"
  read -r -p "按回车键关闭…"
  exit 1
fi

# 已经在跑就不再启动第二个（否则端口冲突）
if curl -sS --max-time 2 "${URL}api/health" >/dev/null 2>&1; then
  echo "工作台已经在运行了，直接打开浏览器。"
  open "$URL"
  exit 0
fi

echo "正在启动本地工作台…"
echo ""

# 等服务器就绪后再打开浏览器，避免打开一个「无法连接」的页面
(
  for _ in $(seq 1 20); do
    sleep 0.5
    if curl -sS --max-time 2 "${URL}api/health" >/dev/null 2>&1; then
      open "$URL"
      break
    fi
  done
) &

# 前台运行：这样 Control + C 就能干净地停掉服务，不会留下看不见的后台进程
exec "$PY" workbench.py
