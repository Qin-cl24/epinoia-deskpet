#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# 小屋调试：按页面上报的「屏幕投影框」点击 3D 元素
#
# 用法：
#   tools/room-tap.sh lamp-shade clock pic curtain-L rugitem
#   tools/room-tap.sh --fresh beditem          # 先重启页面（机位复位）再点
#   tools/room-tap.sh --list                   # 只打印当前所有元素的屏幕框
#
# 为什么需要它：小屋是 CSS 3D，元素在屏幕上的位置由机位（yaw/tilt/zoom）决定，
# 手写坐标必然错。页面每 3 秒把每个元素的 getBoundingClientRect 报进 logcat
# （tag RoomDebug，行首 rects），本脚本读那行 → 换算成 device 像素 → adb input tap。
#
# 换算（真机实测，2026-11-03）：
#   device_x = css_x * dpr        dpr = devicePixelRatio（本机 3.25）
#   device_y = css_y * dpr + 153  153 = 状态栏高度（device px），竖屏横屏都是它，
#                                 WebView 的内容起点就落在这里——踩过坑：少加这 153
#                                 会整体偏下 47 CSS px，点哪都不准。
# ============================================================
set -uo pipefail

PKG=com.epinoia.deskpet
ACT="$PKG/.RoomActivity"
STATUS_BAR=153
FRESH=0
NAMES=()

for a in "$@"; do
  case "$a" in
    --fresh) FRESH=1 ;;
    --list)  LIST_ONLY=1 ;;
    -*)      echo "未知参数 $a"; exit 2 ;;
    *)       NAMES+=("$a") ;;
  esac
done
LIST_ONLY="${LIST_ONLY:-0}"

DEV="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{print $1; exit}')"
[ -z "$DEV" ] && { echo "❌ 没有已连接的设备（先 adb connect 127.0.0.1:<端口>）"; exit 1; }

ADB="adb -s $DEV"
if [ "$FRESH" = 1 ]; then
  adb logcat -c 2>/dev/null
  $ADB shell am force-stop "$PKG" >/dev/null 2>&1
  sleep 0.4
  $ADB shell am start -n "$ACT" >/dev/null 2>&1
  sleep 4.6     # 等物理落定（3s 才报 rects）
fi

LOADED="$($ADB logcat -d -s RoomDebug 2>/dev/null | grep 'loaded ' | tail -1)"
DPR="$(echo "$LOADED" | grep -oE 'dpr=[0-9.]+' | cut -d= -f2)"
[ -z "$DPR" ] && DPR=3.2487      # 页面没报就退回本机实测值
RECTS="$($ADB logcat -d -s RoomDebug 2>/dev/null | grep -E 'rects( cam)? ' | tail -1)"
[ -z "$RECTS" ] && { echo "❌ 没读到 rects 行（页面没加载？用 --fresh 重启一次）"; exit 1; }

get_box() {   # $1=名字 → 打印 "x y w h"
  echo "$RECTS" | tr '|' '\n' | sed 's/.*rects[^ ]* //' \
    | grep -E "(^| )$1=[0-9-]" | head -1 | sed "s/.*$1=//" | tr ',' ' ' | awk '{print $1, $2, $3}' | sed 's/x/ /'
}

if [ "$LIST_ONLY" = 1 ]; then
  printf 'dpr=%s  %s\n' "$DPR" "$LOADED"
  echo "$RECTS" | tr '|' '\n' | sed 's/.*rects[^ ]* //' | sed '/^$/d'
  exit 0
fi

[ ${#NAMES[@]} -eq 0 ] && { echo "用法: room-tap.sh [--fresh] [--list] <元素名>..."; exit 2; }

for n in "${NAMES[@]}"; do
  read -r X Y W H <<<"$(get_box "$n")"
  if [ -z "${X:-}" ]; then echo "⚠️ $n 不在 rects 里，跳过"; continue; fi
  CX=$(awk -v x="$X" -v w="$W" -v d="$DPR" 'BEGIN{printf "%d", (x + w/2) * d}')
  CY=$(awk -v y="$Y" -v h="$H" -v d="$DPR" -v s="$STATUS_BAR" 'BEGIN{printf "%d", (y + h/2) * d + s}')
  echo "→ 点 $n  框($X,$Y,${W}x${H}) → device($CX,$CY)"
  adb logcat -c 2>/dev/null
  $ADB shell input tap "$CX" "$CY"
  sleep 1.1
  $ADB logcat -d -s RoomDebug 2>/dev/null | grep -E 'hit |lamp (on|off)|phys drop|cam reset' | tail -2
done
