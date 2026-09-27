#!/bin/bash
# 把「市场日历 · 本地工作台」设为开机自动启动（macOS 系统服务）
#
# 双击运行一次即可。之后每次开机，工作台都会自动在后台跑起来，
# 你随时打开 http://127.0.0.1:8787/ 就能看。
#
# 想取消自启：把下面这行粘到「终端」里执行
#   launchctl bootout gui/$(id -u)/com.market-calendar.workbench
# 或者只把 ~/Library/LaunchAgents/com.market-calendar.workbench.plist 删掉。

LABEL="com.market-calendar.workbench"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="/Users/jason/.workbuddy/binaries/python/versions/3.13.12/bin/python3"

echo "正在配置开机自启…"
echo ""

if [ ! -x "$PY" ]; then
  echo "找不到 Python：$PY"
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" || {
  echo "无法创建 ~/Library/LaunchAgents，请检查权限。"
  read -r -p "按回车键关闭…"
  exit 1
}

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PY}</string>
        <string>${HERE}/tools/workbench.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${HERE}/tools</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/tmp/market-workbench.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/market-workbench.err</string>
</dict>
</plist>
PLISTEOF

echo "配置已写入：$PLIST"
echo ""

# 先卸掉旧实例，避免「已在运行」的报错
launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1

if launchctl bootstrap "gui/$(id -u)" "$PLIST" >/dev/null 2>&1; then
  sleep 3
  if curl -sS --max-time 5 "http://127.0.0.1:8787/api/health" >/dev/null 2>&1; then
    echo "✓ 已设为开机自启，并且现在就在运行了。"
    echo ""
    echo "  地址：http://127.0.0.1:8787/"
    open "http://127.0.0.1:8787/"
  else
    echo "✓ 配置已加载，但服务还没响应。"
    echo "  看日志：cat /tmp/market-workbench.err"
  fi
else
  echo "✗ 系统拒绝了自启配置（launchctl 返回错误）。"
  echo ""
  echo "  替代做法：手动把「启动工作台.command」加进登录项——"
  echo "  系统设置 → 通用 → 登录项 → 点「+」→ 选择那个文件。"
fi

echo ""
read -r -p "按回车键关闭…"
