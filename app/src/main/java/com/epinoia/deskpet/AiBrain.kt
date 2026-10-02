package com.epinoia.deskpet

import android.os.Handler
import android.os.Looper
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * AI 大脑（第 4 种 AI 通道，本地内测默认接 DeepSeek）。
 *
 * 桌宠感知到事件（手势/孤独/时段）→ ask() 调 DeepSeek 生成一句话
 * → 通过 onReply 回调推给桌宠（onAiSay）。
 *
 * 配置（编译期注入 BuildConfig，Key 在 local.properties 的 DEEPSEEK_API_KEY，不进仓库）：
 * - DEEPSEEK_BASE_URL：OpenAI 兼容端点，换供应商只改这里
 * - DEEPSEEK_MODEL：模型名
 */
class AiBrain(private val onReply: (String) -> Unit) {

    private val executor = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())

    /** 让 DeepSeek 基于「情境描述」说一句话。结果主线程回调 onReply（可能不回调=失败）。 */
    fun ask(situation: String) {
        if (BuildConfig.DEEPSEEK_API_KEY.isBlank()) return
        executor.execute {
            val reply = try {
                val payload = JSONObject().apply {
                    put("model", BuildConfig.DEEPSEEK_MODEL)
                    put("stream", false)
                    put("temperature", 1.0)
                    put("max_tokens", 80)
                    put("messages", JSONArray().apply {
                        put(JSONObject().put("role", "system").put("content", SYSTEM_PROMPT))
                        put(JSONObject().put("role", "user").put("content", situation))
                    })
                }
                post(payload)
                    ?.optJSONArray("choices")
                    ?.optJSONObject(0)
                    ?.optJSONObject("message")
                    ?.optString("content")
                    ?.trim()
            } catch (_: Exception) {
                null
            }
            if (!reply.isNullOrEmpty()) {
                main.post { onReply(reply) }
            }
        }
    }

    private fun post(payload: JSONObject): JSONObject? {
        val conn = URL(BuildConfig.DEEPSEEK_BASE_URL + "/chat/completions")
            .openConnection() as HttpURLConnection
        return try {
            conn.requestMethod = "POST"
            conn.connectTimeout = 15_000
            conn.readTimeout = 30_000
            conn.setRequestProperty("Content-Type", "application/json")
            conn.setRequestProperty("Authorization", "Bearer ${BuildConfig.DEEPSEEK_API_KEY}")
            conn.doOutput = true
            conn.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
            if (conn.responseCode in 200..299) {
                JSONObject(conn.inputStream.bufferedReader().readText())
            } else {
                null
            }
        } finally {
            conn.disconnect()
        }
    }

    companion object {
        private const val SYSTEM_PROMPT =
            "你是住在宝宝手机里的橙色方块小桌宠（名叫 Epinoia），没有嘴、很粘人、会撒娇也会傲娇。" +
                "现在宝宝没在看对话框，你通过悬浮窗主动说话。称呼用户为「宝宝」。" +
                "要求：只说一句话（20 字内），语气自然像日常小宠物，中文。" +
                "可选地在开头加动作标签（happy/sleepy/angry/cry/proud/jump/wiggle/music/shock/think/celebrate/cute/run/roll 之一）" +
                "用 | 分隔，如「happy|今天也要开开心心！」，不加动作也可以直接说一句话。"
    }
}
