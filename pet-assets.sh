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

# 识图：返回一句话描述（失败返回空）
img_desc() {
  local f="$1" mime="image/jpeg"
  case "$f" in
    *.png)  mime="image/png" ;;
    *.webp) mime="image/webp" ;;
    *.gif)  mime="image/gif" ;;
  esac
  local b64
  b64=$(base64 -w0 "$f" 2>/dev/null) || b64=$(base64 "$f" 2>/dev/null | tr -d '\n')
  [ -z "$b64" ] && return 1

  # 注意：base64 可达数百 KB，必须走 stdin（--data-binary @-）；
  # 当命令行参数传会超 Termux 的 ARG_MAX 而静默失败（踩过）。
  printf '{"model":"%s","max_tokens":900,"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:%s;base64,%s"}},{"type":"text","text":"这是桌宠（方块小宠物）形象/动作的参考素材。请用中文简短回答三点：1)画面里是什么形象或动作 2)关键视觉元素（配件、颜色、表情、姿势）3)如果是多格/分镜序列，说明每格在做什么。总共 120 字以内。"}]}]}' "$MODEL" "$mime" "$b64" \
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

[ -f "$LIST" ] || printf '# 桌面宠物素材清单\n\n> 由 pet-assets 自动生成：每张图的形象/动作要点，供挑选实现。\n\n' > "$LIST"

total=0; ok=0
shopt -s nullglob
for f in "$DIR"/*.jpg "$DIR"/*.jpeg "$DIR"/*.png "$DIR"/*.webp "$DIR"/*.gif; do
  key=$(basename "$f")
  if [ "$SCAN_ALL" = "0" ] && grep -qxF "$key" "$SEEN" 2>/dev/null; then
    continue
  fi
  total=$((total+1))
  printf '→ 识图 %s ... ' "$key"
  desc=$(img_desc "$f")
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
