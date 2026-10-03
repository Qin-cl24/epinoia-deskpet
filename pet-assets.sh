#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# 桌宠素材扫描：把素材夹里的新图交给视觉模型识图，汇总成素材清单
#
# 用法：
#   pet-assets                    # 扫描默认素材夹，只处理没读过的
#   pet-assets --all              # 全部重扫（忽略已读记录）
#   pet-assets "/sdcard/某目录"    # 指定别的文件夹
#
# 素材从哪来都行：小红书保存的、网上存的、你自己截的。
# 输出的《素材清单.md》用来看"哪些能做进桌宠、哪些做不了"。
# ============================================================
set -u

# Termux 里 TMPDIR 默认未设置，脚本自备（否则 set -u 直接报 unbound）
TMPDIR="${TMPDIR:-${PREFIX:-/data/data/com.termux/files/usr}/tmp}"
mkdir -p "$TMPDIR"

DEFAULT_DIR="/sdcard/Deskpet/素材"
SEEN="$HOME/.deskpet-assets-seen"
SCAN_ALL=0
DIR=""

for arg in "$@"; do
  case "$arg" in
    --all) SCAN_ALL=1 ;;
    *) DIR="$arg" ;;
  esac
done
DIR="${DIR:-$DEFAULT_DIR}"
LIST="$DIR/素材清单.md"

# 凭据：与 vision_understand 工具共用同一份
if [ -f "$HOME/.dsh/vision.env" ]; then
  set -a; . "$HOME/.dsh/vision.env"; set +a
fi
API_KEY="${VISION_API_KEY:-}"
MODEL="${VISION_MODEL:-glm-4v-flash}"

if [ -z "$API_KEY" ]; then
  echo "❌ 没读到 VISION_API_KEY（应在 ~/.dsh/vision.env）"
  exit 1
fi

mkdir -p "$DIR"
[ "$SCAN_ALL" = "1" ] || touch "$SEEN"

# 识图：返回一句话描述（失败返回空）；anim=1 时按"4 帧动画"提问
img_desc() {
  local f="$1" anim="${2:-0}" mime="image/jpeg"
  case "$f" in
    *.png)  mime="image/png" ;;
    *.webp) mime="image/webp" ;;
    *.gif)  mime="image/gif" ;;
  esac
  local b64
  b64=$(base64 -w0 "$f" 2>/dev/null) || b64=$(base64 "$f" 2>/dev/null | tr -d '\n')
  [ -z "$b64" ] && return 1

  local prompt
  if [ "$anim" = "1" ]; then
    prompt="这是同一段动画按时间顺序抽出的 4 帧（左上→右上→左下→右下）。请用中文简短说明：1)画面里是什么形象 2)这 4 帧之间动作/表情怎么变化（动画节奏）3)如果要复刻这个动作，关键点是什么。总共 150 字以内。"
  else
    prompt="这是桌宠（方块小宠物）形象/动作的参考素材。请用中文简短回答三点：1)画面里是什么形象或动作 2)关键视觉元素（配件、颜色、表情、姿势）3)如果是多格/分镜序列，说明每格在做什么。总共 120 字以内。"
  fi

  # 注意：base64 可达数百 KB，必须走 stdin（--data-binary @-）；
  # 当命令行参数传会超 Termux 的 ARG_MAX 而静默失败（踩过）。
  printf '{"model":"%s","max_tokens":900,"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:%s;base64,%s"}},{"type":"text","text":"%s"}]}]}' "$MODEL" "$mime" "$b64" "$prompt" \
  | curl -s --max-time 120 https://open.bigmodel.cn/api/paas/v4/chat/completions \
      -H "Authorization: Bearer $API_KEY" \
      -H "Content-Type: application/json" \
      --data-binary @- 2>/dev/null \
  | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin)
    m=d["choices"][0]["message"]
    print((m.get("content") or "").replace("\n", " ").strip())
except Exception:
    pass' 2>/dev/null
}

# 动态照片（Motion Photo）/GIF → 抠出视频抽 4 帧拼成 2×2 连环图；成功输出图片路径
# 说明：安卓动态照片是「JPEG + 内嵌 MP4」，直接识图只能看到静态首帧，
#       所以先抠视频再抽帧，才看得出动作。
make_strip() {
  local f="$1" vid="" dur="" out="$TMPDIR/asset_strip_$$.png"
  case "$f" in
    *.gif|*.GIF) vid="$f" ;;
    *)
      if [ "$(head -c 2 "$f" | od -An -tx1 | tr -d ' \n')" = "ffd8" ]; then
        python3 - "$f" "$TMPDIR/asset_mv_$$.mp4" <<'PY' 2>/dev/null
import sys
try:
    d = open(sys.argv[1], 'rb').read()
    i = d.find(b'ftyp')
    if i > 0:
        open(sys.argv[2], 'wb').write(d[i-4:])
except Exception:
    pass
PY
        [ -s "$TMPDIR/asset_mv_$$.mp4" ] && vid="$TMPDIR/asset_mv_$$.mp4"
      fi
      ;;
  esac
  [ -z "$vid" ] && return 1

  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$vid" 2>/dev/null | head -1)
  case "$dur" in ''|*[!0-9.]*) dur=3 ;; esac
  ffmpeg -v error -i "$vid" -vf "fps=4/$dur,scale=220:-2,tile=2x2" -frames:v 1 "$out" -y 2>/dev/null
  rm -f "$TMPDIR/asset_mv_$$.mp4"
  if [ -s "$out" ]; then echo "$out"; else return 1; fi
}

# 静态图预处理：缩到最大边 1024（原图可能十几 MB，base64 后 API 又慢又易失败）
prep_image() {
  local f="$1" out="$TMPDIR/asset_img_$$.jpg"
  ffmpeg -v error -i "$f" -vf "scale='min(1024,iw)':-2" -frames:v 1 -q:v 4 "$out" -y 2>/dev/null
  if [ -s "$out" ]; then echo "$out"; else return 1; fi
}

[ -f "$LIST" ] || printf '# 桌面宠物素材清单\n\n> 由 pet-assets 自动生成：每张图的形象/动作要点，供挑选实现。\n\n' > "$LIST"

total=0; ok=0
shopt -s nullglob
for f in "$DIR"/*.jpg "$DIR"/*.jpeg "$DIR"/*.png "$DIR"/*.webp "$DIR"/*.gif; do
  key=$(basename "$f")
  if [ "$SCAN_ALL" = "0" ] && grep -qxF "$key" "$SEEN" 2>/dev/null; then
    continue
  fi
  total=$((total+1))
  # 动态照片/GIF → 先抠视频抽帧拼图，再按"动画"提问
  target=""; anim=0; tmpimg=""
  if strip=$(make_strip "$f"); then target="$strip"; anim=1; tmpimg="$strip"
  elif small=$(prep_image "$f"); then target="$small"; tmpimg="$small"
  else target="$f"; fi
  if [ "$anim" = "1" ]; then printf '→ 识图 %s（动图·已抽 4 帧）... ' "$key"; else printf '→ 识图 %s ... ' "$key"; fi
  desc=$(img_desc "$target" "$anim")
  [ -n "$tmpimg" ] && rm -f "$tmpimg"
  if [ -n "$desc" ]; then
    ok=$((ok+1))
    printf -- '- **%s**：%s\n' "$key" "$desc" >> "$LIST"
    echo "ok"
  else
    printf -- '- **%s**：（识图失败，可稍后重跑）\n' "$key" >> "$LIST"
    echo "失败"
  fi
  [ "$SCAN_ALL" = "0" ] && echo "$key" >> "$SEEN"
done

echo
echo "本次扫描 $total 张，成功 $ok 张"
echo "清单：$LIST"
