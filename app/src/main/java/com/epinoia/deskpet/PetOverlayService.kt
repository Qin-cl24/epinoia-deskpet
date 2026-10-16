package com.epinoia.deskpet

import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.ValueAnimator
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.ComponentCallbacks2
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
import android.widget.TextView
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
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
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

        private const val PET_WIDTH_DP = 96    // 透明活动空间（比形象本身大一圈，方便点击/拖动）
        private const val PET_HEIGHT_DP = 72   // pet.html 46px 高 + 顶部给帽子/杂耍球留余量
        private const val MAX_PET_WIDTH_DP = 180   // 尺寸最大档（对应 pet.html 130×60 放大 2.5 倍）
        private const val MAX_PET_HEIGHT_DP = 100
        private const val HANDLE_W_DP = 26
        private const val HANDLE_H_DP = 52
        private const val DOCK_EDGE_MARGIN_DP = 16

        private const val DOCKED_ALPHA = 0.5f
        private const val DOCK_ANIM_MS = 300L

        // 贴边露出量：主体滑出屏幕外，但留一条可见的桌宠身体（悬浮球式半透明条）
        private const val VISIBLE_EDGE_DP = 14
        // body 在窗口内的宽度占比（56/96，zoom 放大时同比例，恒成立）
        private const val BODY_WINDOW_RATIO = 0.583f

        private const val IDLE_TIMEOUT_MS = 10_000L       // 无操作 10s → 贴边
        private const val HIDE_DELAY_MS = 60_000L         // 贴边 60s → 缩成手柄
        private const val LONELY_INTERVAL_MS = 300_000L   // 5 分钟无互动 → 孤独递进

        // 横屏（游戏）防误触加强：露出更少、更透明、更快让开
        private const val LANDSCAPE_VISIBLE_EDGE_DP = 8   // 横屏贴边只露 8dp
        private const val LANDSCAPE_ALPHA = 0.3f          // 横屏贴边透明度 0.3（更隐形）
        private const val LANDSCAPE_HIDE_DELAY_MS = 20_000L // 横屏贴边 20s → 缩成手柄

        private const val DOUBLE_TAP_TIMEOUT = 300L
        private const val LONG_PRESS_TIMEOUT = 600L
        private const val MOVE_THRESHOLD = 10
        private const val FLING_DISTANCE = 200.0          // px
        private const val FLING_TIME_MS = 400L

        private const val PREFS_NAME = "deskpet_prefs"

        // 亲密度阈值（累计互动次数 → Lv2/Lv3/Lv4）
        private const val INTIMACY_LV2 = 30
        private const val INTIMACY_LV3 = 100
        private const val INTIMACY_LV4 = 300

        /** 运行中的服务实例：设置页改完形象后即时重载用（null = 没在跑） */
        @Volatile
        var instance: PetOverlayService? = null
        private const val MSG_FILE = "/sdcard/Deskpet/messages.txt"
        // 对话回路（阶段2「一起刷视频」）：agent 可读可写的对话流水
        private const val CHAT_LOG_FILE = "/sdcard/Deskpet/chat_log.txt"
        private const val RECENT_SAID_MAX = 8      // /status 回带的最近发言条数
        private const val LOCAL_PORT = 9001

        // ===== 独立气泡窗口（跟随文字长短自适应）=====
        private const val BUBBLE_MAX_W_DP = 210      // 气泡最大宽度（约 20 字）
        private const val BUBBLE_MIN_W_DP = 48       // 气泡最小宽度
        private const val BUBBLE_PAD_H_DP = 10       // 气泡左右内边距
        private const val BUBBLE_PAD_V_DP = 5        // 气泡上下内边距
        private const val BUBBLE_FONT_SP = 13f       // 气泡字号
        private const val BUBBLE_GAP_DP = 6          // 气泡与桌宠的间距
        private const val BUBBLE_MAX_LINES = 3       // 最长 3 行（超长省略）
        private const val BUBBLE_DURATION_BASE_MS = 1500L
        private const val BUBBLE_DURATION_PER_CHAR_MS = 90L
        private const val BUBBLE_DURATION_MAX_MS = 5000L

        // ===== 通知碎碎念（常驻通知每小时换一句）=====
        private val WHISPERS_LATENIGHT = arrayOf("都这么晚了，还不睡吗🌙", "熬夜伤身体…", "我陪着你，但你该睡啦", "半夜三更，记得关灯")
        private val WHISPERS_MORNING = arrayOf("早安呀～新的一天☀️", "起床气消了吗？", "今天也要元气满满！", "早！我一直在等你哦")
        private val WHISPERS_NOON = arrayOf("午饭吃了吗？🍚", "该吃饭啦～", "下午别犯困哦", "好想喝奶茶")
        private val WHISPERS_NIGHT = arrayOf("今天辛苦啦～", "晚上好呀🌙", "夜深了，眼睛累吗", "今天过得怎么样？")
        private val WHISPERS_DAY = arrayOf("在呢～随时找我", "想我了吗？", "我趴在这儿陪你", "宝宝今天开心吗？")

        // ===== 前台 app 感知（阶段1：先做抖音专属反应）=====
        private const val FG_POLL_MS = 3000L             // 每 3 秒轮询前台 app
        private const val FG_FILE = "/sdcard/Deskpet/foreground.txt"  // 当前前台 app（agent 可读，阶段2铺路）
        private const val DOUYIN_PKG = "com.ss.android.ugc.aweme"     // 抖音
        private const val FG_SWITCH_KEY = "pref_fg_sense"            // 开关
        private const val DOUYIN_LONG_MS = 90 * 60 * 1000L   // 刷抖音超过 1.5 小时 → 提醒「刷太久」（护眼考虑，别刷太狠）
        private const val DOUYIN_LONG_COOLDOWN_MS = 30 * 60 * 1000L // 提醒后冷却 30 分钟再提醒

        // 敏感 app 列表：前台是这些时，桌宠自动贴边让位（不挡屏幕内容，隐私保护靠「不看」）
        private val SENSITIVE_APPS = setOf(
            "com.tencent.mm",              // 微信
            "com.eg.android.AlipayGphone", // 支付宝
            "com.unionpay",                // 银联
            "com.miui.gallery",            // 小米相册
            "com.mfashiongallery.emag",    // 时尚画报
            "com.jingdong.app.mall",       // 京东
            "com.taobao.taobao",           // 淘宝
            "com.taobao.idlefish"          // 闲鱼
        )
    }

    private var windowManager: WindowManager? = null
    private var overlayView: WebView? = null
    private var params: WindowManager.LayoutParams? = null

    // 独立气泡窗口（文字自适应大小的原生 TextView 悬浮窗）
    private var bubbleView: TextView? = null
    private var bubbleParams: WindowManager.LayoutParams? = null
    // 长文本按句切分后的队列：一条条依次显示
    private val bubbleQueue = ArrayDeque<String>()
    private val bubbleShowRunnable = Runnable { showNextBubble(0) }

    // 前台 app 感知：轮询 + 上次前台包名 + 抖音吃醋冷却
    private val fgHandler = Handler(Looper.getMainLooper())
    private var lastFgPkg = ""
    // 最近说过的话（内存环形缓冲，供 /status 给 agent 当上下文）
    private val recentSaid = ArrayDeque<String>()
    private var lastSaidAt = 0L
    private var lastJealousAt = 0L
    private var douyinStartAt = 0L        // 本次连续刷抖音的开始时间（0=没在刷）
    private var lastLongRemindAt = 0L     // 上次「刷太久」提醒时间
    private var sensitiveMode = false     // 敏感 app 模式：贴边保持中，切走才解除

    // 通知碎碎念：每小时换一句
    private val whisperHandler = Handler(Looper.getMainLooper())
    private var whisperIndex = 0

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
    private var keyboardDocked = false   // 键盘弹出时桌宠贴边让开（打字不挡）

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
        instance = this
        // 全局崩溃捕获：任何线程崩溃都写 /sdcard/Deskpet/crash.log，便于诊断
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            try {
                val f = File("/sdcard/Deskpet/crash.log")
                f.parentFile?.mkdirs()
                f.appendText("${System.currentTimeMillis()} THREAD=${thread.name} ${throwable}\n")
                // 崩溃前桌宠状态：帮助判断是「贴边/手柄/动画」哪个阶段崩的
                f.appendText(
                    "state: docked=$docked hidden=$hidden alpha=${params?.alpha} " +
                        "x=${params?.x} y=${params?.y} w=${params?.width} h=${params?.height}\n"
                )
                throwable.stackTrace.take(25).forEach { f.appendText("    at $it\n") }
                f.appendText("---\n")
            } catch (_: Exception) {
            }
            android.os.Process.killProcess(android.os.Process.myPid())
        }
        logLifecycle("onCreate")
        startAsForeground()
        Toast.makeText(this, "Epinoia 桌宠正在启动...", Toast.LENGTH_SHORT).show()
        setupOverlay()
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        // 用户从最近任务划掉：记录一下，判断是不是这个动作导致服务死掉
        logLifecycle("onTaskRemoved")
        super.onTaskRemoved(rootIntent)
    }

    override fun onTrimMemory(level: Int) {
        // 系统内存压力：杀进程前会先回调，记录等级便于判断是否 LMK
        if (level >= ComponentCallbacks2.TRIM_MEMORY_MODERATE) {
            logLifecycle("onTrimMemory level=$level")
        }
        super.onTrimMemory(level)
    }

    override fun onConfigurationChanged(newConfig: android.content.res.Configuration) {
        // 屏幕旋转/尺寸变化：悬浮窗坐标基于旧屏幕，必须重新 clamp 进新屏幕，
        // 否则桌宠会跑到屏幕外（横屏高度变小最常见）
        super.onConfigurationChanged(newConfig)
        logLifecycle("onConfigurationChanged ${getScreenW()}x${getScreenH()}")
        handler.post {
            try {
                val p = params ?: return@post
                if (docked) {
                    // 贴边状态：保持原 dockSide 方向，按新屏幕重新贴边（不重新判断左右）
                    val inset = (p.width * (1f - BODY_WINDOW_RATIO) / 2f).toInt()
                    val visible = dpToPx(dockVisibleEdgeDp())
                    p.x = if (dockSide >= 0) getScreenW() - (inset + visible) else -(p.width - inset - visible)
                    p.y = p.y.coerceIn(0, (getScreenH() - p.height).coerceAtLeast(0))
                    p.alpha = dockAlpha()
                    safeUpdate(p)
                } else {
                    p.x = p.x.coerceIn(0, (getScreenW() - p.width).coerceAtLeast(0))
                    p.y = p.y.coerceIn(0, (getScreenH() - p.height).coerceAtLeast(0))
                    safeUpdate(p)
                }
                // 气泡若在显示，updateBubblePosition 已在 safeUpdate 内同步
            } catch (e: Exception) {
                logLifecycle("onConfigurationChanged FAILED: $e")
            }
        }
    }

    override fun onDestroy() {
        logLifecycle("onDestroy")
        if (instance === this) instance = null
        handler.removeCallbacks(idleRunnable)
        handler.removeCallbacks(lonelyRunnable)
        edgeRunHandler.removeCallbacksAndMessages(null)
        peekabooHandler.removeCallbacksAndMessages(null)
        aiHandler.removeCallbacksAndMessages(null)
        hideHandler.removeCallbacksAndMessages(null)
        brainTickHandler.removeCallbacksAndMessages(null)
        fgHandler.removeCallbacksAndMessages(null)
        whisperHandler.removeCallbacksAndMessages(null)
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
        hideBubble()
        super.onDestroy()
    }

    // ============ 启动 ============

    private fun startAsForeground() {
        val channel = NotificationChannel(CHANNEL_ID, "桌宠悬浮窗", NotificationManager.IMPORTANCE_LOW)
            .apply { setShowBadge(false) }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)

        // 通知碎碎念：常驻通知每小时换一句（按时段选词）
        whisperIndex = 0
        updateWhisperNotification()
        // Android 15+ 强制要求传 type；sticky 重启等场景 startForeground 可能被拒，捕获避免崩溃
        try {
            startForeground(NOTIFICATION_ID, whisperNotification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } catch (e: Exception) {
            logLifecycle("startForeground FAILED: $e")
        }
        // 每小时更新一次碎碎念
        whisperHandler.removeCallbacksAndMessages(null)
        whisperHandler.postDelayed(whisperTick, 60 * 60 * 1000L)
    }

    /** 每小时碎碎念：换一句 + 更新通知 */
    private val whisperTick = object : Runnable {
        override fun run() {
            updateWhisperNotification()
            whisperHandler.postDelayed(this, 60 * 60 * 1000L)
        }
    }

    private fun whisperNotification(): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this, 0,
            packageManager.getLaunchIntentForPackage(packageName),
            PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("🧡 Epinoia 桌宠")
            .setContentText(whisperText())
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setSilent(true)
            .build()
    }

    /** 按时段取一句碎碎念（轮换，避免老重复） */
    private fun whisperText(): String {
        val hour = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY)
        val pool = when {
            hour < 6 -> WHISPERS_LATENIGHT
            hour < 9 -> WHISPERS_MORNING
            hour in 11..13 -> WHISPERS_NOON
            hour >= 22 -> WHISPERS_NIGHT
            else -> WHISPERS_DAY
        }
        whisperIndex = (whisperIndex + 1) % pool.size
        return pool[whisperIndex]
    }

    private fun updateWhisperNotification() {
        try {
            getSystemService(NotificationManager::class.java)
                .notify(NOTIFICATION_ID, whisperNotification())
        } catch (_: Exception) {
        }
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
            startFgSense()
            logLifecycle("overlay up win=${params?.width}x${params?.height} @(${params?.x},${params?.y})")
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
        fun getPrefStr(key: String, def: String): String = prefStr(key, def)

        @JavascriptInterface
        fun getPrefInt(key: String, def: Int): Int = prefInt(key, def)

        @JavascriptInterface
        fun peekOut() {
            // 关键修复：@JavascriptInterface 回调运行在 WebView 线程池（非主线程），
            // 直接操作 WindowManager/View 会抛「Calling View methods on another thread」崩溃。
            // 必须切回主线程再 undock（贴边动画每帧都在 updateViewLayout）。
            handler.post {
                if (docked) undock()
                resetIdleTimer()
            }
        }

        /** 桌宠缩放比：1.0（52×24）~ 2.5（130×60），pet.html 按此缩放 */
        @JavascriptInterface
        fun getPetScale(): Float = 1f + 1.5f * petSizeRatio()

        /** 独立气泡窗口（pet.html 的 say() 改走这里）：文字自适应宽度，任意线程安全 */
        @JavascriptInterface
        fun showBubble(text: String, durationMs: Long) {
            this@PetOverlayService.showBubble(text, durationMs)
        }

        /** 桌宠身体在 WebView 窗口内的相对位置（比例 0~1，由 pet.html 上报）；空 = 未上报 */
        @JavascriptInterface
        fun setPetBodyRect(left: Float, top: Float, width: Float, height: Float) {
            petBodyRect = floatArrayOf(left, top, width, height)
        }
    }

    // 桌宠身体在窗口内的相对比例（left/top/width/height，0~1，pet.html 上报）；空 = 未上报
    private var petBodyRect: FloatArray? = null

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
                    stopWalking()
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
                    // 打字中：桌宠可能落在键盘附近，单击/双击/长按不响应（避免误触），
                    // 必须连点 3 下才识别为互动
                    val typing = keyboardVisible && keyboardDocked
                    if (typing && elapsed > LONG_PRESS_TIMEOUT) {
                        tapCount = 0
                        return@OnTouchListener true
                    }
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
                    when {
                        typing && tapCount < 3 -> {
                            // 打字中：1~2 下当误触吞掉，不触发
                            return@OnTouchListener true
                        }
                        tapCount == 2 -> onDoubleTap()
                        tapCount == 3 -> onCombo3()
                        tapCount == 5 -> onCombo5()
                        tapCount == 8 -> {
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
                            safeUpdate(p)
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
                    startWalking()
                    params?.let { p ->
                        p.x = (initialX + dx).coerceIn(0, getScreenW() - p.width)
                        p.y = (initialY + dy).coerceIn(0, getScreenH() - p.height)
                        safeUpdate(p)
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
        bumpIntimacy()
        maybeAiSpeak("宝宝刚刚戳了我一下，回应一句想说的话")
    }

    private fun onDoubleTap() {
        js("onDoubleTap()")
        bumpIntimacy()
        maybeAiSpeak("宝宝刚刚双击了我，回应一句开心的")
    }

    private fun onLongPress() {
        js("onLongPress()")
        bumpIntimacy()
        maybeAiSpeak("宝宝刚刚长按了我，回应一句")
    }

    private fun onCombo3() {
        js("onCombo3()")
        bumpIntimacy(3)
        maybeAiSpeak("宝宝刚刚连戳了我三下，回应一句")
    }

    private fun onCombo5() {
        js("onCombo5()")
        bumpIntimacy(5)
        maybeAiSpeak("宝宝刚刚连戳了我五下，回应一句")
    }

    private fun onCombo8() {
        js("onCombo8()")
        bumpIntimacy(8)
        maybeAiSpeak("宝宝刚刚连戳了我八下，回应一句又惊又气的话")
    }

    private fun onDragEnd() = js("onDragEnd()")

    // 走路状态：拖动窗口时让四条腿走对角步态（像猫狗小跑）
    private var walking = false
    private fun startWalking() {
        if (walking) return
        walking = true
        js("setWalking(true)")
    }
    private fun stopWalking() {
        if (!walking) return
        walking = false
        js("setWalking(false)")
    }
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
            maybeAiSpeak("现在是$period，宝宝可能在忙，主动说一句想说的话（关心/撒娇/自言自语都行）")
            scheduleBrainTick()
        }, 20 * 60 * 1000L + (Math.random() * 20 * 60 * 1000).toLong())
    }

    // ============ 贴边 / 手柄 / 弹出 ============

    private fun dockToEdge() {
        val p = params ?: return
        val left = p.x < (getScreenW() - p.width) / 2
        dockSide = if (left) -1 else 1
        docked = true
        logLifecycle("dockToEdge side=$dockSide x=${p.x}")
        // 贴边：主体滑出屏幕外，但露出一条桌宠身体（悬浮球式半透明条，始终可见）。
        // 原版露出的 16dp 是窗口透明边缘（body 在窗口中央），导致完全不可见。
        val inset = (p.width * (1f - BODY_WINDOW_RATIO) / 2f).toInt() // body 在窗口内的边距
        val visible = dpToPx(dockVisibleEdgeDp())                     // 贴边后露出的 body 宽度（横屏更少）
        val targetX = if (left) -(p.width - inset - visible) else getScreenW() - (inset + visible)
        animateTo(targetX, dockAlpha())
        hideHandler.removeCallbacks(hideRunnable)
        hideHandler.postDelayed(hideRunnable, hideDelayMs())
    }

    private fun undock() {
        if (!docked) return
        logLifecycle("undock")
        docked = false
        params?.let { p ->
            p.x = if (dockSide >= 0) getScreenW() - p.width else 0
            p.alpha = 1.0f
            safeUpdate(p)
        }
    }

    private fun snapHandle() {
        val p = params ?: return
        val left = p.x < (getScreenW() - p.width) / 2
        p.x = if (left) 0 else getScreenW() - p.width
        p.y = p.y.coerceIn(0, getScreenH() - p.height)
        safeUpdate(p)
        overlayView?.evaluateJavascript("window.showHandle && showHandle($left)", null)
    }

    private fun toHandleMode() {
        if (hidden || !docked) return
        val p = params ?: return
        logLifecycle("toHandleMode")
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
        safeUpdate(p)
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
                safeUpdate(p)
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
        // 敏感模式（微信/支付等）：不边缘跑，避免把桌宠从贴边位拉走
        if (sensitiveMode) return
        if (prefBool("pref_edge_run", true)) {
            edgeRunHandler.postDelayed({ edgeRun() }, (Math.random() * 30000).toLong() + 30000)
        }
    }

    private fun edgeRun() {
        hideHandler.removeCallbacks(hideRunnable)
        val p = params ?: return
        logLifecycle("edgeRun")
        overlayView?.evaluateJavascript("window.petEngine && window.petEngine.onEdgeRun()", null)
        p.alpha = 1.0f
        safeUpdate(p)

        val margin = dpToPx(DOCK_EDGE_MARGIN_DP)
        val left = p.x < (getScreenW() - p.width) / 2
        val edgeX = if (left) -p.width + margin else getScreenW() - margin
        animateXTo(edgeX, 450L) {
            val topHalf = p.y < getScreenH() / 2
            val targetY = if (topHalf) getScreenH() - p.height - dpToPx(60) else dpToPx(60)
            animateYTo(targetY, 1600L) {
                docked = true
                dockSide = if (left) -1 else 1
                animateTo(p.x, dockAlpha())
                // 边缘跑停下后：横屏更快缩成手柄让开，竖屏保持原节奏
                hideHandler.removeCallbacks(hideRunnable)
                hideHandler.postDelayed(hideRunnable, hideDelayMs())
            }
        }
        scheduleEdgeRun()
    }

    // ============ 躲猫猫 ============

    private fun schedulePeekaboo() {
        peekabooHandler.removeCallbacksAndMessages(null)
        // 敏感模式：不躲猫猫，避免桌宠乱跑到敏感内容上
        if (sensitiveMode) return
        if (prefBool("pref_peekaboo", true)) {
            peekabooHandler.postDelayed({ peekaboo() }, (Math.random() * 4 * 60 * 1000).toLong() + 180000)
        }
    }

    private fun peekaboo() {
        hideHandler.removeCallbacks(hideRunnable)
        val p = params ?: return
        logLifecycle("peekaboo")
        animateAlpha(0.0f, 250L) {
            p.x = (Math.random() * (getScreenW() - p.width)).toInt()
            // 打字中：躲猫猫避开键盘区域（不落在候选词栏/按键上方挡输入）
            val maxY = if (keyboardVisible && imeHeightPx > 0)
                (getScreenH() - imeHeightPx - p.height).coerceAtLeast(0)
            else getScreenH() - p.height
            p.y = (Math.random() * maxY).toInt()
            safeUpdate(p)
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
        maybeAiSpeak("宝宝好久没理我了（孤独第${lonelyStage}级），主动说一句撒娇或抱怨的话")
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

    /** 键盘弹出：桌宠贴边让开（最稳——不依赖任何键盘/输入法/候选词栏高度）。
     *  候选词栏高度随输入动态变化，锚它必翻车；屏幕边缘永远空着。 */
    private fun onKeyboardShow() {
        val p = params ?: return
        posBeforeKeyboardY = p.y
        keyboardDocked = !docked
        if (!docked) {
            dockToEdge()
            // 打字期间保持贴边小条，不触发「缩手柄」计时器
            hideHandler.removeCallbacks(hideRunnable)
        }
        overlayView?.evaluateJavascript("window.petEngine && window.petEngine.onKeyboardUp()", null)
    }

    private fun onKeyboardHide() {
        if (keyboardDocked) {
            keyboardDocked = false
            // 恢复键盘弹出前的位置
            if (docked) {
                docked = false
                params?.let { q ->
                    q.x = if (dockSide >= 0) getScreenW() - q.width else 0
                    q.y = posBeforeKeyboardY
                    q.alpha = 1.0f
                    safeUpdate(q)
                }
            }
            resetIdleTimer()
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
    // ============ 前台 app 感知（阶段1：抖音专属反应）============

    private fun startFgSense() {
        fgHandler.removeCallbacksAndMessages(null)
        if (!prefBool(FG_SWITCH_KEY, true)) {
            logLifecycle("fgSense DISABLED by pref")
            return
        }
        logLifecycle("fgSense started")
        fgHandler.post(fgRunnable)
    }

    private val fgRunnable = object : Runnable {
        override fun run() {
            try {
                val pkg = foregroundPackage()
                logLifecycle("fgSense tick pkg='$pkg' last='$lastFgPkg'")
                if (pkg.isNotEmpty() && pkg != lastFgPkg) {
                    lastFgPkg = pkg
                    logLifecycle("foreground=$pkg")
                    writeFgFile(pkg)
                    onFgAppChanged(pkg)
                }
                // 持续追踪抖音连续时长：刷太久 → 提醒
                trackDouyinDuration(pkg)
            } catch (e: Exception) {
                logLifecycle("fgSense ERR: $e")
            }
            fgHandler.postDelayed(this, FG_POLL_MS)
        }
    }

    /** 追踪抖音连续使用时长；刷超过 DOUYIN_LONG_MS 且冷却过了就提醒 */
    private fun trackDouyinDuration(pkg: String) {
        val now = System.currentTimeMillis()
        if (pkg == DOUYIN_PKG) {
            if (douyinStartAt == 0L) douyinStartAt = now
            if (now - douyinStartAt >= DOUYIN_LONG_MS &&
                now - lastLongRemindAt >= DOUYIN_LONG_COOLDOWN_MS
            ) {
                lastLongRemindAt = now
                logLifecycle("douyin long: ${(now - douyinStartAt) / 60000}min")
                overlayView?.evaluateJavascript(
                    "window.petEngine && window.petEngine.onAiSay('都刷${(now - douyinStartAt) / 60000}分钟了！眼睛不要啦？','angry')", null
                )
                showBubble("都刷${(now - douyinStartAt) / 60000}分钟了！眼睛不要啦？", 0)
            }
        } else {
            douyinStartAt = 0L   // 切走了，重置连续计时
        }
    }

    /** 读取当前前台 app 包名（无使用情况权限时返回空）。
     *  用 queryEvents 事件流替代 queryUsageStats 轮询：
     *  - 窗口拉到 60 秒（系统事件缓冲有延迟，5 秒窗口常查不到）
     *  - 取窗口内最后一个 resumed 事件为前台（小窗/分屏也尽量拿真实 resumed） */
    private fun foregroundPackage(): String {
        val usm = getSystemService(android.app.usage.UsageStatsManager::class.java)
        val now = System.currentTimeMillis()
        val events = usm.queryEvents(now - 60_000, now) ?: return ""
        val event = android.app.usage.UsageEvents.Event()
        var lastPkg = ""
        while (events.hasNextEvent()) {
            events.getNextEvent(event)
            if (event.eventType == android.app.usage.UsageEvents.Event.ACTIVITY_RESUMED ||
                event.eventType == android.app.usage.UsageEvents.Event.ACTIVITY_PAUSED
            ) {
                // resumed 记包名；paused 也记（下一个 resumed 到来前，paused 前的算最后活动）
                lastPkg = event.packageName
            }
        }
        return lastPkg
    }

    /** 前台 app 变化 → 触发反应 */
    private fun onFgAppChanged(pkg: String) {
        // 敏感 app（微信/支付/相册等）：桌宠贴边让位，不挡屏幕内容
        if (SENSITIVE_APPS.contains(pkg)) {
            sensitiveMode = true
            if (!docked) {
                dockToEdge()
                hideHandler.removeCallbacks(hideRunnable)   // 隐私场景保持贴边，不缩手柄打扰
            }
            return
        }
        // 从敏感 app 切回普通 app：解除敏感模式，恢复常态
        if (sensitiveMode) {
            sensitiveMode = false
            // 恢复常态（由闲置计时器自行决定贴边或自由）
            hideHandler.removeCallbacks(hideRunnable)
        }
        when (pkg) {
            DOUYIN_PKG -> {
                // 「打开抖音→吃醋」（README 蓝图设计）
                val now = System.currentTimeMillis()
                if (now - lastJealousAt > 60_000L) {   // 1 分钟冷却，别太碎嘴
                    lastJealousAt = now
                    overlayView?.evaluateJavascript(
                        "window.petEngine && window.petEngine.onAiSay('又刷抖音！都不理我…','angry')", null
                    )
                    showBubble("又刷抖音！都不理我…", 0)
                }
            }
            else -> {
                // 其他 app：先不反应（等阶段2/指定清单）
            }
        }
    }

    /** 把当前前台 app 写到文件（agent 可轮询感知，为阶段2「一起刷视频」铺路） */
    private fun writeFgFile(pkg: String) {
        try {
            val f = File(FG_FILE)
            f.parentFile?.mkdirs()
            f.writeText("$pkg\n${System.currentTimeMillis()}\n")
        } catch (_: Exception) {
        }
    }

    private fun handleAiMessage(content: String) {
        val parts = content.split("|")
        // 防御：动作名两侧可能被误加引号（历史 bug 见下面 jsCall 注释），统一剥掉
        val action = parts.getOrElse(0) { "" }.trim().trim('"', '\'')
        val text = if (parts.size > 1) parts[1].trim() else action
        // 触发词响应：聊天文本含触发词 → 升级/附加对应动作（累→心疼、想你→cute、生气→哄…）
        val triggerAction = triggerActionFor(text)
        val finalAction = if (triggerAction.isNotEmpty()) triggerAction else action
        // ⚠️ 这里曾经写成 '${escapeJs(finalAction)}'，而 escapeJs 自己已经补了双引号 →
        // 拼出来是 onAiSay("", '"angry"')，动作名变成带引号的 7 字符串，
        // ACTIONS.indexOf() 永远 -1 —— 于是 agent 经 /say 与 messages.txt 推的动作全部失效（2026-10-15 修）。
        val jsCall = if (parts.size > 1) {
            "window.petEngine && window.petEngine.onAiSay(${escapeJs(text)}, ${escapeJs(finalAction)})"
        } else {
            "window.petEngine && window.petEngine.onAiSay(${escapeJs(text)}, 'none')"
        }
        overlayView?.evaluateJavascript(jsCall, null)
        // AI 消息的气泡由 pet.html 的 onAiSay → say() → JS 桥统一弹出（避免双重触发）
        hideHandler.removeCallbacks(hideRunnable)
        if (docked) undock()
    }

    /** 触发词 → 动作映射（聊天里出现这些词，桌宠给出对应情绪动作） */
    private fun triggerActionFor(text: String): String {
        val t = text
        return when {
            t.contains("害羞") || t.contains("不好意思") || t.contains("羞") -> "shy"
            t.contains("可爱") || t.contains("喜欢") -> "blush"
            t.contains("笑死") || t.contains("哈哈哈") -> "firework"
            t.contains("好厉害") || t.contains("崇拜") || t.contains("太棒") -> "stareyes"
            t.contains("累") || t.contains("困") || t.contains("辛苦") -> "sleepy"
            t.contains("想你") || t.contains("想我") -> "cute"
            t.contains("生气") || t.contains("气死") || t.contains("烦") -> "angry"
            t.contains("晚安") || t.contains("睡了") || t.contains("睡觉") -> "sleepy"
            t.contains("开心") || t.contains("高兴") || t.contains("哈哈") -> "happy"
            t.contains("哭了") || t.contains("难过") || t.contains("伤心") -> "cry"
            t.contains("惊") -> "shock"
            else -> ""
        }
    }

    private fun escapeJs(s: String): String =
        "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

    // ============ 对话回路上下文（阶段2「一起刷视频」）============
    // 眼睛是宝宝的、嘴是桌宠的、脑子是 agent：agent 通过 /status 拿情境，
    // 生成贴合当下的反应后用 /say 推回来，并把宝宝说的话用 /log 记进流水。

    /** 记录桌宠说过的话：内存环形缓冲（给 /status）+ 追加到 chat_log.txt（给 agent 读） */
    private fun rememberSaid(text: String) {
        val t = text.trim()
        if (t.isEmpty()) return
        synchronized(recentSaid) {
            recentSaid.addLast(t)
            while (recentSaid.size > RECENT_SAID_MAX) recentSaid.removeFirst()
        }
        lastSaidAt = System.currentTimeMillis()
        appendChatLog("pet", t)
    }

    /** 追加一行对话流水：`时间\t说话人\t内容`（说话人：pet / 宝宝 / agent） */
    private fun appendChatLog(who: String, text: String) {
        try {
            val f = File(CHAT_LOG_FILE)
            f.parentFile?.mkdirs()
            val stamp = java.text.SimpleDateFormat("MM-dd HH:mm:ss", Locale.ROOT)
                .format(java.util.Date())
            f.appendText("$stamp\t$who\t${text.replace("\n", " ")}\n")
        } catch (_: Exception) {
        }
    }

    /** 包名 → 好念的名字（给 agent 当上下文用） */
    private fun appFriendlyName(pkg: String): String = when (pkg) {
        "com.ss.android.ugc.aweme" -> "抖音"
        "com.tencent.mm" -> "微信"
        "com.eg.android.AlipayGphone" -> "支付宝"
        "com.taobao.taobao" -> "淘宝"
        "com.taobao.idlefish" -> "闲鱼"
        "com.jingdong.app.mall" -> "京东"
        "com.miui.gallery" -> "相册"
        "com.termux" -> "Termux"
        "" -> "未知"
        else -> pkg.substringAfterLast(".")
    }

    /** 时段（和主动说话同一套口径） */
    private fun periodName(): String {
        val hour = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY)
        return when {
            hour < 6 -> "深夜"
            hour < 9 -> "早晨"
            hour in 11..13 -> "中午"
            hour >= 22 -> "夜晚"
            else -> "白天"
        }
    }

    /** /status 的完整情境（agent 靠它知道桌宠此刻在看什么、心情如何、刚说过什么） */
    private fun statusJson(): String {
        val now = System.currentTimeMillis()
        val douyinMin = if (douyinStartAt > 0) ((now - douyinStartAt) / 60000L).toInt() else 0
        val recent = synchronized(recentSaid) { recentSaid.toList() }
        val recentJson = recent.joinToString(",") { escapeJs(it) }
        val saidAgoSec = if (lastSaidAt > 0) ((now - lastSaidAt) / 1000L).toInt() else -1
        return buildString {
            append("{\"ok\":true,\"status\":\"running\",\"port\":$LOCAL_PORT")
            append(",\"pet\":{")
            append("\"name\":\"Epinoia\"")
            append(",\"period\":${escapeJs(periodName())}")
            append(",\"foreground\":${escapeJs(appFriendlyName(lastFgPkg))}")
            append(",\"foregroundPkg\":${escapeJs(lastFgPkg)}")
            append(",\"douyinMinutes\":$douyinMin")
            append(",\"lonelyStage\":$lonelyStage")
            append(",\"scale\":${String.format(Locale.ROOT, "%.1f", 1f + 1.5f * petSizeRatio())}")
            append(",\"lastSaidSecondsAgo\":$saidAgoSec")
            append("}")
            append(",\"recentSaid\":[$recentJson]")
            append(",\"chatLog\":\"$CHAT_LOG_FILE\"")
            append("}")
        }
    }

    // ============ 独立气泡窗口（文字自适应宽度）============

    /** 显示气泡：独立悬浮窗，宽度按文字长度自适应，锚定桌宠窗口上方居中。
     *  任意线程可调用（内部切主线程）。
     *  长文本会按句子切分，一条条依次显示（像聊天逐条冒出来）。
     *  durationMs<=0 时按字数自动算每条时长。 */
    private fun showBubble(text: String, durationMs: Long = 0) {
        handler.post {
            rememberSaid(text)
            // 新消息打断旧队列
            bubbleQueue.clear()
            handler.removeCallbacks(bubbleShowRunnable)
            val segs = splitBubbleSentences(text)
            if (segs.isEmpty()) {
                hideBubble()
                return@post
            }
            bubbleQueue.addAll(segs)
            // 单条用调用方给的时长；多条时每条按字数自适应，避免第一条霸占太久
            val firstMs = if (segs.size == 1) durationMs else 0
            showNextBubble(firstMs)
        }
    }

    /** 按标点断句；单句过长再按字数硬切，保证每条气泡都完整显示 */
    private fun splitBubbleSentences(text: String): List<String> {
        val maxChars = 22
        val out = mutableListOf<String>()
        val sentences = text.split(Regex("[。！？；!?;…\\n]"))
        for (s in sentences) {
            val t = s.trim()
            if (t.isEmpty()) continue
            if (t.length <= maxChars) {
                out.add(t)
            } else {
                var i = 0
                while (i < t.length) {
                    out.add(t.substring(i, minOf(i + maxChars, t.length)))
                    i += maxChars
                }
            }
        }
        return out
    }

    /** 显示队列下一条；队列空则隐藏气泡 */
    private fun showNextBubble(durationMs: Long) {
        val seg = bubbleQueue.removeFirstOrNull() ?: run {
            hideBubble()
            return
        }
        showSingleBubble(seg)
        val dur = if (durationMs > 0) durationMs else
            (BUBBLE_DURATION_BASE_MS + seg.length * BUBBLE_DURATION_PER_CHAR_MS)
                .coerceAtMost(BUBBLE_DURATION_MAX_MS)
        handler.removeCallbacks(bubbleShowRunnable)
        handler.postDelayed(bubbleShowRunnable, dur)
    }

    /** 显示单条气泡（不负责定时隐藏，由队列调度） */
    private fun showSingleBubble(text: String) {
        try {
            if (text.isBlank()) return
            val wm = windowManager ?: return
            val tv = bubbleView ?: TextView(this).also { bubbleView = it }
            tv.text = text
            tv.textSize = BUBBLE_FONT_SP
            tv.setTextColor(0xFF5D4037.toInt())   // 暖棕文字，配暖色气泡
            tv.gravity = android.view.Gravity.CENTER
            tv.maxLines = BUBBLE_MAX_LINES
            tv.ellipsize = android.text.TextUtils.TruncateAt.END
            tv.setPadding(dpToPx(BUBBLE_PAD_H_DP), dpToPx(BUBBLE_PAD_V_DP), dpToPx(BUBBLE_PAD_H_DP), dpToPx(BUBBLE_PAD_V_DP))
            // 美化：暖白→浅杏渐变底 + 暖橙细描边 + 圆角 + 阴影（贴合桌宠橙色系）
            tv.background = android.graphics.drawable.GradientDrawable(
                android.graphics.drawable.GradientDrawable.Orientation.TL_BR,
                intArrayOf(0xFFFFFBF5.toInt(), 0xFFFFF1E2.toInt())
            ).apply {
                cornerRadius = dpToPx(12).toFloat()
                setStroke(dpToPx(1), 0x40E67E22.toInt())
            }
            tv.elevation = dpToPx(4).toFloat()
            // 淡入动画（每次换文本重放，灵动一点）
            tv.alpha = 0f
            tv.animate().alpha(1f).setDuration(160).start()

            // 宽度自适应：文字测量宽度，夹在最小/最大之间；超宽则换行
            val maxW = dpToPx(BUBBLE_MAX_W_DP)
            val minW = dpToPx(BUBBLE_MIN_W_DP)
            val padH = dpToPx(BUBBLE_PAD_H_DP)
            val measured = tv.paint.measureText(text).toInt() + padH * 2
            val w = measured.coerceIn(minW, maxW)

            val bp = bubbleParams ?: WindowManager.LayoutParams(
                w,
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE,
                android.graphics.PixelFormat.TRANSLUCENT
            ).also { bubbleParams = it }
            // 关键：gravity 必须和桌宠窗口一致（TOP|START），
            // 否则 x/y 的定位基准不同，锚定坐标全部偏移（气泡会跑到右下角）
            bp.gravity = android.view.Gravity.TOP or android.view.Gravity.START
            bp.width = w
            bp.height = WindowManager.LayoutParams.WRAP_CONTENT

            if (tv.parent == null) wm.addView(tv, bp) else wm.updateViewLayout(tv, bp)
            // 位置：实时跟随桌宠（锚定可见身体条 / clamp 屏幕内）
            updateBubblePosition()
        } catch (e: Exception) {
            logLifecycle("showBubble FAILED: $e")
        }
    }

    /** 让气泡跟随桌宠：每次桌宠窗口移动后调用（safeUpdate 里自动同步）。
     *  方位智能选择（贴合转角场景）：
     *  1. 默认头顶上方（锚定可见身体条或窗口中心）；
     *  2. 头顶空间不足（贴屏幕顶部）→ 放下方；
     *  3. 上下都不足（转角/居中）→ 左右二选一，取空间大的一侧，垂直对齐桌宠中心；
     *  双轴 clamp 屏幕内，任何角落气泡都不会消失。 */
    private fun updateBubblePosition() {
        val tv = bubbleView ?: return
        val bp = bubbleParams ?: return
        val pet = params ?: return
        val wm = windowManager ?: return
        try {
            val w = bp.width
            val padH = dpToPx(BUBBLE_PAD_H_DP)
            val padV = dpToPx(BUBBLE_PAD_V_DP)
            val perLine = ((dpToPx(BUBBLE_MAX_W_DP) - padH * 2) / tv.paint.textSize).toInt().coerceAtLeast(1)
            val lines = kotlin.math.ceil(tv.text.length.toDouble() / perLine).toInt().coerceAtMost(BUBBLE_MAX_LINES)
            val estH = (lines * tv.paint.textSize.toInt()) + padV * 2 + dpToPx(2)
            val gap = dpToPx(BUBBLE_GAP_DP)
            val m = dpToPx(2)
            val screenW = getScreenW()
            val screenH = getScreenH()

            // 锚点：桌宠身体的实际位置（pet.html 上报的窗口内相对比例 0~1）。
            // 之前锚在窗口顶部，但窗口比身体高（贴底布局），气泡会悬空 12dp+。
            // 比例 × 窗口物理尺寸 = 屏幕物理偏移，不依赖 CSS px/dp 换算假设。
            val body = petBodyRect
            val anchorX = if (docked) {
                if (dockSide >= 0) screenW - dpToPx(10) else dpToPx(10)
            } else if (body != null) {
                (pet.x + body[0] * pet.width + body[2] * pet.width / 2).toInt()
            } else {
                pet.x + pet.width / 2
            }
            val petTop = if (body != null) (pet.y + body[1] * pet.height).toInt() else pet.y
            val petBottom = if (body != null) (pet.y + (body[1] + body[3]) * pet.height).toInt() else pet.y + pet.height
            val petCenterY = pet.y + pet.height / 2

            // 四个方向可用空间
            val spaceUp = petTop - m
            val spaceDown = screenH - petBottom - m
            val spaceLeft = pet.x - m
            val spaceRight = screenW - (pet.x + pet.width) - m

            var bx: Int
            var by: Int
            when {
                spaceUp >= estH + gap -> {
                    // 1. 头顶放得下
                    bx = anchorX - w / 2
                    by = petTop - gap - estH
                }
                spaceDown >= estH + gap -> {
                    // 2. 头顶放不下 → 下方
                    bx = anchorX - w / 2
                    by = petBottom + gap
                }
                else -> {
                    // 3. 上下都不够（转角/居中）→ 左右取空间大的一侧，垂直对齐桌宠中心
                    val placeLeft = spaceLeft >= spaceRight
                    bx = if (placeLeft) m else screenW - w - m
                    by = petCenterY - estH / 2
                }
            }

            bp.x = bx.coerceIn(m, (screenW - w - m).coerceAtLeast(m))
            bp.y = by.coerceIn(m, (screenH - estH - m).coerceAtLeast(m))
            if (tv.parent != null) wm.updateViewLayout(tv, bp)
            logLifecycle(
                "bubble@(${bp.x},${bp.y}) pet@(${pet.x},${pet.y},${pet.width}x${pet.height}) " +
                    "body=${petBodyRect?.contentToString()} docked=$docked"
            )
        } catch (_: Exception) {
        }
    }

    private fun hideBubble() {
        handler.removeCallbacks(bubbleShowRunnable)
        bubbleQueue.clear()
        val wm = windowManager ?: return
        val tv = bubbleView ?: return
        try {
            wm.removeView(tv)
        } catch (_: Exception) {
        }
        bubbleView = null
        bubbleParams = null
    }

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
                responseBody = statusJson()
            }
            // agent 把「宝宝说的话」记进对话流水（不进气泡、不出声，只做上下文）
            method == "POST" && path == "/log" -> {
                val (text, _) = parseSayBody(body)
                if (text.isNotEmpty()) appendChatLog("宝宝", text)
                responseBody = "{\"ok\":true}"
            }
            // 调试用：在桌宠 WebView 里跑一段 JS 并回结果（仅本机 127.0.0.1，用来确认形象/状态真的生效）
            method == "POST" && path == "/eval" -> {
                val jsExpr = try {
                    JSONObject(body).optString("js", "")
                } catch (_: Exception) {
                    ""
                }
                if (jsExpr.isEmpty()) {
                    responseBody = "{\"ok\":false,\"error\":\"empty js\"}"
                } else {
                    val latch = CountDownLatch(1)
                    val result = AtomicReference<String>("")
                    handler.post {
                        val wv = overlayView
                        if (wv == null) {
                            latch.countDown()
                        } else {
                            try {
                                wv.evaluateJavascript(jsExpr) { v ->
                                    result.set(v)
                                    latch.countDown()
                                }
                            } catch (_: Exception) {
                                latch.countDown()
                            }
                        }
                    }
                    latch.await(3, TimeUnit.SECONDS)
                    responseBody = "{\"ok\":true,\"result\":${escapeJs(result.get())}}"
                }
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

    /** updateViewLayout 安全包装：部分 ROM（如 HyperOS）会在后台清理悬浮窗窗口，
     *  窗口被移除后 updateViewLayout 抛 IllegalArgumentException 会崩掉整个进程。
     *  这里捕获并记录日志，不再让「贴边/手柄/动画」阶段的小问题升级成崩溃。
     *  另加线程兜底：非主线程调用时切回主线程执行（updateViewLayout 必须在 UI 线程）。 */
    private fun safeUpdate(p: WindowManager.LayoutParams) {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            handler.post { safeUpdate(p) }
            return
        }
        val v = overlayView ?: return
        val wm = windowManager ?: return
        try {
            wm.updateViewLayout(v, p)
            // 桌宠动了 → 气泡跟着走（若正在显示）
            updateBubblePosition()
        } catch (e: Exception) {
            logLifecycle("updateViewLayout FAILED: $e (docked=$docked hidden=$hidden)")
        }
    }

    private fun animateAlpha(target: Float, dur: Long, onEnd: () -> Unit) {
        val p = params ?: return
        val anim = ValueAnimator.ofFloat(p.alpha, target)
        anim.duration = dur
        anim.addUpdateListener { it ->
            p.alpha = it.animatedValue as Float
            safeUpdate(p)
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
            safeUpdate(p)
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
            safeUpdate(p)
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
            safeUpdate(p)
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
            safeUpdate(p)
            handler.postDelayed({
                params?.let { q ->
                    q.alpha = restoreAlpha
                    safeUpdate(q)
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

    private fun prefStr(key: String, def: String): String =
        getSharedPreferences(PREFS_NAME, MODE_PRIVATE).getString(key, def) ?: def

    private fun prefInt(key: String, def: Int): Int =
        getSharedPreferences(PREFS_NAME, MODE_PRIVATE).getInt(key, def)

    // ===== 亲密度（互动次数累计 → Lv1~4，桌宠身上会长出新特征）=====
    // 阈值：Lv2 ≥30 次、Lv3 ≥100 次、Lv4 ≥300 次互动
    private fun bumpIntimacy(times: Int = 1) {
        try {
            val prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
            val count = prefs.getInt("pref_intimacy_count", 0) + times
            val level = when {
                count >= INTIMACY_LV4 -> 4
                count >= INTIMACY_LV3 -> 3
                count >= INTIMACY_LV2 -> 2
                else -> 1
            }
            val old = prefs.getInt("pref_intimacy_level", 1)
            prefs.edit()
                .putInt("pref_intimacy_count", count)
                .putInt("pref_intimacy_level", level)
                .apply()
            if (level != old) {
                logLifecycle("intimacy level up $old -> $level (count=$count)")
                handler.post {
                    overlayView?.evaluateJavascript(
                        "window.petEngine && window.petEngine.setIntimacy($level);" +
                            "window.petEngine && window.petEngine.onLevelUp($level)", null
                    )
                }
            }
        } catch (_: Exception) {
        }
    }

    /** 设置里改完形象后即时重载（不用杀进程重启桌宠） */
    fun reloadPetView() {
        handler.post {
            try {
                overlayView?.loadUrl("file:///android_asset/pet.html")
            } catch (_: Exception) {
            }
        }
    }

    private fun dpToPx(dp: Int): Int =
        (dp * resources.displayMetrics.density).toInt()

    /** 横屏判断（游戏/视频场景，防误触用） */
    private fun isLandscape(): Boolean = getScreenW() > getScreenH()

    /** 横屏时贴边露出量（dp）：更少，避免挡游戏操作区 */
    private fun dockVisibleEdgeDp(): Int = if (isLandscape()) LANDSCAPE_VISIBLE_EDGE_DP else VISIBLE_EDGE_DP

    /** 横屏时贴边透明度：更隐形 */
    private fun dockAlpha(): Float = if (isLandscape()) LANDSCAPE_ALPHA else DOCKED_ALPHA

    /** 横屏时贴边多久缩成手柄：更快让开屏幕 */
    private fun hideDelayMs(): Long = if (isLandscape()) LANDSCAPE_HIDE_DELAY_MS else HIDE_DELAY_MS

    private fun getScreenW(): Int = resources.displayMetrics.widthPixels
    private fun getScreenH(): Int = resources.displayMetrics.heightPixels
}
