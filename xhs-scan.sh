#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# 代刷找灵感：自动滑动 + 截图，配合 pet-assets 出素材清单
#
# 用法：
#   xhs-scan                # 默认滑 10 次
#   xhs-scan 20             # 滑 20 次
#   xhs-scan 20 3           # 滑 20 次，每次间隔 3 秒
#
# 用前准备：
#   ① 手机开好无线调试（adb 已连上）
#   ② 打开小红书（或任何 App），搜好关键词，停在结果页
#   ③ 保持亮屏（别锁屏，否则截到的是锁屏）
#
# 原理：纯模拟手指手势（input swipe）+ 截图，不调任何 API、
#       不读登录态、不改账号 —— 风险等同于自己划屏幕。
# ============================================================
set -u

ROUNDS="${1:-10}"
GAP="${2:-2}"
OUT="/sdcard/Deskpet/素材"

DEV=$(adb devices 2>/dev/null | awk 'NR==2 && $2=="device"{print $1}')
if [ -z "${DEV:-}" ]; then
  echo "❌ 没有已连接的 adb 设备。"
  echo "   手机 → 设置 → 开发者选项 → 无线调试，然后："
  echo "   TMPDIR=\$PREFIX/tmp adb connect 192.168.1.141:<端口>"
  exit 1
fi

# 按屏幕分辨率算滑动轨迹（纵向滑，从下往上 = 下一个）
SIZE=$(adb -s "$DEV" shell wm size 2>/dev/null | grep -oE '[0-9]+x[0-9]+' | head -1)
W=${SIZE%x*}; H=${SIZE#*x}
W=${W:-1080}; H=${H:-2400}
X=$((W/2)); Y1=$((H*72/100)); Y2=$((H*32/100))

mkdir -p "$OUT"
echo "设备：$DEV   分辨率：${W}x${H}"
echo "滑动轨迹：($X,$Y1) → ($X,$Y2)"
echo "输出目录：$OUT"
echo

for i in $(seq 1 "$ROUNDS"); do
  f="$OUT/刷_$(date +%m%d_%H%M%S)_$i.png"
  if adb -s "$DEV" exec-out screencap -p > "$f" 2>/dev/null && [ -s "$f" ]; then
    echo "[$i/$ROUNDS] 已截图：$(basename "$f")"
  else
    echo "[$i/$ROUNDS] ⚠️ 截图失败（设备掉了？）"
    rm -f "$f"
    break
  fi
  adb -s "$DEV" shell input swipe "$X" "$Y1" "$X" "$Y2" 320 >/dev/null 2>&1
  sleep "$GAP"
done

echo
echo "完成。接着跑：pet-assets    → 生成《素材清单.md》"
