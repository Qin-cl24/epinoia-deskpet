package com.epinoia.deskpet

import android.Manifest
import android.app.AppOpsManager
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.Settings
import android.widget.Button
import android.widget.EditText
import android.widget.SeekBar
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

/**
 * Epinoia 桌宠设置界面。
 * 权限引导 + 8 个功能开关 + AI 服务配置 + 启动/停止。
 */
class MainActivity : AppCompatActivity() {

    private lateinit var prefs: SharedPreferences

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        prefs = getSharedPreferences("deskpet_prefs", MODE_PRIVATE)

        findViewById<Button>(R.id.btn_overlay_perm).setOnClickListener { requestOverlay() }
        findViewById<Button>(R.id.btn_notif_perm).setOnClickListener { requestNotif() }
        findViewById<Button>(R.id.btn_storage_perm).setOnClickListener { requestStorage() }
        findViewById<Button>(R.id.btn_usage_perm).setOnClickListener { requestUsageAccess() }

        bindSwitch(R.id.sw_dock, "pref_dock", true)
        bindSwitch(R.id.sw_edge, "pref_edge_run", true)
        bindSwitch(R.id.sw_peek, "pref_peekaboo", true)
        bindSwitch(R.id.sw_actions, "pref_idle_actions", true)
        bindSwitch(R.id.sw_water, "pref_water", true)
        bindSwitch(R.id.sw_keyboard, "pref_keyboard", true)
        bindSwitch(R.id.sw_ai, "pref_ai_channel", true)
        bindSwitch(R.id.sw_http, "pref_local_http", true)
        bindSwitch(R.id.sw_deepseek, "pref_deepseek", true)
        bindSwitch(R.id.sw_fg_sense, "pref_fg_sense", true)

        // 桌宠尺寸：0 = 最小（52×24dp），100 = 最大（130×60dp）
        val tvSize = findViewById<TextView>(R.id.tv_size)
        val sbSize = findViewById<SeekBar>(R.id.sb_size)
        val sizePref = prefs.getInt("pref_pet_size", 0)
        sbSize.progress = sizePref
        tvSize.text = sizeLabel(sizePref)
        sbSize.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                tvSize.text = sizeLabel(progress)
                if (fromUser) prefs.edit().putInt("pref_pet_size", progress).apply()
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })

        val etUrl = findViewById<EditText>(R.id.et_ai_url)
        val etKey = findViewById<EditText>(R.id.et_ai_key)
        etUrl.setText(prefs.getString("pref_ai_url", ""))
        etKey.setText(prefs.getString("pref_ai_key", ""))
        findViewById<Button>(R.id.btn_save_ai).setOnClickListener {
            prefs.edit()
                .putString("pref_ai_url", etUrl.text.toString().trim())
                .putString("pref_ai_key", etKey.text.toString().trim())
                .apply()
            Toast.makeText(this, "AI 配置已保存（重启桌宠生效）", Toast.LENGTH_SHORT).show()
        }

        findViewById<Button>(R.id.btn_start).setOnClickListener {
            // 前台服务通知需要 POST_NOTIFICATIONS 才显示（Android 13+），没有通知服务易被杀
            if (Build.VERSION.SDK_INT >= 33 &&
                ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) {
                ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), 2)
            }
            if (Settings.canDrawOverlays(this)) {
                startForegroundService(Intent(this, PetOverlayService::class.java))
                Toast.makeText(this, "桌宠启动中...", Toast.LENGTH_SHORT).show()
            } else {
                Toast.makeText(this, "请先授予悬浮窗权限！", Toast.LENGTH_LONG).show()
                requestOverlay()
            }
        }

        findViewById<Button>(R.id.btn_stop).setOnClickListener {
            stopService(Intent(this, PetOverlayService::class.java))
            Toast.makeText(this, "桌宠已停止", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onResume() {
        super.onResume()
        refreshPermButtons()
    }

    private fun bindSwitch(id: Int, key: String, def: Boolean) {
        val sw = findViewById<Switch>(id)
        sw.isChecked = prefs.getBoolean(key, def)
        sw.setOnCheckedChangeListener { _, checked ->
            prefs.edit().putBoolean(key, checked).apply()
        }
    }

    /** 尺寸显示：0→52×24dp，100→130×60dp */
    private fun sizeLabel(progress: Int): String {
        val w = 52 + (130 - 52) * progress / 100
        val h = 24 + (60 - 24) * progress / 100
        return "当前：${w}×${h}dp"
    }

    private fun refreshPermButtons() {
        findViewById<Button>(R.id.btn_overlay_perm).text =
            if (Settings.canDrawOverlays(this)) "✅ 悬浮窗权限已授予" else "⚠️ 悬浮窗权限（必需）"
        findViewById<Button>(R.id.btn_notif_perm).text =
            if (Build.VERSION.SDK_INT < 33 ||
                ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                == PackageManager.PERMISSION_GRANTED
            ) "✅ 通知权限已授予" else "⚠️ 通知权限（保活用）"
        findViewById<Button>(R.id.btn_storage_perm).text =
            if (Build.VERSION.SDK_INT < 30 || Environment.isExternalStorageManager())
                "✅ 文件访问权限已授予" else "⚠️ 文件访问权限（AI 消息通道用）"
        findViewById<Button>(R.id.btn_usage_perm).text =
            if (hasUsageAccess()) "✅ 使用情况访问已授予" else "⚠️ 使用情况访问（前台感知用）"
    }

    /** 是否已授予「使用情况访问」特殊权限（前台 app 感知必需） */
    private fun hasUsageAccess(): Boolean {
        val appOps = getSystemService(AppOpsManager::class.java)
        val mode = appOps.unsafeCheckOpNoThrow(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            packageManager.getPackageInfo(packageName, 0).applicationInfo.uid,
            packageName
        )
        return mode == AppOpsManager.MODE_ALLOWED
    }

    private fun requestUsageAccess() {
        if (hasUsageAccess()) return
        startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
    }

    private fun requestNotif() {
        if (Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
            == PackageManager.PERMISSION_GRANTED
        ) return
        ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
    }

    private fun requestOverlay() {
        if (Settings.canDrawOverlays(this)) return
        startActivity(
            Intent(
                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:$packageName")
            )
        )
    }

    private fun requestStorage() {
        if (Build.VERSION.SDK_INT < 30 || Environment.isExternalStorageManager()) return
        startActivity(
            Intent(
                Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                Uri.parse("package:$packageName")
            )
        )
    }
}
