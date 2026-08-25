package com.epinoia.deskpet

import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.ValueAnimator
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.ServiceInfo
import android.graphics.Insets
import android.os.Build
import android.os.Environment
import android.os.FileObserver
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.view.MotionEvent
import android.view.View
import android.view.WindowInsets
import android.view.WindowManager
import android.webkit.JavascriptInterface
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.core.app.NotificationCompat
import org.json.JSONObject
import java.io.BufferedReader
import java.io.File
import java.io.InputStreamReader
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.URL
import java.net.URLDecoder
import java.util.Locale
import kotlin.math.abs
import kotlin.math.sqrt

/**
 * Epinoia 桌宠悬浮窗核心服务。
 * 功能：贴边半透明 / 边缘跑 / 躲猫猫 / 连击 / 孤独递进 / 键盘感知 / 喝水(在 pet.html) /
 *       AI 消息通道（文件 + 外部后端 + 本地 HTTP 9001）
 */
class PetOverlayService : Service() {

    companion object {
        private const val CHANNEL_ID = "deskpet_overlay"
        private const val NOTIFICATION_ID = 1

        private const val PET_WIDTH_DP = 72
        private const val PET_HEIGHT_DP = 72
        private const val MAX_PET_WIDTH_DP = 180   // 尺寸最大档（对应 pet.html 130×60 放大 2.5 倍）
        private const val MAX_PET_HEIGHT_DP = 180
        private const val HANDLE_W_DP = 26
        private const val HANDLE_H_DP = 52
        private const val DOCK_EDGE_MARGIN_DP = 16

        private const val DOCKED_ALPHA = 0.5f
        private const val DOCK_ANIM_MS = 300L

        // 贴边露出量：主体滑出屏幕外，但留一条可见的桌宠身体（悬浮球式半透明条）
        private const val VISIBLE_EDGE_DP = 14
        // body 在窗口内的宽度占比（52/72，zoom 放大时同比例，恒成立）
        private const val BODY_WINDOW_RATIO = 0.722f

        private const val IDLE_TIMEOUT_MS = 10_000L       // 无操作 10s → 贴边
        private const val HIDE_DELAY_MS = 60_000L         // 贴边 60s → 缩成手柄
        private const val LONELY_INTERVAL_MS = 300_000L   // 5 分钟无互动 → 孤独递进

        private const val DOUBLE_TAP_TIMEOUT = 300L
        private const val LONG_PRESS_TIMEOUT = 600L
        private const val MOVE_THRESHOLD = 10
        private const val FLING_DISTANCE = 200.0          // px
        private const val FLING_TIME_MS = 400L

        private const val PREFS_NAME = "deskpet_prefs"
        private const val MSG_FILE = "/sdcard/Deskpet/messages.txt"
        private const val LOCAL_PORT = 9001
    }

    private var windowManager: WindowManager? = null
    private var overlayView: WebView? = null
    private var params: WindowManager.LayoutParams? = null

    // 贴边 / 手柄 / 隐藏状态
    private var docked = false
    private var dockSide = -1
    private var hidden = false
    private var petW = 0
    private var petH = 0
    private var petX = 0
    private var petY = 0
    private var edgeAnimator: ValueAnimator? = null

    // 孤独 / 键盘
    private var lonelyStage = 0
    private var keyboardVisible = false
    private var imeHeightPx = 0
    private var posBeforeKeyboardY = 0

    // 触摸状态
    private var initialX = 0
    private var initialY = 0
    private var initialTouchX = 0f
    private var initialTouchY = 0f
    private var touchStartTime = 0L
    private var hasMoved = false
    private var tapCount = 0
    private var firstTapTime = 0L

    // 定时器
    private val handler = Handler(Looper.getMainLooper())
    private val edgeRunHandler = Handler(Looper.getMainLooper())
    private val peekabooHandler = Handler(Looper.getMainLooper())
    private val aiHandler = Handler(Looper.getMainLooper())
    private val hideHandler = Handler(Looper.getMainLooper())

    // AI 消息去重
    private var aiLastContent = ""
    private var aiLinkLast = ""

    // 本地 HTTP 服务（127.0.0.1:9001）
    private var httpServer: ServerSocket? = null
    private var httpThread: Thread? = null

    // 截图检测：截图时临时隐藏桌宠，避免入镜
    private val screenshotObservers = mutableListOf<FileObserver>()

    // AI 大脑（第 4 通道：DeepSeek，本地内测）
    private var aiBrain: AiBrain? = null
    private var lastAiSpeakAt = 0L
    private val aiSpeakCooldownMs = 5 * 60 * 1000L   // 两次主动说话至少间隔 5 分钟
    private val brainTickHandler = Handler(Looper.getMainLooper())

    private val idleRunnable = Runnable { dockToEdge() }
    private val lonelyRunnable = Runnable { advanceLoneliness() }
    private val hideRunnable = Runnable { toHandleMode() }
    private val aiWatchRunnable = Runnable { watchAiMessages() }

    // ============ 生命周期 ============

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        logLifecycle("onStartCommand")
        // START_STICKY：被系统杀掉后，条件允许时自动重建（基础保活）
        return START_STICKY
    }

    override fun onCreate() {
        super.onCreate()
        logLifecycle("onCreate")
        startAsForeground()
        Toast.makeText(this, "Epinoia 桌宠正在启动...", Toast.LENGTH_SHORT).show()
        setupOverlay()
    }

    override fun onDestroy() {
        logLifecycle("onDestroy")
        handler.removeCallbacks(idleRunnable)
        handler.removeCallbacks(lonelyRunnable)
        edgeRunHandler.removeCallbacksAndMessages(null)
        peekabooHandler.removeCallbacksAndMessages(null)
        aiHandler.removeCallbacksAndMessages(null)
        hideHandler.removeCallbacksAndMessages(null)
        brainTickHandler.removeCallbacksAndMessages(null)
        edgeAnimator?.cancel()
        screenshotObservers.forEach { it.stopWatching() }
        screenshotObservers.clear()
        try {
            httpServer?.close()
        } catch (_: Exception) {
        }
        httpThread?.interrupt()
        overlayView?.let { v ->
            windowManager?.removeView(v)
            v.destroy()
        }
        overlayView = null
        super.onDestroy()
    }

    // ============ 启动 ============

    private fun startAsForeground() {
        val channel = NotificationChannel(CHANNEL_ID, "桌宠悬浮窗", NotificationManager.IMPORTANCE_LOW)
            .apply { setShowBadge(false) }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)

        val pendingIntent = PendingIntent.getActivity(
            this, 0,
            packageManager.getLaunchIntentForPackage(packageName),
            PendingIntent.FLAG_IMMUTABLE
        )
        val notification: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("🧡 Epinoia 桌宠")
            .setContentText("点击返回应用")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setSilent(true)
            .build()
        // Android 15+ 强制要求传 type（不传会抛 MissingForegroundServiceTypeException 崩溃）
        startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
    }

    private fun setupOverlay() {
        try {
            windowManager = getSystemService(WINDOW_SERVICE) as WindowManager

            // 尺寸档位：0 = 最小（72dp 窗口 / pet 52×24），100 = 最大（180dp 窗口 / pet 130×60）
            val t = petSizeRatio()
            val winW = dpToPx(PET_WIDTH_DP + ((MAX_PET_WIDTH_DP - PET_WIDTH_DP) * t).toInt())
            val winH = dpToPx(PET_HEIGHT_DP + ((MAX_PET_HEIGHT_DP - PET_HEIGHT_DP) * t).toInt())

            params = WindowManager.LayoutParams(
                winW,
                winH,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                android.graphics.PixelFormat.TRANSLUCENT
            ).apply {
                gravity = android.view.Gravity.TOP or android.view.Gravity.START
                x = dpToPx(20)
                y = dpToPx(250)
            }

            overlayView = WebView(this).apply {
                setBackgroundColor(0x00000000)
                settings.apply {
                    javaScriptEnabled = true
                    domStorageEnabled = true
                    allowFileAccess = true
                    cacheMode = WebSettings.LOAD_DEFAULT
                }
                webViewClient = WebViewClient()
                // JS 桥：pet.html 里用 AndroidBridge.getPref / AndroidBridge.peekOut
                addJavascriptInterface(AndroidBridge(), "AndroidBridge")
                if (Build.VERSION.SDK_INT >= 30) {
                    setOnApplyWindowInsetsListener { _, insets -> onWindowInsets(insets) }
                }
                loadUrl("file:///android_asset/pet.html")
                setOnTouchListener(createTouchListener())
            }

            windowManager?.addView(overlayView, params)
            resetIdleTimer()
            resetLonelyTimer()
            scheduleEdgeRun()
            schedulePeekaboo()
            scheduleAiWatch()
            startLocalServer()
            scheduleBrainTick()
            startScreenshotWatch()
            Toast.makeText(this, "桌宠已上线！", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            logLifecycle("setupOverlay FAILED: $e")
            Toast.makeText(this, "启动失败：${e.message}", Toast.LENGTH_LONG).show()
            stopSelf() // 优雅停止，避免进程崩溃带崩主界面
        }
    }

    // ============ JS 桥（pet.html 调用）============

    /** 修复：原版把 WebView 自身注册成了 AndroidBridge，getPref/peekOut 实际失效；
     *  这里用真正的 Bridge 对象，让 pet.html 的开关与贴边弹出真正生效。 */
    inner class AndroidBridge {
        @JavascriptInterface
        fun getPref(key: String, def: Boolean): Boolean = prefBool(key, def)

        @JavascriptInterface
        fun peekOut() {
            if (docked) undock()
            resetIdleTimer()
        }

        /** 桌宠缩放比：1.0（52×24）~ 2.5（130×60），pet.html 按此缩放 */
        @JavascriptInterface
        fun getPetScale(): Float = 1f + 1.5f * petSizeRatio()
    }

    /** pref_pet_size（0~100）→ 0.0~1.0 */
    private fun petSizeRatio(): Float {
        val v = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
            .getInt("pref_pet_size", 0).coerceIn(0, 100)
        return v / 100f
    }

    private fun onWindowInsets(insets: WindowInsets): WindowInsets {
        if (prefBool("pref_keyboard", true)) {
            val ime = insets.getInsets(WindowInsets.Type.ime())
            if (ime.bottom > 0 && !keyboardVisible) {
                keyboardVisible = true
                imeHeightPx = ime.bottom
                onKeyboardShow()
            } else if (ime.bottom == 0 && keyboardVisible) {
                keyboardVisible = false
                imeHeightPx = 0
                onKeyboardHide()
            }
        }
        return insets
    }

    // ============ 手势 ============

    private fun createTouchListener(): View.OnTouchListener {
        return View.OnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    hideHandler.removeCallbacks(hideRunnable)
                    if (hidden) {
                        initialX = params?.x ?: 0
                        initialY = params?.y ?: 0
                        initialTouchX = event.rawX
                        initialTouchY = event.rawY
                        touchStartTime = System.currentTimeMillis()
                        hasMoved = false
                    } else {
                        if (docked) undock()
                        overlayView?.evaluateJavascript("window.wakeUp && window.wakeUp()", null)
                        resetLonelyTimer()
                        edgeAnimator?.cancel()
                        scheduleEdgeRun()
                        schedulePeekaboo()
                        initialX = params?.x ?: 0
                        initialY = params?.y ?: 0
                        initialTouchX = event.rawX
                        initialTouchY = event.rawY
                        touchStartTime = System.currentTimeMillis()
                        hasMoved = false
                        resetIdleTimer()
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (hidden) {
                        if (hasMoved) snapHandle() else toPetMode()
                        return@OnTouchListener true
                    }
                    resetIdleTimer()
                    val elapsed = System.currentTimeMillis() - touchStartTime
                    if (hasMoved) {
                        val dx = event.rawX - initialTouchX
                        val dy = event.rawY - initialTouchY
                        if (sqrt(dx * dx + dy * dy) <= FLING_DISTANCE || elapsed >= FLING_TIME_MS) {
                            onDragEnd()
                        } else {
                            onFling()
                        }
                        return@OnTouchListener true
                    }
                    val now = System.currentTimeMillis()
                    if (elapsed > LONG_PRESS_TIMEOUT) {
                        tapCount = 0
                        onLongPress()
                        return@OnTouchListener true
                    }
                    if (now - firstTapTime > 2000) {
                        tapCount = 0
                        firstTapTime = now
                    }
                    if (tapCount == 0) firstTapTime = now
                    tapCount++
                    when (tapCount) {
                        2 -> onDoubleTap()
                        3 -> onCombo3()
                        5 -> onCombo5()
                        8 -> {
                            onCombo8()
                            tapCount = 0
                        }
                        else -> onTap()
                    }
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    if (hidden) {
                        params?.let { p ->
                            p.x = initialX + (event.rawX - initialTouchX).toInt()
                            p.y = initialY + (event.rawY - initialTouchY).toInt()
                            overlayView?.let { windowManager?.updateViewLayout(it, p) }
                        }
                        hasMoved = true
                        return@OnTouchListener true
                    }
                    val dx = (event.rawX - initialTouchX).toInt()
                    val dy = (event.rawY - initialTouchY).toInt()
                    if (abs(dx) <= MOVE_THRESHOLD && abs(dy) <= MOVE_THRESHOLD) {
                        return@OnTouchListener true
                    }
                    hasMoved = true
                    params?.let { p ->
                        p.x = (initialX + dx).coerceIn(0, getScreenW() - p.width)
                        p.y = (initialY + dy).coerceIn(0, getScreenH() - p.height)
                        overlayView?.let { windowManager?.updateViewLayout(it, p) }
                    }
                    true
                }
                else -> false
            }
        }
    }

    // ============ 手势回调 → JS ============

    private fun onTap() {
        js("onTap()")
        maybeAiSpeak("主人刚刚戳了我一下，回应一句想说的话")
    }

    private fun onDoubleTap() {
        js("onDoubleTap()")
        maybeAiSpeak("主人刚刚双击了我，回应一句开心的")
    }

    private fun onLongPress() {
        js("onLongPress()")
        maybeAiSpeak("主人刚刚长按了我，回应一句")
    }

    private fun onCombo3() {
        js("onCombo3()")
        maybeAiSpeak("主人刚刚连戳了我三下，回应一句")
    }

    private fun onCombo5() {
        js("onCombo5()")
        maybeAiSpeak("主人刚刚连戳了我五下，回应一句")
    }

    private fun onCombo8() {
        js("onCombo8()")
        maybeAiSpeak("主人刚刚连戳了我八下，回应一句又惊又气的话")
    }

    private fun onDragEnd() = js("onDragEnd()")
    private fun onFling() = js("onFling()")

    private fun js(call: String) {
        overlayView?.evaluateJavascript("window.petEngine && window.petEngine.$call", null)
    }

    // ============ AI 大脑（DeepSeek 第 4 通道）============

    private fun ensureAiBrain(): AiBrain? {
        if (aiBrain == null && BuildConfig.DEEPSEEK_API_KEY.isNotBlank()) {
            aiBrain = AiBrain { reply -> handleAiMessage(reply) }
        }
        return aiBrain
    }

    /** 情境触发：桌宠想说话时调用。带开关 + 冷却控制。 */
    private fun maybeAiSpeak(situation: String) {
        if (!prefBool("pref_deepseek", true)) return
        val brain = ensureAiBrain() ?: return
        val now = System.currentTimeMillis()
        if (now - lastAiSpeakAt < aiSpeakCooldownMs) return
        lastAiSpeakAt = now
        brain.ask(situation)
    }

    /** 周期主动说话：每 20~40 分钟随机一次（时段感知）。 */
    private fun scheduleBrainTick() {
        brainTickHandler.removeCallbacksAndMessages(null)
        brainTickHandler.postDelayed({
            val hour = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY)
            val period = when {
                hour < 6 -> "深夜"
                hour < 9 -> "早晨"
                hour in 11..13 -> "中午"
                hour >= 22 -> "夜晚"
                else -> "白天"
            }
            maybeAiSpeak("现在是$period，主人可能在忙，主动说一句想说的话（关心/撒娇/自言自语都行）")
            scheduleBrainTick()
        }, 20 * 60 * 1000L + (Math.random() * 20 * 60 * 1000).toLong())
    }

    // ============ 贴边 / 手柄 / 弹出 ============

    private fun dockToEdge() {
        val p = params ?: return
        val left = p.x < (getScreenW() - p.width) / 2
        dockSide = if (left) -1 else 1
        docked = true
        // 贴边：主体滑出屏幕外，但露出一条桌宠身体（悬浮球式半透明条，始终可见）。
        // 原版露出的 16dp 是窗口透明边缘（body 在窗口中央），导致完全不可见。
        val inset = (p.width * (1f - BODY_WINDOW_RATIO) / 2f).toInt() // body 在窗口内的边距
        val visible = dpToPx(VISIBLE_EDGE_DP)                        // 贴边后露出的 body 宽度
        val targetX = if (left) -(p.width - inset - visible) else getScreenW() - (inset + visible)
        animateTo(targetX, DOCKED_ALPHA)
        hideHandler.removeCallbacks(hideRunnable)
        hideHandler.postDelayed(hideRunnable, HIDE_DELAY_MS)
    }

    private fun undock() {
        if (!docked) return
        docked = false
        params?.let { p ->
            p.x = if (dockSide >= 0) getScreenW() - p.width else 0
            p.alpha = 1.0f
            overlayView?.let { windowManager?.updateViewLayout(it, p) }
        }
    }

    private fun snapHandle() {
        val p = params ?: return
        val left = p.x < (getScreenW() - p.width) / 2
        p.x = if (left) 0 else getScreenW() - p.width
        p.y = p.y.coerceIn(0, getScreenH() - p.height)
        overlayView?.let { windowManager?.updateViewLayout(it, p) }
        overlayView?.evaluateJavascript("window.showHandle && showHandle($left)", null)
    }

    private fun toHandleMode() {
        if (hidden || !docked) return
        val p = params ?: return
        petW = p.width
        petH = p.height
        petX = p.x
        petY = p.y
        val left = petX < (getScreenW() - petW) / 2
        p.width = dpToPx(HANDLE_W_DP)
        p.height = dpToPx(HANDLE_H_DP)
        p.x = if (left) 0 else getScreenW() - p.width
        p.y = ((getScreenH() - p.height) / 2).coerceIn(0, getScreenH() - p.height)
        p.alpha = 1.0f
        hidden = true
        overlayView?.let { windowManager?.updateViewLayout(it, p) }
        overlayView?.evaluateJavascript("window.showHandle && showHandle($left)", null)
    }

    private fun toPetMode() {
        if (hidden) {
            params?.let { p ->
                p.width = petW
                p.height = petH
                p.x = petX.coerceIn(0, getScreenW() - p.width)
                p.y = petY.coerceIn(0, getScreenH() - p.height)
                p.alpha = 1.0f
                hidden = false
                overlayView?.let { windowManager?.updateViewLayout(it, p) }
                overlayView?.evaluateJavascript("window.showPet && showPet()", null)
                docked = false
                resetIdleTimer()
                resetLonelyTimer()
            }
        }
    }

    // ============ 边缘跑 ============

    private fun scheduleEdgeRun() {
        edgeRunHandler.removeCallbacksAndMessages(null)
        if (prefBool("pref_edge_run", true)) {
            edgeRunHandler.postDelayed({ edgeRun() }, (Math.random() * 30000).toLong() + 30000)
        }
    }

    private fun edgeRun() {
        hideHandler.removeCallbacks(hideRunnable)
        val p = params ?: return
        overlayView?.evaluateJavascript("window.petEngine && window.petEngine.onEdgeRun()", null)
        p.alpha = 1.0f
        overlayView?.let { windowManager?.updateViewLayout(it, p) }

        val margin = dpToPx(DOCK_EDGE_MARGIN_DP)
        val left = p.x < (getScreenW() - p.width) / 2
        val edgeX = if (left) -p.width + margin else getScreenW() - margin
        animateXTo(edgeX, 450L) {
            val topHalf = p.y < getScreenH() / 2
            val targetY = if (topHalf) getScreenH() - p.height - dpToPx(60) else dpToPx(60)
            animateYTo(targetY, 1600L) {
                docked = true
                dockSide = if (left) -1 else 1
                animateTo(p.x, DOCKED_ALPHA)
            }
        }
        scheduleEdgeRun()
    }

    // ============ 躲猫猫 ============

    private fun schedulePeekaboo() {
        peekabooHandler.removeCallbacksAndMessages(null)
        if (prefBool("pref_peekaboo", true)) {
            peekabooHandler.postDelayed({ peekaboo() }, (Math.random() * 4 * 60 * 1000).toLong() + 180000)
        }
    }

    private fun peekaboo() {
        hideHandler.removeCallbacks(hideRunnable)
        val p = params ?: return
        animateAlpha(0.0f, 250L) {
            p.x = (Math.random() * (getScreenW() - p.width)).toInt()
            p.y = (Math.random() * (getScreenH() - p.height)).toInt()
            overlayView?.let { windowManager?.updateViewLayout(it, p) }
            overlayView?.evaluateJavascript("window.petEngine && window.petEngine.onPeekaboo()", null)
            animateAlpha(1.0f, 250L) {}
        }
        schedulePeekaboo()
    }

    // ============ 孤独递进 ============

    private fun resetLonelyTimer() {
        lonelyStage = 0
        handler.removeCallbacks(lonelyRunnable)
        handler.postDelayed(lonelyRunnable, LONELY_INTERVAL_MS)
    }

    private fun advanceLoneliness() {
        if (lonelyStage >= 4) return
        lonelyStage++
        overlayView?.evaluateJavascript(
            "window.petEngine && window.petEngine.onLonely$lonelyStage()", null
        )
        maybeAiSpeak("主人好久没理我了（孤独第${lonelyStage}级），主动说一句撒娇或抱怨的话")
        if (lonelyStage < 4) {
            handler.postDelayed(lonelyRunnable, LONELY_INTERVAL_MS)
        }
    }

    // ============ 闲置贴边 ============

    private fun resetIdleTimer() {
        handler.removeCallbacks(idleRunnable)
        if (prefBool("pref_dock", true)) {
            handler.postDelayed(idleRunnable, IDLE_TIMEOUT_MS)
        }
    }

    // ============ 键盘感知 ============

    private fun onKeyboardShow() {
        val p = params ?: return
        posBeforeKeyboardY = p.y
        if (docked) undock()
        p.y = (getScreenH() - imeHeightPx - p.height).coerceAtLeast(0)
        overlayView?.let { windowManager?.updateViewLayout(it, p) }
        overlayView?.evaluateJavascript("window.petEngine && window.petEngine.onKeyboardUp()", null)
    }

    private fun onKeyboardHide() {
        params?.let { p ->
            p.y = posBeforeKeyboardY
            overlayView?.let { windowManager?.updateViewLayout(it, p) }
        }
        overlayView?.evaluateJavascript("window.petEngine && window.petEngine.onKeyboardHide()", null)
    }

    // ============ AI 消息通道 ============

    private fun scheduleAiWatch() {
        aiHandler.removeCallbacksAndMessages(null)
        aiHandler.postDelayed(aiWatchRunnable, 2000L)
    }

    private fun watchAiMessages() {
        if (prefBool("pref_ai_channel", true)) {
            try {
                val file = File(MSG_FILE)
                if (file.exists() && file.canRead()) {
                    val content = file.readText().trim()
                    if (content.isNotEmpty() && content != aiLastContent) {
                        aiLastContent = content
                        handleAiMessage(content)
                    }
                }
            } catch (_: Exception) {
            }
        }
        pollAiLink()
        aiHandler.postDelayed(aiWatchRunnable, 2000L)
    }

    /** 外部后端轮询：GET pref_ai_url，返回新内容即触发。 */
    private fun pollAiLink() {
        val prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
        val url = prefs.getString("pref_ai_url", "") ?: return
        if (url.isBlank()) return
        val key = prefs.getString("pref_ai_key", "")
        Thread {
            try {
                val conn = URL(url).openConnection() as HttpURLConnection
                conn.requestMethod = "GET"
                conn.connectTimeout = 5000
                conn.readTimeout = 5000
                if (!key.isNullOrBlank()) {
                    conn.setRequestProperty("Authorization", "Bearer $key")
                }
                if (conn.responseCode == 200) {
                    val body = conn.inputStream.bufferedReader().readText().trim()
                    if (body.isNotEmpty() && body != aiLinkLast) {
                        aiLinkLast = body
                        aiHandler.post { handleAiMessage(body) }
                    }
                }
                conn.disconnect()
            } catch (_: Exception) {
            }
        }.start()
    }

    /** 消息格式：「动作名|文本」或纯文本；支持 /say 的 JSON {text, action}。 */
    private fun handleAiMessage(content: String) {
        val parts = content.split("|")
        val action = parts.getOrElse(0) { "" }.trim()
        val text = if (parts.size > 1) parts[1].trim() else action
        val jsCall = if (parts.size > 1) {
            "window.petEngine && window.petEngine.onAiSay(${escapeJs(text)}, '${escapeJs(action)}')"
        } else {
            "window.petEngine && window.petEngine.onAiSay(${escapeJs(text)}, 'none')"
        }
        overlayView?.evaluateJavascript(jsCall, null)
        hideHandler.removeCallbacks(hideRunnable)
        if (docked) undock()
    }

    private fun escapeJs(s: String): String =
        "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

    // ============ 本地 HTTP 服务（127.0.0.1:9001）============

    private fun startLocalServer() {
        if (!prefBool("pref_local_http", true)) return
        try {
            httpServer = ServerSocket(LOCAL_PORT, 8, InetAddress.getByName("127.0.0.1"))
            val server = httpServer
            httpThread = Thread {
                while (!Thread.currentThread().isInterrupted) {
                    try {
                        val socket = server?.accept() ?: return@Thread
                        Thread {
                            try {
                                handleSocket(socket)
                            } catch (_: Exception) {
                            } finally {
                                try {
                                    socket.close()
                                } catch (_: Exception) {
                                }
                            }
                        }.start()
                    } catch (_: Exception) {
                        return@Thread
                    }
                }
            }.apply { isDaemon = true }
            httpThread?.start()
        } catch (_: Exception) {
        }
    }

    private fun handleSocket(socket: Socket) {
        val reader = BufferedReader(InputStreamReader(socket.getInputStream(), Charsets.UTF_8))
        val requestLine = reader.readLine() ?: return
        val parts = requestLine.split(" ")
        if (parts.size < 2) return
        val method = parts[0]
        val path = parts[1]

        var contentLength = 0
        var line: String? = reader.readLine()
        while (line != null && line.isNotEmpty()) {
            if (line.lowercase(Locale.ROOT).startsWith("content-length:")) {
                contentLength = line.substringAfter(":").trim().toIntOrNull() ?: 0
            }
            line = reader.readLine()
        }

        val body = if (contentLength > 0) {
            val chars = CharArray(contentLength)
            reader.read(chars)
            String(chars)
        } else ""

        var status = "200 OK"
        var responseBody: String
        when {
            method == "POST" && (path == "/say" || path == "/message") -> {
                val (text, action) = parseSayBody(body)
                val msg = if (action.isNotEmpty()) "$action|$text" else text
                aiHandler.post { handleAiMessage(msg) }
                responseBody = "{\"ok\":true}"
            }
            method == "GET" && path == "/status" -> {
                responseBody = "{\"ok\":true,\"status\":\"running\",\"port\":$LOCAL_PORT}"
            }
            else -> {
                status = "404 Not Found"
                responseBody = "{\"ok\":false,\"error\":\"not found\"}"
            }
        }

        val bytes = responseBody.toByteArray(Charsets.UTF_8)
        val out: OutputStream = socket.getOutputStream()
        out.write(
            ("HTTP/1.1 $status\r\n" +
                "Content-Type: application/json\r\n" +
                "Content-Length: ${bytes.size}\r\n" +
                "Connection: close\r\n\r\n").toByteArray(Charsets.UTF_8)
        )
        out.write(bytes)
        out.flush()
    }

    /** 兼容 JSON 与表单两种 body。 */
    private fun parseSayBody(body: String): Pair<String, String> {
        return try {
            val json = JSONObject(body)
            json.optString("text", "") to json.optString("action", "")
        } catch (_: Exception) {
            val text = Regex("text=([^&]*)").find(body)?.groupValues?.getOrNull(1) ?: ""
            val action = Regex("action=([^&]*)").find(body)?.groupValues?.getOrNull(1) ?: ""
            URLDecoder.decode(text, "UTF-8") to URLDecoder.decode(action, "UTF-8")
        }
    }

    // ============ 动画工具 ============

    private fun animateAlpha(target: Float, dur: Long, onEnd: () -> Unit) {
        val p = params ?: return
        val anim = ValueAnimator.ofFloat(p.alpha, target)
        anim.duration = dur
        anim.addUpdateListener { it ->
            p.alpha = it.animatedValue as Float
            overlayView?.let { windowManager?.updateViewLayout(it, p) }
        }
        anim.addListener(object : AnimatorListenerAdapter() {
            override fun onAnimationEnd(animation: Animator) = onEnd()
        })
        anim.start()
    }

    private fun animateTo(targetX: Int, targetAlpha: Float) {
        val p = params ?: return
        val startX = p.x
        val startAlpha = p.alpha
        val anim = ValueAnimator.ofFloat(0.0f, 1.0f)
        anim.duration = DOCK_ANIM_MS
        anim.addUpdateListener { it ->
            val t = it.animatedValue as Float
            p.x = startX + ((targetX - startX) * t).toInt()
            p.alpha = startAlpha + (targetAlpha - startAlpha) * t
            overlayView?.let { windowManager?.updateViewLayout(it, p) }
        }
        anim.start()
    }

    private fun animateXTo(target: Int, dur: Long, onEnd: () -> Unit) {
        val p = params ?: return
        edgeAnimator?.cancel()
        val anim = ValueAnimator.ofInt(p.x, target)
        anim.duration = dur
        anim.addUpdateListener { it ->
            p.x = it.animatedValue as Int
            overlayView?.let { windowManager?.updateViewLayout(it, p) }
        }
        anim.addListener(object : AnimatorListenerAdapter() {
            override fun onAnimationEnd(animation: Animator) = onEnd()
        })
        anim.start()
        edgeAnimator = anim
    }

    private fun animateYTo(target: Int, dur: Long, onEnd: () -> Unit) {
        val p = params ?: return
        edgeAnimator?.cancel()
        val anim = ValueAnimator.ofInt(p.y, target)
        anim.duration = dur
        anim.addUpdateListener { it ->
            p.y = it.animatedValue as Int
            overlayView?.let { windowManager?.updateViewLayout(it, p) }
        }
        anim.addListener(object : AnimatorListenerAdapter() {
            override fun onAnimationEnd(animation: Animator) = onEnd()
        })
        anim.start()
        edgeAnimator = anim
    }

    // ============ 截图检测（截图时不把桌宠拍进去）============

    /** 监听截图目录，检测到新截图 → 临时隐藏桌宠 1.5s 后恢复 */
    private fun startScreenshotWatch() {
        val paths = listOf(
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DCIM)
                .resolve("Screenshots").absolutePath,
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES)
                .resolve("Screenshots").absolutePath
        )
        for (path in paths) {
            val dir = File(path)
            if (!dir.exists()) continue
            try {
                val fo = object : FileObserver(dir.absolutePath, FileObserver.CREATE or FileObserver.MOVED_TO) {
                    override fun onEvent(event: Int, path: String?) {
                        if (path != null && isImageFile(path)) hideForScreenshot()
                    }
                }
                fo.startWatching()
                screenshotObservers.add(fo)
            } catch (_: Exception) {
            }
        }
    }

    private fun isImageFile(name: String): Boolean {
        val l = name.lowercase()
        return l.endsWith(".png") || l.endsWith(".jpg") || l.endsWith(".jpeg")
    }

    /** 截图瞬间把桌宠窗口透明化，8s 后恢复（避免被截进图里；系统无"截图前"事件，首次截图后开始生效） */
    private fun hideForScreenshot() {
        handler.post {
            val p = params ?: return@post
            if (p.alpha <= 0f) return@post
            val restoreAlpha = p.alpha
            p.alpha = 0f
            overlayView?.let { windowManager?.updateViewLayout(it, p) }
            handler.postDelayed({
                params?.let { q ->
                    q.alpha = restoreAlpha
                    overlayView?.let { windowManager?.updateViewLayout(it, q) }
                }
            }, 8000)
        }
    }

    // ============ 工具 ============

    /** 生命周期诊断日志（/sdcard/Deskpet/service.log）：判断掉后台是被杀还是崩溃 */
    private fun logLifecycle(msg: String) {
        try {
            val f = File("/sdcard/Deskpet/service.log")
            f.parentFile?.mkdirs()
            f.appendText("${System.currentTimeMillis()} $msg\n")
        } catch (_: Exception) {
        }
    }

    private fun prefBool(key: String, def: Boolean): Boolean =
        getSharedPreferences(PREFS_NAME, MODE_PRIVATE).getBoolean(key, def)

    private fun dpToPx(dp: Int): Int =
        (dp * resources.displayMetrics.density).toInt()

    private fun getScreenW(): Int = resources.displayMetrics.widthPixels
    private fun getScreenH(): Int = resources.displayMetrics.heightPixels
}
