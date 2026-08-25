# AI 接入通道（AiChannel）

桌宠的「大脑」不绑死在某一家 AI 上。身体（App）通过 `AiChannel` 抽象和大脑说话，大脑可以是任何东西——这就是 README 里「大脑和身体分离」的落地接口。

## 三种接入方式（按场景选）

| 方式 | 适合场景 | 通道实现 | 延迟 | 说明 |
|------|----------|----------|------|------|
| **A. 对话 App 的 AI（间接）** | 你已经有固定的 AI 聊天 App（DeepSeek / ChatGPT 等），不想换 | 无（走后端表） | 秒级 | README 原架构：App 上报手势/app 事件到 Supabase，AI 下次对话读到；AI 写 `pet_state` 表 → App 轮询/Realtime 收到。**不新增任何大脑** |
| **B. API 直连（直接）** | 想让桌宠随时开口说话，不依赖你手动打开聊天 App | `DeepSeekChannel`（默认） | 秒级 | App 直接调 OpenAI 兼容 `/chat/completions`。DeepSeek / 通义 / Kimi / GLM / 本地 vLLM 全都兼容，只改 `BASE_URL` + `MODEL` |
| **C. Agent 桥接（本地/自托管）** | 想让你现有的 coding agent / MCP 机器人成为大脑 | 本地 HTTP 网关（待实现） | 秒级 | 在电脑/服务器上跑一个轻量网关：App → 网关 → 你的 agent。agent 拥有全部上下文和工具，可以真正「主动」推消息给桌宠 |

## 默认配置（本地内测版）

本地内测版默认走 **B：DeepSeek 直连**（`AI_CHANNEL=deepseek`）。

```
# 根目录 local.properties（已被 .gitignore 忽略，不会提交）
DEEPSEEK_API_KEY=sk-你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com   # 换供应商只改这里
DEEPSEEK_MODEL=deepseek-chat                 # 模型名
```

编译时 key/URL/模型会注入 `BuildConfig.*`，运行时只在内存中使用。

> ⚠️ 内测默认接 DeepSeek（也就是和你对话的「我」背后的模型）。
> 公开仓库（GitHub）不含任何密钥，只有通道抽象，key 永远在本地。

## 换供应商（OpenAI 兼容全家桶）

改 `local.properties` 里 `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` 两个字段即可，代码零改动：

| 供应商 | BASE_URL | MODEL 示例 |
|--------|----------|-----------|
| DeepSeek（默认） | `https://api.deepseek.com` | `deepseek-chat` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| Kimi (Moonshot) | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| GLM (智谱) | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| 本地 Ollama | `http://192.168.x.x:11434/v1` | `llama3.2`（本地跑） |
| 本地 vLLM | `http://192.168.x.x:8000/v1` | 你部署的模型 |

> 本地 Ollama / vLLM 走 http，需要 `usesCleartextTraffic`（Manifest 里已开启，公开版建议改 networkSecurityConfig 收紧）。

## 代码结构

```
app/src/main/java/com/example/deskpet/ai/
├── AiChannel.kt          ← 接口抽象 + 工厂（BuildConfig.AI_CHANNEL 选实现）
└── DeepSeekChannel.kt    ← 默认实现（OpenAI 兼容，HttpURLConnection + org.json）
```

新增通道三步：
1. 实现 `AiChannel` 接口（照抄 DeepSeekChannel 的骨架即可）
2. `AiChannel.create()` 的 `when` 加分支
3. build.gradle.kts 里加对应 `buildConfigField`

## 当前状态（骨架）

- [x] AiChannel 抽象
- [x] DeepSeekChannel（直连，可跑）
- [x] 方式 C 的 Agent 网关（本地 HTTP 桥）—— 已实现，见下方「Agent 桥接落地指南」
- [ ] 把手势/前台 app 事件接入 `reportEvent`（现为日志）
- [ ] 方式 A 的 Supabase 同步落地（文档已有，代码待写）
- [ ] 聊天记忆（把最近 N 条对话存本地，作为上下文发给 AI）

## Agent 桥接落地指南（方式 C，已实现）

App 内已内置本地 HTTP 服务（`PetOverlayService.startLocalServer()`，监听 `127.0.0.1:9001`），
**任何能访问本机 9001 端口的 agent / 脚本 / 服务器都能直接让桌宠说话**——这是自由度最高的通道。

### 接口一览

| 方法 | 路径 | 作用 |
|------|------|------|
| POST | `/say` 或 `/message` | 推一条消息给桌宠（JSON：`{"text":"...","action":"cute"}`，也兼容表单） |
| GET | `/status` | 查桌宠是否活着（返回 `{"ok":true,"status":"running"}`） |

消息格式：`动作名|文本` 或纯文本；动作可选 `happy/sleepy/angry/cry/proud/jump/wiggle/music/shock/think/celebrate/cute/run/roll`。

### 最快上手（curl 直接推）

```bash
curl -X POST http://127.0.0.1:9001/say \
  -H "Content-Type: application/json" \
  -d '{"text":"主人回来啦！","action":"cute"}'
```

### 把 agent 变成桌宠的大脑（推荐架构）

```
你的 agent（任意：本地脚本 / MCP server / 服务器上的 bot）
   │  ① 持有完整对话上下文、工具、记忆
   │  ② 需要桌宠开口时：POST /say
   ▼
Epinoia 桌宠（App，127.0.0.1:9001）→ 冒泡 + 动作
```

- **key 不进 App**：AI 供应商的 key 由 agent 侧持有（独立密钥文件 + `.gitignore` 保护），App 里不留任何密钥
- **有上下文**：agent 带着历史/情境去问 AI，桌宠的话更懂你
- **可监测**：agent 轮询 `/status`、读 `/sdcard/Deskpet/service.log`（生命周期）与 `crash.log`（崩溃）判断桌宠状态
- **零改动**：App 只需开启「本地 HTTP」开关（`pref_local_http`，默认开）

> ⚠️ 说明：本仓库只提交「接口文档与架构」；作者本地使用的桥接脚本（含其本机路径/端口习惯）
> 属于个人配置，不入库——每个使用者按上面接口自己写几行就能对接，通用且无兼容性包袱。
> 桥接脚本如果写成通用版（配置外置、不绑死路径），欢迎提交共享 🌚
