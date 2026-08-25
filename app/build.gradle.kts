import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
}

android {
    namespace = "com.epinoia.deskpet"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.epinoia.deskpet"
        minSdk = 26          // Android 8.0
        targetSdk = 34
        versionCode = 4
        versionName = "4.0"

        // AI 大脑（DeepSeek，本地内测）：Key/URL/Model 都在 local.properties（已被 gitignore），换供应商只改那里
        buildConfigField("String", "DEEPSEEK_BASE_URL", "\"${deepseekProp("DEEPSEEK_BASE_URL", "https://api.deepseek.com")}\"")
        buildConfigField("String", "DEEPSEEK_MODEL", "\"${deepseekProp("DEEPSEEK_MODEL", "deepseek-chat")}\"")
        buildConfigField("String", "DEEPSEEK_API_KEY", "\"${deepseekProp("DEEPSEEK_API_KEY", "")}\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        buildConfig = true
    }
}

/** 从 local.properties 读取 AI 配置（该文件已被 .gitignore 忽略，不会进仓库）；缺省用默认值 */
fun deepseekProp(key: String, def: String): String {
    val props = Properties()
    val local = rootProject.file("local.properties")
    if (local.exists()) {
        local.inputStream().use { props.load(it) }
    }
    return props.getProperty(key, def)
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.appcompat)
    implementation(libs.androidx.activity)
}
