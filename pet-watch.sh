#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# 一起刷视频 · 对话回路（阶段2）
#
# 用法：
#   pet-watch "我刷到一个猫在键盘上打滚的视频，笑死"
#   pet-watch                 # 不带内容：让桌宠就着当前情境自己说一句
#
# 眼睛是宝宝的、嘴是桌宠的、脑子是 agent：
#   ① 读桌宠 /status 拿到情境（前台 app、刷了多久、时段、孤独度、刚说过什么）
#   ② 读 /sdcard/Deskpet/chat_log.txt 尾部接上刚才的对话
#   ③ 以桌宠人格生成一句贴合当下的反应
#   ④ POST /say 让桌宠冒泡 + 做动作；POST /log 把宝宝说的话记进流水
# ============================================================
set -uo pipefail

PET_URL="${PET_URL:-http://127.0.0.1:9001}"
PROJECT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
KEY_FILE="$PROJECT_DIR/.zhipu-key"
CHAT_LOG="/sdcard/Deskpet/chat_log.txt"
ZHIPU_URL_DEFAULT="https://open.bigmodel.cn/api/paas/v4/chat/completions"
ZHIPU_URL="${ZHIPU_URL:-$ZHIPU_URL_DEFAULT}"
MODEL="${PET_MODEL:-glm-4-flash}"

SAW="${1:-}"

# ── 0. 前置检查 ────────────────────────────────────────────
[ -f "$KEY_FILE" ] || { echo "❌ 找不到密钥文件 $KEY_FILE"; exit 1; }
# .zhipu-key 是 shell 变量格式（与 pet-brain.sh 共用同一份，不入库）
set -a; . "$KEY_FILE" 2>/dev/null || true; set +a
ZHIPU_KEY="${ZHIPU_API_KEY:-${ZHIPU_KEY:-}}"
[ -n "$ZHIPU_KEY" ] || { echo "❌ 密钥没读到：$KEY_FILE 里应有 ZHIPU_API_KEY=..."; exit 1; }

STATUS="$(curl -s --max-time 4 "$PET_URL/status" 2>/dev/null)"
case "$STATUS" in
  *'"ok":true'*) : ;;
  *) echo "❌ 桌宠没应答（$PET_URL/status）。检查：桌宠是否在跑、设置里「本地 HTTP」是否开着。"; exit 1 ;;
esac

# ── 1. 情境 + 最近对话（交给 python 拼好，避免手搓 JSON）────
CTX="$(python3 - "$STATUS" "$CHAT_LOG" "$SAW" <<'PYEOF'
import json, sys, os
status, log_path, saw = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    st = json.loads(status)
except Exception:
    st = {}
pet = st.get("pet", {}) or {}
recent = st.get("recentSaid", []) or []

lines = []
lines.append(f"当前时段：{pet.get('period','未知')}")
fg = pet.get("foreground", "未知")
lines.append(f"前台 app：{fg}")
if pet.get("douyinMinutes", 0):
    lines.append(f"已连续刷抖音：{pet['douyinMinutes']} 分钟")
lines.append(f"孤独等级：{pet.get('lonelyStage', 0)}/4")
if recent:
    lines.append("桌宠最近说过：" + " / ".join(recent[-3:]))

# chat_log 尾部：接住刚才的对话
tail = []
try:
    with open(log_path, encoding="utf-8") as f:
        for ln in f.read().splitlines()[-8:]:
            parts = ln.split("\t")
            if len(parts) >= 3:
                tail.append(f"{parts[1]}：{parts[2]}")
except Exception:
    pass
if tail:
    lines.append("刚才的对话（新→旧）：" + " | ".join(reversed(tail)))

print("；".join(lines))
PYEOF
)"

# ── 2. 生成反应 ────────────────────────────────────────────
SITUATION="${SAW:-（宝宝没说话，你自己找点话说）}"
REPLY="$(python3 - "$ZHIPU_KEY" "$ZHIPU_URL" "$MODEL" "$SITUATION" "$CTX" <<'PYEOF'
import json, sys, urllib.request
key, url, model, situation, ctx = sys.argv[1:6]

system = (
    "你是住在宝宝手机里的橙色方块小桌宠（名叫 Epinoia），没有嘴、很粘人、会撒娇也会傲娇，称呼用户为「宝宝」。"
    "现在你和宝宝一起刷视频/看东西：宝宝把他看到的内容告诉你，你要像一起看的小伙伴那样接话"
    "（好奇、吐槽、跟着笑、吃醋、关心都行），别像助手那样解释或总结。"
    "要求：只说一句话（20 字内），语气自然像日常小宠物，中文。"
    "可选地在开头加动作标签（happy/sleepy/angry/cry/proud/jump/wiggle/music/shock/think/celebrate/cute/run/roll/blush/stareyes/sweat/heartburst/firework/note 之一）用 | 分隔，"
    "如「happy|这个我也要看！」，不加动作也可以。"
)
user = f"【当下情境】{ctx}\n【宝宝刚说】{situation}\n请回一句。"

payload = {
    "model": model,
    "stream": False,
    "temperature": 1.0,
    "max_tokens": 60,
    "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ],
}
req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode(),
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    print(data["choices"][0]["message"]["content"].strip())
except Exception as e:
    detail = ""
    try:
        detail = e.read().decode()[:200]      # 接口返回的错误详情（不含密钥）
    except Exception:
        pass
    sys.stderr.write(f"❌ 生成失败：{e} {detail}\n")
    sys.exit(3)
PYEOF
)"
[ -z "$REPLY" ] && { echo "❌ 没拿到回话"; exit 1; }

# ── 3. 拆动作标签 → 推给桌宠 ───────────────────────────────
ACTION=""
TEXT="$REPLY"
case "$REPLY" in
  *"|"*)
    RAW_ACTION="${REPLY%%|*}"
    RAW_TEXT="${REPLY#*|}"
    # 收口常见近义词（模型爱自己造词，如 wriggle/wobble）
    case "$RAW_ACTION" in
      wriggle|wobble|wiggle|shake|扭) ACTION="wiggle" ;;
      laugh|laughing|joy|smile|开心) ACTION="happy" ;;
      dance|dancing|sing|singing) ACTION="music" ;;
      surprise|shocked) ACTION="shock" ;;
      crybaby|sad|teary) ACTION="cry" ;;
      angry|mad|pout) ACTION="angry" ;;
      sleep|sleeping|yawn|tired) ACTION="sleepy" ;;
      happy|jump|proud|music|shock|think|celebrate|cute|run|roll|cry|angry|sleepy|wiggle|blush|stareyes|sweat|heartburst|firework|note) ACTION="$RAW_ACTION" ;;
      # 认不出来就当没写动作，且不要把这个词留在台词里
      *) ACTION="" ;;
    esac
    TEXT="$RAW_TEXT"
    ;;
esac

python3 - "$PET_URL" "$TEXT" "$ACTION" <<'PYEOF'
import json, sys, urllib.request
url, text, action = sys.argv[1:4]
body = json.dumps({"text": text, "action": action}).encode()
req = urllib.request.Request(url + "/say", data=body,
                             headers={"Content-Type": "application/json"})
try:
    urllib.request.urlopen(req, timeout=6).read()
except Exception as e:
    sys.stderr.write(f"❌ 推送失败：{e}\n")
    sys.exit(4)
PYEOF

# ── 4. 把宝宝说的话记进流水（供下一轮当上下文）─────────────
if [ -n "$SAW" ]; then
  python3 - "$PET_URL" "$SAW" <<'PYEOF'
import json, sys, urllib.request
url, saw = sys.argv[1:3]
body = json.dumps({"text": saw}).encode()
req = urllib.request.Request(url + "/log", data=body,
                             headers={"Content-Type": "application/json"})
try:
    urllib.request.urlopen(req, timeout=6).read()
except Exception:
    pass
PYEOF
fi

echo "🐾 桌宠：${ACTION:+[$ACTION] }$TEXT"
