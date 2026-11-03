package com.epinoia.deskpet

import android.annotation.SuppressLint
import android.os.Bundle
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import androidx.appcompat.app.AppCompatActivity

/**
 * 狐狐的小屋（2026-10-29 新增）
 *
 * 占位版本：房间和家具全用 CSS 画（assets/room.html），狐狐还是那 34 层素材。
 * 交互：点床 → 去睡觉；点饭碗 → 吃饭；点收音机 → 跳舞；点窗台 → 看窗外；点狐狐 → 跳一下。
 * 页面里的图层坐标不是手写的，由 tools/build-room.py 从 assets/fox/_layers.json 生成，
 * 主人重导画稿后跑一次脚本 + 重新编译即可。
 */
class RoomActivity : AppCompatActivity() {

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val web = WebView(this)
        setContentView(web)
        web.settings.javaScriptEnabled = true
        web.settings.allowFileAccess = true
        web.setBackgroundColor(0xFFF6E3CF.toInt())
        web.webViewClient = WebViewClient()
        // 页面的 console 送到 logcat（tag RoomDebug），排查交互问题用
        web.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(m: ConsoleMessage): Boolean {
                android.util.Log.i("RoomDebug", "console[${m.messageLevel()}] ${m.message()} @${m.lineNumber()}")
                return true
            }
        }
        web.addJavascriptInterface(RoomBridge(), "RoomBridge")
        web.loadUrl("file:///android_asset/room.html")
    }

    /** JS 桥：方法必须写在下面这个 inner class 里，注册到 WebView 的才是 RoomBridge 对象 */
    inner class RoomBridge {
        /** 页面每次动作/移动上报一行状态，方便 adb logcat -s RoomDebug 验证交互 */
        @JavascriptInterface
        fun note(state: String) {
            android.util.Log.i("RoomDebug", state)
        }

        /** 顶栏 ⚙️：打开设置页 */
        @JavascriptInterface
        fun openSettings() {
            runOnUiThread {
                startActivity(android.content.Intent(this@RoomActivity, MainActivity::class.java))
            }
        }

        /** 页面里的 ✕ 调这里关掉小屋 */
        @JavascriptInterface
        fun close() {
            runOnUiThread { finish() }
        }
    }
}
