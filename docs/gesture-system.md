# Gesture System

Your pet needs to respond to touch. This module handles tap, double-tap, long-press, drag, and fling.

## Design

All touch events come through `setOnTouchListener` on the WebView. The native layer classifies the gesture, then calls into JS to trigger the appropriate animation/reaction.

## State Machine

```
ACTION_DOWN
    │
    ├── no movement + short duration → TAP
    │       └── second tap within 300ms → DOUBLE TAP
    ├── no movement + long duration (>600ms) → LONG PRESS
    └── movement detected
            ├── fast + short → FLING
            └── slow/long → DRAG
```

## Key Parameters

```kotlin
const val DOUBLE_TAP_TIMEOUT = 300L    // ms between taps
const val LONG_PRESS_TIMEOUT = 600L    // ms to trigger long press
const val MOVE_THRESHOLD = 10          // px before counting as movement
```

## Skeleton Implementation

```kotlin
private var initialX = 0
private var initialY = 0
private var initialTouchX = 0f
private var initialTouchY = 0f
private var lastTapTime = 0L
private var touchStartTime = 0L
private var hasMoved = false

View.OnTouchListener { view, event ->
    when (event.action) {
        MotionEvent.ACTION_DOWN -> {
            initialX = params.x
            initialY = params.y
            initialTouchX = event.rawX
            initialTouchY = event.rawY
            touchStartTime = System.currentTimeMillis()
            hasMoved = false
            true
        }
        MotionEvent.ACTION_MOVE -> {
            val dx = (event.rawX - initialTouchX).toInt()
            val dy = (event.rawY - initialTouchY).toInt()
            if (abs(dx) > MOVE_THRESHOLD || abs(dy) > MOVE_THRESHOLD) {
                hasMoved = true
                params.x = initialX + dx
                params.y = initialY + dy
                windowManager.updateViewLayout(overlayView, params)
            }
            true
        }
        MotionEvent.ACTION_UP -> {
            val elapsed = System.currentTimeMillis() - touchStartTime
            if (!hasMoved) {
                when {
                    elapsed > LONG_PRESS_TIMEOUT -> onLongPress()
                    System.currentTimeMillis() - lastTapTime < DOUBLE_TAP_TIMEOUT -> onDoubleTap()
                    else -> {
                        lastTapTime = System.currentTimeMillis()
                        onTap()
                    }
                }
            } else {
                // NOTE: dx/dy from ACTION_MOVE are out of scope here — don't reference them!
                // Use a VelocityTracker for real fling detection:
                //   - addMovement(event) on every DOWN/MOVE/UP
                //   - computeCurrentVelocity(1000) on ACTION_UP
                //   - val vx = tracker.xVelocity; val vy = tracker.yVelocity
                //   - if (abs(vx) > 800 || abs(vy) > 800) onFling(vx, vy) else onDragEnd()
                onDragEnd() // placeholder — wire up the VelocityTracker as above
            }
            true
        }
        else -> false
    }
}
```

## Customization Ideas

- Tap: pet blinks, shows a speech bubble
- Double tap: pet does a special animation
- Long press: pet gets embarrassed / shows a menu
- Drag: pet looks dizzy or clings on
- Fling: pet flies across screen and crawls back
- Tap counter: track consecutive taps, unlock different reactions at 3/5/8/10 taps

## Reporting Gestures to Backend

Optionally log gestures to your backend for your AI to read:

```kotlin
private fun reportGesture(type: String) {
    scope.launch {
        // POST to your backend
        // { gesture_type: "tap", x: 50, y: 300, timestamp: ... }
    }
}
```

This lets your AI know when you interacted with the pet, what gesture you used, and respond accordingly in conversation.
