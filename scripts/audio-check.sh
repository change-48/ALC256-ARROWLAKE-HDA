#!/bin/zsh
# ALC256 / Arrow Lake-H (8086:7728) 音频状态自检
# 用法：zsh scripts/audio-check.sh

echo "=== 系统 ==="
sw_vers -productVersion

echo
echo "=== 已加载的音频相关驱动 ==="
kmutil showloaded --list-only 2>/dev/null \
  | grep -iE "AppleHDA|AppleALC|SimpleHDA|Lilu|VoodooHDA" || echo "（无）"

echo
echo "=== 音频设备 ==="
system_profiler SPAudioDataType 2>/dev/null

echo
echo "=== HDEF 属性 ==="
ioreg -rn HDEF -w0 2>/dev/null \
  | grep -E '"(class-code|layout-id|alc-layout-id|IOName|device-id|subsystem-id)"'

echo
echo "=== 控制器/编解码器实例数（0 表示未 attach） ==="
ioreg -l -w0 2>/dev/null | grep -oE \
  '"AppleHDAController"=[0-9]+|"IOHDACodecDevice"=[0-9]+|"VoodooHDADevice"=[0-9]+|"VoodooHDAEngine"=[0-9]+'

echo
echo "=== VoodooHDA 引擎 ==="
ioreg -rc VoodooHDAEngine -w0 2>/dev/null | grep -E "IOAudioEngineDescription"

echo
echo "=== 系统音量 ==="
osascript -e 'get volume settings' 2>/dev/null

echo
echo "=== 驱动内部日志（需要 root，且驱动为 VoodooHDA 时才有输出） ==="
if [[ -x "${0:A:h}/../tools/vhda_msgbuf" ]]; then
  sudo "${0:A:h}/../tools/vhda_msgbuf" 2>/dev/null | tail -5
else
  echo "（vhda_msgbuf 不在附近；它来自 VoodooHDA 源码树的 tools/，"
  echo "  通过 IOConnectMapMemory64 读 kVoodooHDAMemoryMessageBuffer = 0x2000）"
fi
