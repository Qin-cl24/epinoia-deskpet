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
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.SeekBar
import android.widget.Spinner
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

        // ===== 🎨 桌宠形象：皮肤 / 配件 / 待机微动作 / 活跃度 / 亲密度 =====
        // 注意：Spinner 在挂载到窗口时会派发一次「当前选中项」回调，若此时就把值写回 prefs，
        // 会把用户上次的选择重置掉（踩过：打开设置页 → 皮肤被打回原版橙）。所以用 initGuard 挡住首次回调。
        val skinKeys = listOf("orange", "peach", "mint", "night", "latte", "grape")
        val skinNames = listOf("原版橙", "蜜桃粉", "薄荷绿", "夜空蓝", "奶咖", "紫葡萄")
        var skinInit = true
        val spSkin = findViewById<Spinner>(R.id.sp_skin)
        styleSpinner(spSkin, skinNames)
        spSkin.setSelection(skinKeys.indexOf(prefs.getString("pref_skin", "orange")).coerceAtLeast(0))
        spSkin.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: AdapterView<*>?, v: View?, position: Int, id: Long) {
                if (skinInit) { skinInit = false; return }
                prefs.edit().putString("pref_skin", skinKeys[position]).apply()
                applyLookLive()
            }

            override fun onNothingSelected(p: AdapterView<*>?) {}
        }
        spSkin.post { skinInit = false }

        bindLookBox(R.id.cb_acc_cap, "pref_acc_cap")
        bindLookBox(R.id.cb_acc_sleepcap, "pref_acc_sleepcap")
        bindLookBox(R.id.cb_acc_xmascap, "pref_acc_xmascap")
        bindLookBox(R.id.cb_acc_scarf, "pref_acc_scarf")
        bindLookBox(R.id.cb_acc_phones, "pref_acc_phones")
        bindLookBox(R.id.cb_acc_glasses, "pref_acc_glasses")
        bindLookBox(R.id.cb_acc_halo, "pref_acc_halo")

        bindLookBox(R.id.cb_idle_blink, "pref_blink", true)
        bindLookBox(R.id.cb_idle_breathe, "pref_idle_breathe", true)
        bindLookBox(R.id.cb_idle_music, "pref_idle_music", false)
        bindLookBox(R.id.cb_idle_hop, "pref_idle_hop", false)
        bindLookBox(R.id.cb_toy_ball, "pref_toy_ball", true)
        bindLookBox(R.id.cb_life_acts, "pref_life_acts", true)

        val actSecs = listOf(8, 45, 150)
        val actNames = listOf("话痨（约 8 秒一次）", "正常（约 45 秒一次）", "安静（约 2.5 分钟一次）")
        var actInit = true
        val spAct = findViewById<Spinner>(R.id.sp_act)
        styleSpinner(spAct, actNames)
        spAct.setSelection(actSecs.indexOf(prefs.getInt("pref_act_sec", 45)).coerceAtLeast(0))
        spAct.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: AdapterView<*>?, v: View?, position: Int, id: Long) {
                if (actInit) { actInit = false; return }
                prefs.edit().putInt("pref_act_sec", actSecs[position]).apply()
                applyLookLive()
            }

            override fun onNothingSelected(p: AdapterView<*>?) {}
        }
        spAct.post { actInit = false }

        findViewById<Button>(R.id.btn_intimacy_reset).setOnClickListener {
            prefs.edit().putInt("pref_intimacy_count", 0).putInt("pref_intimacy_level", 1).apply()
            applyLookLive()
            updateIntimacyText()
            Toast.makeText(this, "亲密度已重置为 Lv1", Toast.LENGTH_SHORT).show()
        }
        updateIntimacyText()

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
        updateIntimacyText()
    }

    /** 下拉框：强制深色文字 + 白色弹窗底色。
     *  原因：App 主题是 Theme.AppCompat（深色主题，默认文字偏白），页面底色却是 #fff8f0 浅色，
     *  不显式定色就会「白字白底」看不清；而下拉弹窗本身自带深色底，两边都要定死，才不依赖主题。 */
    private fun styleSpinner(sp: Spinner, items: List<String>) {
        sp.adapter = object : ArrayAdapter<String>(this, android.R.layout.simple_spinner_dropdown_item, items) {
            override fun getView(position: Int, convertView: View?, parent: android.view.ViewGroup): View =
                super.getView(position, convertView, parent).apply {
                    (this as? TextView)?.setTextColor(0xFF333333.toInt())
                }

            override fun getDropDownView(position: Int, convertView: View?, parent: android.view.ViewGroup): View =
                super.getDropDownView(position, convertView, parent).apply {
                    (this as? TextView)?.setTextColor(0xFF333333.toInt())
                }
        }
        sp.setPopupBackgroundDrawable(android.graphics.drawable.ColorDrawable(0xFFFFFFFF.toInt()))
    }

    /** 形象类勾选项（配件/待机微动作）：改完立刻重载桌宠，不用重启 */
    private fun bindLookBox(id: Int, key: String, def: Boolean = false) {
        val cb = findViewById<CheckBox>(id)
        cb.isChecked = prefs.getBoolean(key, def)
        cb.setOnCheckedChangeListener { _, checked ->
            prefs.edit().putBoolean(key, checked).apply()
            applyLookLive()
        }
    }

    /** 桌宠在跑就直接重载 WebView（形象类设置即时生效）；没跑则下次启动生效 */
    private fun applyLookLive() {
        PetOverlayService.instance?.reloadPetView()
    }

    /** 亲密度文案：Lv1~4 + 距下一级还差几次互动 */
    private fun updateIntimacyText() {
        val count = prefs.getInt("pref_intimacy_count", 0)
        val lv = prefs.getInt("pref_intimacy_level", 1)
        val next = when (lv) {
            1 -> 30
            2 -> 100
            3 -> 300
            else -> -1
        }
        val tv = findViewById<TextView>(R.id.tv_intimacy)
        tv.text = if (next > 0) {
            "亲密度 Lv$lv · 已互动 $count 次（再 ${(next - count).coerceAtLeast(0)} 次升 Lv${lv + 1}）"
        } else {
            "亲密度 Lv4 · 已互动 $count 次（满级，红晕+光环都在啦）"
        }
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
