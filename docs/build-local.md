# 本地编译指南（内测版）

在本地编译出 APK 装手机测试。分两种环境：

## 常规环境（PC / 已装 Android Studio）

```bash
# 需要：JDK 17+，Android SDK 34（compileSdk 34）
# SDK 路径写进 local.properties：
#   sdk.dir=/你的/Android/Sdk
# DeepSeek key（可选）：
#   DEEPSEEK_API_KEY=sk-你的key

./gradlew assembleDebug
# 产物：app/build/outputs/apk/debug/app-debug.apk
```

## Termux（本机 aarch64，内测主力环境）

Termux 是 ARM64，官方 Android build-tools 全是 x86_64，必须用 Termux 仓库的 aarch64 原生工具：

```bash
# 1. 依赖
pkg install openjdk-17 gradle unzip aapt2

# 2. 下载 Gradle 8.7（AGP 8.5 兼容；Termux 仓库的 gradle 9.x 与 AGP 8.5 不兼容）
cd $HOME && curl -fL -o gradle-8.7-bin.zip https://services.gradle.org/distributions/gradle-8.7-bin.zip
unzip gradle-8.7-bin.zip && rm gradle-8.7-bin.zip

# 3. Android SDK（cmdline-tools）
mkdir -p $HOME/android-sdk/cmdline-tools && cd $HOME/android-sdk/cmdline-tools
curl -fL -o cmdtools.zip https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
python3 -m zipfile -e cmdtools.zip . && mv cmdline-tools latest && rm cmdtools.zip
chmod +x $HOME/android-sdk/cmdline-tools/latest/bin/*

# 4. 安装 SDK 组件
export ANDROID_HOME=$HOME/android-sdk
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin
yes | sdkmanager --licenses
sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"

# 5. aapt2 必须用 aarch64 原生版（AGP 下载的 linux 版跑不了）
mkdir -p $HOME/.gradle
echo "android.aapt2FromMavenOverride=$(which aapt2)" >> $HOME/.gradle/gradle.properties

# 6. 工程 local.properties
#   sdk.dir=/data/data/com.termux/files/home/android-sdk

# 7. 编译（首次会自动生成 wrapper 并下载依赖，几分钟）
cd $HOME/AI-Live-Overflow
$HOME/gradle-8.7/bin/gradle wrapper --gradle-version 8.7   # 生成 wrapper jar
./gradlew assembleDebug
```

## 安装到手机

- 有 adb：`adb install app/build/outputs/apk/debug/app-debug.apk`
- 没 adb：把 APK 拷到手机（Termux 里 `cp` 到 `~/storage/downloads/`），文件管理器点开安装

首次打开需要：
1. 允许「悬浮窗」权限（App 内按钮会跳转系统设置）
2. Android 13+ 允许「通知」权限
3. 华为/小米等 ROM 建议加入电池白名单（防杀后台）

## 踩过的坑（Termux aarch64 专用）

| 坑 | 解法 |
|----|------|
| AGP 下载的 aapt2（x86_64）Daemon startup failed | `pkg install aapt2` + `android.aapt2FromMavenOverride`（见上） |
| Termux 仓库 gradle 9.x 加载 AGP 8.5 失败 | 用独立的 Gradle 8.7 发行版 |
| build-tools 34.0.0 的 aapt2 也是 x86_64 | 别用它，用 Termux 的 aapt2（16.0.0.4，兼容） |
| `java.util.Properties` 在 build.gradle.kts 报 Unresolved | 顶部 `import java.util.Properties` |
| release 构建的 zipalign 是 x86_64（可能失败） | 内测先用 debug 包；release 需另想办法（待验证） |
