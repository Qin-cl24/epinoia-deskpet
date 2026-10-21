#!/data/data/com.termux/files/usr/bin/bash
# 桌宠形象截图核对工具
#   用法： pet-shot.sh <动作名> [输出名] [延迟秒]
#   例：   pet-shot.sh angry             → ~/storage/downloads/pet-angry.png
#          pet-shot.sh read 看书 2.0      → 动作 read、文件名 pet-看书.png、等 2 秒再拍
#
# 为什么需要它：桌宠是 96×72dp 的悬浮窗，贴边时大部分在屏幕外（frame=[-260,347][52,581]），
# 直接 adb screencap 只能看到屏幕左上角一小条。所以本工具做三件事：
#   ① 用 /eval 调 peekOut() 让它从贴边滑出来、② POST /say 触发指定动作、
#   ③ 读 dumpsys 里悬浮窗的真实 frame，按坐标裁剪并放大 3 倍（2px 的眼睛细节才看得清）。
SELF="$(readlink -f "$0")"
export TMPDIR="${TMPDIR:-$PREFIX/tmp}"

ACT="${1:?用法: pet-shot.sh <动作名> [输出名] [延迟秒]}"
NAME="${2:-$ACT}"
DELAY="${3:-1.4}"
OUT="$HOME/storage/downloads/pet-$NAME.png"
API="http://127.0.0.1:9001"

DEV="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')"
if [ -z "$DEV" ]; then
  echo "❌ 没有已连接的 adb 设备。先在设置→无线调试里配对，然后："
  echo "     adb pair 127.0.0.1:<配对端口> <配对码> && adb connect 127.0.0.1:<连接端口>"
  exit 1
fi

# ① 唤醒 + 从贴边滑出来（否则窗口大部分在屏幕外）
curl -s -m 5 -X POST "$API/eval" \
  -d '{"js":"var p=document.getElementById(\"pet\");p.classList.remove(\"asleep\",\"handle-mode\");try{showPet();}catch(e){};window.AndroidBridge&&window.AndroidBridge.peekOut();\"ok\""}' \
  >/dev/null 2>&1 || true
sleep 0.4

# ② 触发动作（文本留空，避免气泡挡脸；气泡本身是独立窗口，不影响裁剪）
curl -s -m 5 -X POST "$API/say" -d "{\"text\":\"\",\"action\":\"$ACT\"}" >/dev/null 2>&1 || true
sleep "$DELAY"

# ③ 截屏（exec-out 直接拿二进制，不用先存手机再 pull）
if ! adb -s "$DEV" exec-out screencap -p > "$TMPDIR/pet-shot-raw.png" 2>/dev/null; then
  echo "❌ 截屏失败"; exit 1
fi

python3 - "$TMPDIR/pet-shot-raw.png" "$OUT" "$DEV" <<'PY'
import re, subprocess, sys
from PIL import Image

raw, out, dev = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    dump = subprocess.run(["adb", "-s", dev, "shell", "dumpsys", "window", "windows"],
                          capture_output=True, text=True, timeout=60).stdout
except Exception as e:
    print("❌ dumpsys 失败:", e); sys.exit(1)

# 找到桌宠悬浮窗那一块（APPLICATION_OVERLAY = 悬浮窗，区别于 MainActivity）
box = None
for blk in dump.split("Window #"):
    if "com.epinoia.deskpet" in blk and "APPLICATION_OVERLAY" in blk:
        m = re.search(r"frame=\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", blk)
        if m:
            box = tuple(int(x) for x in m.groups())
            break
if box is None:
    print("⚠️ 找不到悬浮窗坐标（桌宠没在跑？），整屏输出")
    box = None

im = Image.open(raw).convert("RGB")
W, H = im.size
if box:
    x1, y1, x2, y2 = box
    pad = 12
    x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
    x2, y2 = min(W, x2 + pad), min(H, y2 + pad)
    if x2 - x1 < 20 or y2 - y1 < 20:
        print(f"⚠️ 悬浮窗几乎全在屏幕外 {box}（peekOut 没生效？），改出整屏"); print(f"RAW={out}")
    else:
        im = im.crop((x1, y1, x2, y2))
        print(f"裁剪区域 ({x1},{y1})-({x2},{y2})  原窗口 {box}")

im = im.resize((im.width * 3, im.height * 3), Image.NEAREST)
im.save(out)
# 额外存一份固定名字，方便主人随时点开看最新那张
import shutil, os
latest = os.path.expanduser("~/storage/downloads/pet-最新.png")
try:
    shutil.copyfile(out, latest)
    print("LATEST=" + latest)
except Exception as e:
    print("latest copy failed:", e)
print(f"OUT={out}  {im.width}x{im.height}")
PY
