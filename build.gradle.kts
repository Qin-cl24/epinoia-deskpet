// 根工程：只声明插件版本，子模块（app）各自配置
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
}
