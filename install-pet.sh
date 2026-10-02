#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# 桌宠一键构建 + 安装（Termux / 无线调试）
# 用法： pet-install [无线调试端口]
#   pet-install          # 已连接过就直接装
#   pet-install 36569    # 没连过时用端口连一次（端口在「无线调试」页看）
# 做的事：增量构建 → 覆盖安装（同签名，设置不丢）→ 拉起桌宠 → 校验包一致 + 台词检查
# ============================================================
set -uo pipefail

export TMPDIR="${TMPDIR:-$PREFIX/tmp}"
# 解析真实路径（脚本可能被 $PREFIX/bin/pet-install 软链调用）
SELF="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
PROJECT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
APK="$PROJECT_DIR/app/build/outputs/apk/debug/app-debug.apk"
PKG="com.epinoia.deskpet"
ACTIVITY="$PKG/.MainActivity"
PORT="${1:-}"

WLAN_IP="$(ip -4 addr show wlan0 2>/dev/null | grep -oE 'inet [0-9.]+' | awk '{print $2}' | head -1)"

# ── 1. 找设备 ──────────────────────────────────────────────
DEV="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')"
if [ -z "$DEV" ]; then
  if [ -z "$PORT" ]; then
    echo "❌ 没有已连接的设备，也没给端口。"
    echo "   请在 设置 → 开发者选项 → 无线调试 里看「IP 地址和端口」，然后："
    echo "     pet-install <端口>        # 例如 pet-install 36569"
    [ -n "$WLAN_IP" ] && echo "   （本机 wlan0 IP 是 $WLAN_IP）"
    exit 1
  fi
  HOST="${WLAN_IP:-127.0.0.1}"
  echo "🔌 连接 $HOST:$PORT ..."
  adb connect "$HOST:$PORT" >/dev/null 2>&1 || true
  sleep 1
  DEV="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')"
  [ -z "$DEV" ] && { echo "❌ 连接失败：端口可能变了，或需要在「无线调试」里重新配对"; exit 1; }
fi
echo "📱 设备：$DEV"

# ── 2. 构建 ───────────────────────────────────────────────
echo "🔨 构建中（增量一般 1 分钟内）..."
if ! (cd "$PROJECT_DIR" && ./gradlew assembleDebug --console=plain 2>&1 | tail -3); then
  echo "❌ 构建失败，已中止"; exit 1
fi
[ -f "$APK" ] || { echo "❌ 没找到产物 $APK"; exit 1; }

# ── 3. 安装 ───────────────────────────────────────────────
echo "📦 覆盖安装中..."
# 用 --no-streaming：先 push 到设备再装。无线调试下 streamed install 偶发卡死，
# 这条道稳定得多（本地设备 push 速度约 175MB/s，几乎无额外开销）。
if ! timeout 150 adb -s "$DEV" install -r --no-streaming "$APK" 2>&1 | tail -3; then
  echo "❌ 安装失败（签名不一致？那就得先卸载旧版，设置会丢）"; exit 1
fi

# ── 4. 拉起桌宠 ────────────────────────────────────────────
echo "🚀 拉起桌宠..."
adb -s "$DEV" shell am start -n "$ACTIVITY" >/dev/null 2>&1 || true
sleep 3

# ── 5. 校验 ───────────────────────────────────────────────
LOCAL_SHA="$(sha256sum "$APK" | awk '{print $1}')"
REMOTE_PATH="$(adb -s "$DEV" shell pm path "$PKG" 2>/dev/null | head -1 | tr -d '\r' | sed 's/^package://')"
REMOTE_SHA="$(adb -s "$DEV" shell "sha256sum '$REMOTE_PATH'" 2>/dev/null | awk '{print $1}' | tr -d '\r')"

echo "─────────────────────────────────"
if [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
  echo "✅ 手机上装的正是这次构建的包（sha256 ${LOCAL_SHA:0:12}…）"
else
  echo "⚠️ 哈希不一致：本地 ${LOCAL_SHA:0:12}… / 手机 ${REMOTE_SHA:0:12}…"
fi
PID="$(adb -s "$DEV" shell pidof "$PKG" 2>/dev/null | tr -d '\r')"
[ -n "$PID" ] && echo "✅ 桌宠进程在跑（pid $PID）" || echo "⚠️ 没看到桌宠进程，可能要手动点一下图标"

# 台词自检：宝宝有几处、主人还剩几处
if unzip -p "$APK" assets/pet.html >"$TMPDIR/pet_check.html" 2>/dev/null; then
  BB="$(grep -c "宝宝" "$TMPDIR/pet_check.html" || true)"
  ZR="$(grep -c "主人" "$TMPDIR/pet_check.html" || true)"
  echo "📝 台词自检：包内 pet.html 含「宝宝」$BB 行，「主人」$ZR 行"
  rm -f "$TMPDIR/pet_check.html"
fi
echo "─ 完成，去戳一下桌宠吧 ─"
