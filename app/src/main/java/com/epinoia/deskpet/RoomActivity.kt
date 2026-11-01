package com.epinoia.deskpet

import android.annotation.SuppressLint
import android.os.Bundle
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
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
        web.addJavascriptInterface(RoomBridge(), "RoomBridge")
        web.loadUrl("file:///android_asset/room.html")
    }

    /** 页面里的 ✕ 调这里关掉小屋 */
    inner class RoomBridge {
        @JavascriptInterface
        fun close() {
            runOnUiThread { finish() }
        }
    }
}
