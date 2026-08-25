package com.example.deskpet.service

import android.app.*
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.os.Handler
import android.os.Looper
import android.view.*
import android.webkit.WebView
import android.webkit.WebViewClient
import android.webkit.WebSettings
import androidx.core.app.NotificationCompat

/**
 * Minimal overlay service example.
 * This is a stripped-down skeleton — add your own logic.
 */
class OverlayService : Service() {

    private var windowManager: WindowManager? = null
    private var overlayView: WebView? = null
    private var params: WindowManager.LayoutParams? = null

    companion object {
        private const val CHANNEL_ID = "pet_overlay_channel"
        private const val NOTIFICATION_ID = 1001
        private const val PET_SIZE_DP = 180
        private const val PET_HEIGHT_DP = 240

        // === Gesture parameters (keep in sync with docs/gesture-system.md) ===
        private const val DOUBLE_TAP_TIMEOUT = 300L          // ms between the two taps
        private const val LONG_PRESS_TIMEOUT = 600L          // hold duration before long press fires
        private const val MOVE_THRESHOLD_PX = 10             // px before it counts as a drag
        private const val FLING_VELOCITY_THRESHOLD = 800f    // px/s, from VelocityTracker
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, buildNotification("..."))
        setupOverlay()
    }

    private fun setupOverlay() {
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager

        params = WindowManager.LayoutParams(
            dpToPx(PET_SIZE_DP),
            dpToPx(PET_HEIGHT_DP),
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
            WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 50
            y = 300
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
            // Load your pet's HTML from assets
            loadUrl("file:///android_asset/pet.html")
            setOnTouchListener(createTouchListener())
        }

        windowManager?.addView(overlayView, params)
    }

    // === GESTURE HANDLING ===

    private var initialX = 0
    private var initialY = 0
    private var initialTouchX = 0f
    private var initialTouchY = 0f
    private var lastTapTime = 0L
    private var touchStartTime = 0L
    private var hasMoved = false
    private var longPressTriggered = false
    private var velocityTracker: VelocityTracker? = null
    private val gestureHandler = Handler(Looper.getMainLooper())

    /** Fires while the finger is still down, so the pet reacts without waiting for release. */
    private val longPressRunnable = Runnable {
        longPressTriggered = true
        fireJs("onLongPress()")
    }

    /** Single tap is delayed by DOUBLE_TAP_TIMEOUT so a second tap can cancel it (double tap). */
    private val singleTapRunnable = Runnable { fireJs("onTap()") }

    private fun fireJs(call: String) {
        overlayView?.evaluateJavascript(
            "window.petEngine && window.petEngine.$call", null
        )
    }

    private fun createTouchListener(): View.OnTouchListener {
        return View.OnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    initialX = params?.x ?: 0
                    initialY = params?.y ?: 0
                    initialTouchX = event.rawX
                    initialTouchY = event.rawY
                    touchStartTime = System.currentTimeMillis()
                    hasMoved = false
                    longPressTriggered = false
                    velocityTracker?.recycle()
                    velocityTracker = VelocityTracker.obtain()
                    velocityTracker?.addMovement(event)
                    gestureHandler.removeCallbacks(longPressRunnable)
                    gestureHandler.removeCallbacks(singleTapRunnable)
                    gestureHandler.postDelayed(longPressRunnable, LONG_PRESS_TIMEOUT)
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    velocityTracker?.addMovement(event)
                    val dx = (event.rawX - initialTouchX).toInt()
                    val dy = (event.rawY - initialTouchY).toInt()
                    if (Math.abs(dx) > MOVE_THRESHOLD_PX || Math.abs(dy) > MOVE_THRESHOLD_PX) {
                        if (!hasMoved) {
                            // Movement cancels the pending long press
                            gestureHandler.removeCallbacks(longPressRunnable)
                        }
                        hasMoved = true
                        params?.x = initialX + dx
                        params?.y = initialY + dy
                        params?.let { p ->
                            overlayView?.let { v ->
                                windowManager?.updateViewLayout(v, p)
                            }
                        }
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    gestureHandler.removeCallbacks(longPressRunnable)
                    velocityTracker?.addMovement(event)
                    velocityTracker?.computeCurrentVelocity(1000)
                    val vx = velocityTracker?.xVelocity ?: 0f
                    val vy = velocityTracker?.yVelocity ?: 0f
                    velocityTracker?.recycle()
                    velocityTracker = null

                    val elapsed = System.currentTimeMillis() - touchStartTime
                    when {
                        // Long press already fired while the finger was down
                        longPressTriggered -> Unit
                        // Second tap inside the window → double tap, cancel the pending single tap
                        !hasMoved && elapsed <= LONG_PRESS_TIMEOUT &&
                                System.currentTimeMillis() - lastTapTime < DOUBLE_TAP_TIMEOUT -> {
                            gestureHandler.removeCallbacks(singleTapRunnable)
                            lastTapTime = 0L
                            fireJs("onDoubleTap()")
                        }
                        // Plain tap — delay it briefly to disambiguate from a double tap
                        !hasMoved -> {
                            lastTapTime = System.currentTimeMillis()
                            gestureHandler.removeCallbacks(singleTapRunnable)
                            gestureHandler.postDelayed(singleTapRunnable, DOUBLE_TAP_TIMEOUT)
                        }
                        // Dragged: fling (fast flick) or a plain drag that ended
                        else -> {
                            if (Math.abs(vx) > FLING_VELOCITY_THRESHOLD ||
                                Math.abs(vy) > FLING_VELOCITY_THRESHOLD) {
                                fireJs("onFling($vx, $vy)")
                            } else {
                                fireJs("onDragEnd()")
                            }
                        }
                    }
                    true
                }
                MotionEvent.ACTION_CANCEL -> {
                    // System stole the gesture (call, notification…) — reset everything
                    gestureHandler.removeCallbacks(longPressRunnable)
                    gestureHandler.removeCallbacks(singleTapRunnable)
                    velocityTracker?.recycle()
                    velocityTracker = null
                    true
                }
                else -> false
            }
        }
    }

    private fun onTap() = fireJs("onTap()")

    private fun onDoubleTap() = fireJs("onDoubleTap()")

    private fun onLongPress() = fireJs("onLongPress()")

    // === NOTIFICATION ===

    private fun buildNotification(text: String): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this, 0,
            packageManager.getLaunchIntentForPackage(packageName),
            PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("\uD83D\uDC3E")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setSilent(true)
            .build()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Pet",
                NotificationManager.IMPORTANCE_LOW
            ).apply { setShowBadge(false) }
            getSystemService(NotificationManager::class.java)
                .createNotificationChannel(channel)
        }
    }

    // === UTILS ===

    private fun dpToPx(dp: Int): Int {
        return (dp * resources.displayMetrics.density).toInt()
    }

    override fun onDestroy() {
        gestureHandler.removeCallbacksAndMessages(null)
        velocityTracker?.recycle()
        velocityTracker = null
        overlayView?.let {
            it.loadUrl("about:blank")
            it.removeAllViews()
            windowManager?.removeView(it)
            it.destroy()
        }
        overlayView = null
        super.onDestroy()
    }
}
