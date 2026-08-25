# Epinoia 桌宠：目前无特殊混淆规则
# 保留 JS 桥接口（AndroidBridge.getPref / peekOut）
-keep class com.epinoia.deskpet.PetOverlayService$AndroidBridge { *; }
