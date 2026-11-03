#!/usr/bin/env python3
"""生成小屋页面 assets/room.html —— 真 3D 立方体（只留一个角的底面 + 左右两面）

按主人的描述：把小屋想成一个立方体，只保留**一个角的底面和左右两个面**，
其余面全部去掉 —— 就是一个开口的立体盒子，从斜上方看进去。

实现：CSS 3D（perspective + preserve-3d）
    · .floor       底面：绕 X 轴转 90° 躺平，从角点向 +x / +z 铺开
    · .wall.back   后墙：z=0 平面，从角点向 +x 展开
    · .wall.left   左墙：x=0 平面，从角点向 +z 展开（绕 Y 轴 -90°）
    · 家具/角色都是「立在底面上的帖子」：translate3d(x,0,z) 定位，本体由 .sprite 立着不倒，
      影子是 rotateX(-90deg) 躺在地面上的椭圆
图层坐标不手写：读 assets/fox/_layers.json（fox-build-from-psd.py 生成），
主人重导画稿后跑一次本脚本 + 重新编译，小屋里的狐狐就跟着更新。

用法：
    python3 tools/build-room3d.py            # 写 app/src/main/assets/room.html
    python3 tools/build-room3d.py --stdout   # 只打印
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
ASSETS = os.path.join(PROJ, "app", "src", "main", "assets")
LAYERS = os.path.join(ASSETS, "fox", "_layers.json")

ORDER = ["tail-outer", "tail-inner", "shoes", "pants", "pants-front", "leg-detail-L", "leg-detail-R",
         "hair-back", "neck-hands", "top", "sleeves", "ear-L", "fur-under-ear-L", "head", "part25",
         "mouth", "eye-white-R", "eye-white-L", "iris-R", "iris-L", "lash-R-upper", "lash-L-lower",
         "lash-L-upper", "eyelid-R", "brow-C", "brow-L", "brow-R", "lash-L-extra", "ear-R", "bangs",
         "fur-under-ear-R", "hair-highlight", "hair-tuft", "ahoge"]
EYE_GROUP = {
    "R": ["eye-white-R", "iris-R", "lash-R-upper", "brow-R", "eyelid-R"],
    "L": ["eye-white-L", "iris-L", "lash-L-upper", "lash-L-lower", "lash-L-extra"],
}

W, D, H = 420, 500, 300
RUGR = (215, 300)      # 地毯在地面上的中心点          # 房间底面宽 / 进深 / 墙高（CSS px）


def build():
    meta = json.load(open(LAYERS))
    lay = meta["layers"]
    order = [n for n in ORDER if n in lay]

    geo, dom = [], []
    for n in order:
        l, t, w, h = lay[n]["app"]
        geo.append(f'      .fx-{n} {{ left:{l}px; top:{t}px; width:{w}px; height:{h}px; }}')
        dom.append(f'        <img class="fx fx-{n}" src="fox/{n}.png" alt="">')

    anchors = {}
    for side in ("L", "R"):
        white = f"eye-white-{side}"
        if white not in lay:
            continue
        l, t, w, h = lay[white]["app"]
        anchors[side] = (l + w // 2, t + h)

    blink = []
    for side, names in EYE_GROUP.items():
        if side not in anchors:
            continue
        ax, ay = anchors[side]
        for n in names:
            if n not in lay:
                continue
            l, t, w, h = lay[n]["app"]
            blink.append(f"      .fx-{n} {{ transform-origin: {ax - l}px {ay - t}px; transition: transform .09s ease-out; }}")
    blink_sel = ",\n      ".join(f".pet-room.blink .fx-{n}" for s in EYE_GROUP for n in EYE_GROUP[s] if n in lay)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>狐狐的小屋</title>
<style>
  * {{ box-sizing:border-box; -webkit-tap-highlight-color:transparent; }}
  html, body {{ margin:0; height:100%; overflow:hidden; user-select:none;
    font-family: system-ui, sans-serif; background:#1d150e; }}

  /* ===== 3D 舞台：开口的立方体，只留一个角的底面 + 左右两面 ===== */
  .stage {{ position:fixed; inset:0; perspective: 1500px; perspective-origin: 50% 44%; touch-action:none;
    background: radial-gradient(circle at 50% 26%, #372b1e, #17110b 72%); }}
  .world {{ position:absolute; left:50%; top:40%; width:0; height:0;
    transform-style: preserve-3d;
    /* 先把房间的几何中心挪到原点，再套相机旋转（俯视 26°、水平转 -34°）*/
    transform: scale(.85) rotateX(-32deg) rotateY(-30deg) translate3d(-{W//2}px, {H//2}px, -{D//2}px); }}

  /* 底面：做成一块有厚度的板（正面沿 + 右侧沿各一条薄边）*/
  .floor {{ position:absolute; left:0; top:0; width:{W}px; height:{D}px;
    transform-origin:0 0; transform: rotateX(90deg); transform-style: preserve-3d;
    background:
      repeating-linear-gradient(90deg, rgba(96,60,28,.16) 0 2px, transparent 2px 45px),
      repeating-linear-gradient(0deg, rgba(96,60,28,.13) 0 2px, transparent 2px 45px),
      linear-gradient(150deg, #e9c69c, #cf9a6a 60%, #c08a5c); }}
  /* 后墙（z=0 平面） */
  .wall.back {{ position:absolute; left:0; top:-{H}px; width:{W}px; height:{H}px; transform-style: preserve-3d;
    background:
      radial-gradient(circle at 18% 26%, rgba(255,255,255,.55) 0 3px, transparent 3px) 0 0/48px 48px,
      radial-gradient(circle at 68% 72%, rgba(255,255,255,.42) 0 3px, transparent 3px) 0 0/48px 48px,
      linear-gradient(180deg, #f8ecd9, #ecd6b8);
    box-shadow: inset 0 -14px 24px rgba(120,80,40,.18); }}
  /* 左墙（x=0 平面，绕底边转 -90° 立起来） */
  .wall.left {{ position:absolute; left:0; top:-{H}px; width:{D}px; height:{H}px;
    transform-origin:0 100%; transform: rotateY(-90deg); transform-style: preserve-3d;
    background:
      radial-gradient(circle at 22% 30%, rgba(255,255,255,.45) 0 3px, transparent 3px) 0 0/48px 48px,
      linear-gradient(180deg, #f2e2cb, #dcc2a0);
    box-shadow: inset 0 -14px 24px rgba(110,72,36,.24); }}
  /* 踢脚线 */
  .base {{ position:absolute; background:#b57f52; }}
  .base.back {{ left:0; bottom:0; width:{W}px; height:12px; }}
  .base.left {{ left:0; bottom:0; width:{D}px; height:12px; }}

  /* 窗：贴在后墙上 */
  .window {{ position:absolute; left:52%; top:16%; width:132px; height:104px; border-radius:8px; cursor:pointer;
    background: linear-gradient(#bfe3f7, #e7f6ff); border:6px solid #d9b08c; overflow:hidden;
    box-shadow: 0 4px 12px rgba(0,0,0,.16), inset 0 0 0 2px rgba(255,255,255,.6); }}
  .window::before {{ content:''; position:absolute; left:50%; top:0; bottom:0; width:5px; margin-left:-2.5px; background:#d9b08c; }}
  .window::after {{ content:''; position:absolute; top:50%; left:0; right:0; height:5px; margin-top:-2.5px; background:#d9b08c; }}
  .sun {{ position:absolute; right:10px; top:10px; width:26px; height:26px; border-radius:50%;
    background:radial-gradient(circle, #ffe680, #ffcf40); box-shadow:0 0 16px rgba(255,214,64,.85); }}
  .cloud {{ position:absolute; left:8px; top:12px; width:40px; height:12px; border-radius:20px;
    background:rgba(255,255,255,.92); box-shadow:11px -6px 0 -2px rgba(255,255,255,.92); animation: drift 9s ease-in-out infinite; }}
  @keyframes drift {{ 0%,100% {{ transform: translateX(0); }} 50% {{ transform: translateX(20px); }} }}

  /* ===== 地板和墙的厚度（直接挂在 .world 里，用世界坐标，不会被父层的旋转带跑）===== */
  .slab {{ position:absolute; left:0; top:0; }}
  .floor-front {{ width:{W}px; height:56px; margin:-13px 0 0 -{W//2}px;
    background:linear-gradient(#b0763f, #7d4f28);
    transform: translate3d({W//2}px, 27px, {D}px); }}
  .floor-right {{ width:{D}px; height:56px; margin:-13px 0 0 -{D//2}px;
    background:linear-gradient(#bd8248, #8a5a2e);
    transform: translate3d({W}px, 27px, {D//2}px) rotateY(-90deg); }}
  .wall-back-top {{ width:{W}px; height:36px; margin:-8px 0 0 -{W//2}px;
    background:linear-gradient(#a98a63, #8a6c47);
    transform: translate3d({W//2}px, -{H}px, -18px) rotateX(-90deg); }}
  .wall-left-top {{ width:{D}px; height:36px; margin:-8px 0 0 -{D//2}px;
    background:linear-gradient(#9d7f5c, #7f6242);
    transform: translate3d(18px, -{H}px, {D//2}px) rotateX(-90deg) rotateZ(90deg); }}

  /* ===== 贴墙环境阴影（AO）：让墙和地之间有"转角"的暗部，立体感靠它 ===== */
  .ao-floor-back {{ position:absolute; left:0; top:0; width:{W}px; height:60px; margin:0 0 0 -{W//2}px;
    background:linear-gradient(180deg, rgba(70,40,16,.42), rgba(70,40,16,0));
    transform: translate3d({W//2}px, -1px, 30px) rotateX(-90deg); }}
  .ao-floor-left {{ position:absolute; left:0; top:0; width:60px; height:{D}px; margin:-{D//2}px 0 0 -30px;
    background:linear-gradient(90deg, rgba(70,40,16,.45), rgba(70,40,16,0));
    transform: translate3d(30px, -1px, {D//2}px) rotateX(-90deg) rotateZ(90deg); }}
  .ao-corner {{ position:absolute; left:0; top:0; width:70px; height:{H}px; margin:-{H//2}px 0 0 -35px;
    background:radial-gradient(ellipse at 100% 100%, rgba(90,55,25,.5), rgba(90,55,25,0) 70%);
    transform: translate3d(0, -{H//2}px, 1px); }}

  /* 墙的端面（后墙右端、左墙近端）：让墙看起来是有厚度的板 */
  .wall-end {{ position:absolute; left:0; top:0; }}
  .wall-end.back {{ width:36px; height:{H}px; margin:-{H//2}px 0 0 -18px;
    background:linear-gradient(90deg, #c9ab84, #a98a63);
    transform: translate3d({W}px, -{H//2}px, -18px) rotateY(-90deg); }}
  .wall-end.left {{ width:36px; height:{H}px; margin:-{H//2}px 0 0 -18px;
    background:linear-gradient(90deg, #c3a582, #a3855f);
    transform: translate3d(-18px, -{H//2}px, {D}px); }}

  /* ===== 地面上的东西 ===== */
  .item {{ position:absolute; left:0; top:0; transform-style:preserve-3d; }}
  .pshadow {{ position:absolute; left:0; top:0; width:150px; height:150px; margin:-75px 0 0 -75px;
    border-radius:50%; background:rgba(70,40,16,.34); filter:blur(9px); transform: rotateX(-90deg); }}
  .sprite {{ position:absolute; left:0; bottom:0; transform: translateX(-50%); transform-origin: bottom center;
    transform-style: preserve-3d; }}   /* 不开这个，里面的顶面/侧面会被拍平 */

  /* 地毯：平铺在地面上 */
  /* 地毯：用「负 margin 把盒子居中到锚点，然后只做 rotateX」的写法。
     ⚠️ 关键：盒子中心必须正好落在锚点上，否则 transform-origin 在元素中心，
     旋转后整块会偏到地板下面去（上一版就是这样掉了 90px）。*/
  .rugface {{ position:absolute; left:0; top:0; width:250px; height:190px;
    margin:-95px 0 0 -125px; transform: rotateX(-90deg);
    border-radius:50%;
    background: radial-gradient(ellipse at 50% 42%, #ffe9c6, #efc78a);
    box-shadow: inset 0 0 0 6px rgba(255,255,255,.5); }}

  /* 床（2026-11-03 第三版，真立体）：床垫盒子（正面+顶面+右侧面）+ 床头板 + 枕头 + 被子
     所有面都是 .sprite（preserve-3d）的子元素；盒子中心用负 margin 对齐锚点，再 translate3d 到各自位置。*/
  .bed {{ cursor:pointer; }}
  .bed .f {{ position:absolute; left:0; top:0; }}
  /* 床垫正面（朝观察者，z=+55）*/
  .bed .m_front {{ width:150px; height:40px; margin:-20px 0 0 -75px; border-radius:5px;
    background:linear-gradient(#ffffff, #ece7fb); box-shadow:inset 0 -6px 0 rgba(0,0,0,.06);
    transform: translate3d(0,-20px,55px); }}
  /* 床垫顶面（平躺 y=-40）*/
  .bed .m_top {{ width:150px; height:110px; margin:-55px 0 0 -75px; border-radius:5px;
    background:linear-gradient(#ffffff, #f2eefc);
    transform: translate3d(0,-40px,0) rotateX(-90deg); }}
  /* 床垫右侧面（x=+75，朝右）*/
  .bed .m_side {{ width:110px; height:40px; margin:-20px 0 0 -55px;
    background:linear-gradient(90deg, #e6e0f8, #d3c9ef);
    transform: translate3d(75px,-20px,0) rotateY(90deg); }}
  /* 床头板：竖在左端、贴左墙（x=-75，朝右的面）*/
  .bed .m_head {{ width:110px; height:92px; margin:-46px 0 0 -55px; border-radius:6px 6px 3px 3px;
    background:linear-gradient(100deg, #d8ac7d, #a9794f); box-shadow:inset 0 4px 0 rgba(255,255,255,.25);
    transform: translate3d(-75px,-46px,0) rotateY(90deg); }}
  /* 枕头（躺在床面上，靠床头那头）*/
  .bed .m_pillow {{ width:44px; height:62px; margin:-31px 0 0 -22px; border-radius:12px;
    background:linear-gradient(#ffffff, #f4f1fd); box-shadow:0 2px 6px rgba(60,35,15,.18);
    transform: translate3d(-46px,-42px,0) rotateX(-90deg); }}
  /* 被子：铺在床面右半边（y=-41，比床面高 1px 免得打架）*/
  .bed .m_quilt {{ width:92px; height:112px; margin:-56px 0 0 -46px; border-radius:5px;
    background:linear-gradient(#c3b2f4, #9d86e8);
    transform: translate3d(28px,-41px,0) rotateX(-90deg); }}
  /* 被子垂下来的前挡（z=+56，正面）*/
  .bed .m_flap {{ width:92px; height:24px; margin:-12px 0 0 -46px; border-radius:0 0 5px 5px;
    background:linear-gradient(#a790ec, #8b73dd);
    transform: translate3d(28px,-12px,56px); }}

  /* 饭碗 / 收音机（都带右侧暗面，看着有厚度）*/
  .bowl {{ cursor:pointer; }}
  .bowl .cup {{ width:74px; height:36px; margin:-18px 0 0 -37px; border-radius:0 0 34px 34px;
    background:linear-gradient(#f4f4f4, #c6c6c6);
    box-shadow: inset -9px 0 0 rgba(0,0,0,.10), inset 0 -8px 0 rgba(0,0,0,.06);
    transform: translate3d(0,-18px,0); }}
  /* 碗口外圈（平躺 y=-36）*/
  .bowl .brim-o {{ width:74px; height:26px; margin:-13px 0 0 -37px; border-radius:50%;
    background:linear-gradient(#ffc978, #ff9f3d);
    transform: translate3d(0,-36px,0) rotateX(-90deg); }}
  /* 碗口内壁（稍高一点、稍小）*/
  .bowl .brim-i {{ width:60px; height:20px; margin:-10px 0 0 -30px; border-radius:50%;
    background:radial-gradient(ellipse at 50% 40%, #fff3dd, #e9c79a);
    transform: translate3d(0,-37px,0) rotateX(-90deg); }}
  /* 碗里的食物 */
  .bowl .meal {{ width:42px; height:13px; margin:-6px 0 0 -21px; border-radius:50%;
    background:radial-gradient(ellipse at 50% 35%, #ffd08a, #ffab52);
    transform: translate3d(0,-38px,0) rotateX(-90deg); }}
  .radio {{ cursor:pointer; }}
  .radio .case {{ position:absolute; left:0; bottom:0; width:66px; height:50px; transform: translateX(-50%);
    border-radius:7px; background:linear-gradient(#8d6e63, #6d4c41);
    box-shadow:0 8px 14px rgba(60,35,15,.34), inset -8px 0 0 rgba(0,0,0,.18); }}
  .radio .dial {{ position:absolute; left:-18px; bottom:22px; width:22px; height:22px; border-radius:50%;
    background:radial-gradient(circle at 50% 50%, #fff 0 30%, #bdbdbd 32% 60%, #8d8d8d 62%); }}
  .radio .lamp {{ position:absolute; left:14px; bottom:26px; width:9px; height:9px; border-radius:50%;
    background:#ffd54f; box-shadow:0 -13px 0 -1px #ffd54f; }}
  /* 收音机顶面（平躺在 y=-50 的平面）和右侧面（x=+33 的平面）*/
  .radio .rtop {{ width:66px; height:40px; margin:-20px 0 0 -33px; background:linear-gradient(#a1887f, #8d6e63);
    transform: translateY(-50px) rotateX(-90deg); border-radius:4px;
    box-shadow: inset 0 0 0 2px rgba(255,255,255,.16); }}
  .radio .rside {{ width:40px; height:50px; margin:-25px 0 0 -20px;
    background:linear-gradient(90deg, #7a5a4f, #5d4037);
    transform: translate3d(33px,-25px,0) rotateY(90deg); border-radius:0 4px 4px 0; }}
  /* 天线：细杆立在右侧顶上 */
  .radio .ant {{ width:3px; height:34px; margin:0 0 0 -1.5px;
    background:linear-gradient(#e0e0e0, #9e9e9e); border-radius:2px;
    transform: translate3d(24px,-84px,4px) rotateZ(12deg); }}
  .notes {{ position:absolute; left:0; bottom:62px; transform:translateX(-50%); font-size:15px; opacity:0; }}
  .notes.on {{ opacity:1; animation: floatUp 1.4s ease-in-out infinite; }}
  @keyframes floatUp {{ 0% {{ transform:translate(-50%,0); opacity:0; }} 40% {{ opacity:1; }}
                        100% {{ transform:translate(-50%,-26px); opacity:0; }} }}

  /* ===== 方块形态 ===== */
  .blockpet {{ width:72px; height:50px; transform: scale(1.5); transform-origin: bottom center;
    transform-style: preserve-3d; position:relative; }}
  .blockpet .body {{ position:relative; width:56px; height:36px; margin:4px auto 0; border-radius:4px;
    background:#e67e22;
    box-shadow: inset 0 2px 0 rgba(255,255,255,.22), inset -7px 0 0 rgba(0,0,0,.14), inset 0 -3px 0 rgba(0,0,0,.10);
    animation: blockIdle 2.6s ease-in-out infinite; }}
  .blockpet .eye {{ position:absolute; width:5px; height:10px; background:#000; top:9px; border-radius:2px; transition: height .1s; }}
  .blockpet .eye-left {{ left:12px; }} .blockpet .eye-right {{ right:12px; }}
  .pet-room.blink .blockpet .eye {{ height:2px; }}
  .blockpet .arm {{ position:absolute; width:10px; height:10px; top:12px; background:#e67e22;
    background-image:linear-gradient(180deg, rgba(255,255,255,.20), rgba(255,255,255,.05)); }}
  .blockpet .arm-left {{ left:-10px; }} .blockpet .arm-right {{ right:-10px; }}
  .blockpet .leg {{ position:absolute; width:5px; height:10px; bottom:-10px;
    background:linear-gradient(180deg, #e67e22 0%, #d35400 58%); }}
  .blockpet .leg-l1 {{ left:8px; }} .blockpet .leg-l2 {{ left:17px; }}
  .blockpet .leg-r1 {{ right:8px; }} .blockpet .leg-r2 {{ right:17px; }}
  /* 立方体：顶面（平躺）+ 右侧面 + 左侧面（都贴在身体面上）*/
  .blockpet .cb-top {{ position:absolute; left:0; top:0; width:56px; height:40px; margin:-20px 0 0 -28px;
    background:linear-gradient(#f2944a, #e07b2a); border-radius:4px;
    transform: translate3d(28px, -40px, 28px) rotateX(90deg); }}
  .blockpet .cb-right {{ position:absolute; left:0; top:0; width:40px; height:36px; margin:-18px 0 0 -20px;
    background:linear-gradient(#d9752a, #b8590f); border-radius:0 4px 4px 0;
    transform: translate3d(56px, -14px, 28px) rotateY(90deg); }}
  .blockpet .cb-left {{ position:absolute; left:0; top:0; width:40px; height:36px; margin:-18px 0 0 -20px;
    background:linear-gradient(#e8863a, #cf7222); border-radius:4px 0 0 4px;
    transform: translate3d(0, -14px, 28px) rotateY(-90deg); }}
  @keyframes blockIdle {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-2px); }} }}
  .walking #blockitem .blockpet .body {{ animation: blockWalk .45s ease-in-out infinite; }}
  @keyframes blockWalk {{ 0%,100% {{ transform: rotate(-4deg); }} 50% {{ transform: rotate(4deg); }} }}
  .room.act-eat #blockitem .blockpet .body {{ animation: blockEat .5s ease-in-out infinite; }}
  @keyframes blockEat {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(4px) scaleY(.97); }} }}
  .room.act-sleep #blockitem .sprite {{ transform: translateX(-50%) rotate(-78deg) translateY(-10px); }}
  .room.act-look #blockitem .sprite {{ transform: translateX(-50%) translateY(-6px); }}
  .room.act-dance #blockitem .sprite {{ animation: blockDance .5s ease-in-out infinite; }}
  @keyframes blockDance {{ 0%,100% {{ transform: translateX(-50%) rotate(-8deg); }}
                           50% {{ transform: translateX(-50%) rotate(8deg) translateY(-5px); }} }}
  .room.bounce #blockitem .sprite {{ animation: blockHop .45s ease-out; }}
  @keyframes blockHop {{ 0%,100% {{ transform: translateX(-50%) translateY(0); }}
                         40% {{ transform: translateX(-50%) translateY(-16px); }} }}

  /* ===== 狐狐（34 层）===== */
  .fox {{ position:relative; width:543px; height:626px; transform: scale(.30); transform-origin: bottom center; }}
  .fox-inner {{ position:absolute; inset:0; animation: foxBreathe 3.2s ease-in-out infinite; pointer-events:none; }}
  @keyframes foxBreathe {{ 0%,100% {{ transform: translateY(0) scaleY(1); }} 50% {{ transform: translateY(-2px) scaleY(.99); }} }}
  .fox img.fx {{ position:absolute; display:block; pointer-events:none; }}
      {chr(10).join(geo)}
  .fox .fox-hit {{ position:absolute; left:27%; top:18%; width:48%; height:71%; cursor:pointer; border-radius:45%; }}
  .room.act-sleep #foxitem .sprite {{ transform: translateX(-50%) rotate(-74deg) translateY(-26px); }}
  .room.act-look #foxitem .sprite {{ transform: translateX(-50%) translateY(-8px); }}
  .room.act-dance #foxitem .sprite {{ animation: foxDance .55s ease-in-out infinite; }}
  @keyframes foxDance {{ 0%,100% {{ transform: translateX(-50%) rotate(-6deg); }}
                         50% {{ transform: translateX(-50%) rotate(6deg) translateY(-4px); }} }}
  .room.bounce #foxitem .sprite {{ animation: foxHop .45s ease-out; }}
  @keyframes foxHop {{ 0%,100% {{ transform: translateX(-50%) translateY(0); }}
                       40% {{ transform: translateX(-50%) translateY(-18px); }} }}
      {chr(10).join(blink)}
      {blink_sel} {{ transform: scaleY(.12); }}

  /* 形态切换 */
  #foxitem {{ display:none; }}
  .room[data-form="fox"] #foxitem {{ display:block; }}
  .room[data-form="fox"] #blockitem {{ display:none; }}

  /* ===== 机位微调面板（调试期用，调好我就把最终数值写死）===== */
  .tuner {{ position:fixed; left:0; right:0; bottom:0; display:flex; gap:6px; justify-content:center;
    padding:8px; background:rgba(30,20,12,.72); z-index:30; flex-wrap:wrap; }}
  .tuner button {{ min-width:44px; border:none; border-radius:10px; padding:8px 6px; font-size:12px;
    background:#f0dcc8; color:#5a4636; cursor:pointer; }}
  .tuner .val {{ color:#ffd9a8; font-size:11px; align-self:center; padding:0 6px; }}

  /* ===== 顶栏 / 气泡 ===== */
  .top {{ position:fixed; left:0; right:0; top:0; height:52px; display:flex; align-items:center; gap:8px;
    padding:0 12px; background:linear-gradient(rgba(255,248,240,.92), rgba(255,248,240,0)); z-index:20; }}
  .title {{ font-size:15px; font-weight:600; color:#6b5341; }}
  .formbtn, .close {{ border:none; border-radius:14px; padding:5px 10px; font-size:12px; cursor:pointer;
    background:#f0dcc8; color:#6b5341; }}
  .formbtn.on {{ background:#e6a86b; color:#fff; }}
  .close {{ width:34px; height:34px; border-radius:50%; font-size:16px; }}
  .hint {{ font-size:11px; color:#a58b74; margin-left:auto; }}
  .bubble {{ position:fixed; left:50%; top:22%; transform:translateX(-50%); background:#fff; color:#5a4636;
    padding:8px 14px; border-radius:16px; font-size:14px; box-shadow:0 6px 16px rgba(0,0,0,.22);
    opacity:0; transition: opacity .18s, transform .18s; pointer-events:none; white-space:nowrap; z-index:20; }}
  .bubble.on {{ opacity:1; transform:translateX(-50%) translateY(-3px); }}
</style>
</head>
<body>
<div class="room pet-room" id="room" data-form="block">
  <div class="stage">
    <div class="world">
      <div class="wall back"><span class="base back"></span>
        <div class="window" id="window"><span class="sun"></span><span class="cloud"></span></div>
      </div>
      <div class="wall left"><span class="base left"></span></div>
      <span class="slab floor-front" id="fedge"></span>
      <span class="slab floor-right" id="redge"></span>
      <span class="slab wall-back-top" id="wbtop"></span>
      <span class="slab wall-left-top" id="wltop"></span>
      <span class="wall-end back" id="weback"></span>
      <span class="wall-end left" id="weleft"></span>
      <span class="ao-floor-back" id="aob"></span>
      <span class="ao-floor-left" id="aol"></span>
      <span class="ao-corner" id="aoc"></span>
      <div class="floor" id="flooritem"></div>

      <div class="item" id="rugitem" style="transform: translate3d({RUGR[0]}px,-1px,{RUGR[1]}px)">
        <span class="rugface"></span>
      </div>

      <div class="item bed" id="beditem" data-act="sleep" data-x="78" data-z="140"
           style="transform: translate3d(78px,0,140px)">
        <span class="pshadow" style="width:180px;height:140px"></span>
        <div class="sprite"><div class="f m_head"></div><div class="f m_side"></div><div class="f m_front"></div><div class="f m_top"></div><div class="f m_quilt"></div><div class="f m_flap"></div><div class="f m_pillow"></div></div>
      </div>

      <div class="item bowl" id="bowlitem" data-act="eat" data-x="300" data-z="390"
           style="transform: translate3d(300px,0,390px)">
        <span class="pshadow" style="width:110px;height:90px"></span>
        <div class="sprite"><div class="cup"></div><div class="brim-o"></div><div class="brim-i"></div><div class="meal"></div></div>
      </div>

      <div class="item radio" id="radioitem" data-act="dance" data-x="350" data-z="140"
           style="transform: translate3d(350px,0,140px)">
        <span class="pshadow" style="width:120px;height:90px"></span>
        <div class="sprite"><div class="case"></div><div class="rtop"></div><div class="rside"></div><div class="dial"></div><div class="lamp"></div><div class="ant"></div></div>
        <span class="notes" id="notes">🎵</span>
      </div>

      <div class="item" id="blockitem" style="transform: translate3d(210px,0,310px)">
        <span class="pshadow" style="width:120px;height:95px"></span>
        <div class="sprite" id="blocksprite"><div class="blockpet">
          <span class="cb-top"></span><span class="cb-left"></span><span class="cb-right"></span>
          <div class="body">
          <div class="eye eye-left"></div><div class="eye eye-right"></div>
          <div class="arm arm-left"></div><div class="arm arm-right"></div>
          <div class="leg leg-l1"></div><div class="leg leg-l2"></div>
          <div class="leg leg-r1"></div><div class="leg leg-r2"></div>
        </div></div></div>
        <!-- 立方体的三个额外面在上面 span 里 -->
      </div>

      <div class="item" id="foxitem" style="transform: translate3d(210px,0,310px)">
        <span class="pshadow" style="width:160px;height:120px"></span>
        <div class="sprite">
          <div class="fox" id="fox">
            <div class="fox-hit" id="foxhit"></div>
            <div class="fox-inner">
{chr(10).join(dom)}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="bubble" id="bubble"></div>

  <div class="top">
    <span class="title">🏠 小屋</span>
    <button class="formbtn on" id="btn-block">🐣 方块</button>
    <button class="formbtn" id="btn-fox">🦊 狐狐</button>
    <span class="hint">点家具试试</span>
    <button class="close" id="gear">⚙️</button>
    <button class="close" id="close">✕</button>
  </div>
</div>
<script>
  var room = document.getElementById('room');
  var foxitem = document.getElementById('foxitem');
  var blockitem = document.getElementById('blockitem');
  var bubble = document.getElementById('bubble');
  var notes = document.getElementById('notes');
  var foxEl = document.getElementById('fox');
  var busy = false, actTimer = null;

  function note(s) {{ try {{ window.RoomBridge && RoomBridge.note(s); }} catch (e) {{ console.log('note fail ' + e.message); }} }}
  function say(t, ms) {{
    bubble.textContent = t; bubble.classList.add('on');
    clearTimeout(say._t);
    say._t = setTimeout(function () {{ bubble.classList.remove('on'); }}, ms || 1800);
  }}
  function pick(a) {{ return a[Math.floor(Math.random() * a.length)]; }}
  function activeItem() {{ return room.dataset.form === 'fox' ? foxitem : blockitem; }}

  var SAY = {{
    sleep: ['有点困…', '睡一会儿', '（抱着尾巴睡着）'],
    eat:   ['好香！', '开动啦', '呼噜呼噜～'],
    look:  ['外面好亮', '云飘过去了', '有人路过呢'],
    dance: ['一起听！', '这段好听', '啦啦啦～'],
    idle:  ['在屋里转转', '今天待在小屋', '要不要一起玩']
  }};
  var ACT_CLASS = {{ sleep: 'act-sleep', eat: 'act-eat', look: 'act-look', dance: 'act-dance' }};
  var HOME = {{ x: 210, z: 310 }};

  function goTo(x, z, ms) {{
    var it = activeItem();
    var cur = parseFloat(it.dataset.curx || HOME.x);
    if (room.dataset.form === 'fox') foxEl.classList.toggle('flip', x < cur);
    it.dataset.curx = x;
    it.style.transition = 'transform ' + ms + 'ms ease-in-out';
    it.style.transform = 'translate3d(' + x + 'px,0,' + z + 'px)';
    room.classList.add('walking');
    return new Promise(function (res) {{
      setTimeout(function () {{ room.classList.remove('walking'); res(); }}, ms);
    }});
  }}

  function doAct(kind, x, z) {{
    note('click ' + kind + ' target=' + x + ',' + z + ' busy=' + busy);
    clearTimeout(actTimer);
    room.classList.remove('act-sleep', 'act-eat', 'act-look', 'act-dance');
    notes.classList.remove('on');
    busy = true;
    say({{ sleep: '去躺一下', eat: '肚子饿了', look: '去看看窗外', dance: '放首歌吧' }}[kind] || '', 1100);
    goTo(x, z, 900).then(function () {{
      note('arrived ' + kind);
      room.classList.add(ACT_CLASS[kind]);
      if (kind === 'dance') notes.classList.add('on');
      say(pick(SAY[kind]), 2000);
      actTimer = setTimeout(function () {{
        room.classList.remove(ACT_CLASS[kind]);
        notes.classList.remove('on');
        goTo(HOME.x, HOME.z, 900).then(function () {{ busy = false; note('home'); }});
      }}, 2400);
    }});
  }}

  document.querySelectorAll('[data-act]').forEach(function (el) {{
    var sprite = el.querySelector('.sprite') || el;
    sprite.addEventListener('click', function () {{
      doAct(el.dataset.act, parseFloat(el.dataset.x), parseFloat(el.dataset.z));
    }});
  }});
  document.getElementById('window').addEventListener('click', function () {{ doAct('look', 290, 120); }});
  document.getElementById('foxhit').addEventListener('click', function () {{
    note('tap fox'); room.classList.add('bounce'); say(pick(SAY.idle), 1500);
    setTimeout(function () {{ room.classList.remove('bounce'); }}, 500);
  }});
  document.getElementById('blocksprite').addEventListener('click', function () {{
    note('tap block'); room.classList.add('bounce'); say(pick(SAY.idle), 1500);
    setTimeout(function () {{ room.classList.remove('bounce'); }}, 500);
  }});

  // 机位状态（调好后把这里的初始值写死）
  var CAM = {{ tilt: -32, yaw: -30, zoom: 0.85, top: 40 }};
  function applyCam() {{
    var w = document.querySelector('.world');
    w.style.transform = 'scale(' + CAM.zoom.toFixed(2) + ') rotateX(' + CAM.tilt + 'deg) rotateY(' + CAM.yaw + 'deg)'
      + ' translate3d(-{W // 2}px, {H // 2}px, -{D // 2}px)';
    w.style.top = CAM.top + '%';
  }}
  applyCam();

  // ===== 手指控制机位：单指拖动旋转、双指捏合缩放，松手记一行日志 =====
  (function () {{
    var stage = document.querySelector('.stage');
    var pts = {{}}, startDist = 0, startZoom = 1, moved = false, sx = 0, sy = 0;
    function count() {{ return Object.keys(pts).length; }}
    stage.addEventListener('pointerdown', function (e) {{
      pts[e.pointerId] = {{ x: e.clientX, y: e.clientY }};
      moved = false; sx = e.clientX; sy = e.clientY;
      if (count() === 2) {{
        var a = Object.values(pts);
        startDist = Math.hypot(a[0].x - a[1].x, a[0].y - a[1].y) || 1;
        startZoom = CAM.zoom;
      }}
      try {{ stage.setPointerCapture(e.pointerId); }} catch (err) {{}}
    }});
    stage.addEventListener('pointermove', function (e) {{
      if (!pts[e.pointerId]) return;
      var prev = pts[e.pointerId];
      var dx = e.clientX - prev.x, dy = e.clientY - prev.y;
      pts[e.pointerId] = {{ x: e.clientX, y: e.clientY }};
      if (Math.abs(e.clientX - sx) + Math.abs(e.clientY - sy) > 10) moved = true;
      if (count() >= 2) {{
        var a = Object.values(pts);
        var d = Math.hypot(a[0].x - a[1].x, a[0].y - a[1].y) || 1;
        CAM.zoom = Math.min(1.8, Math.max(0.4, Math.round(startZoom * d / startDist * 100) / 100));
        applyCam();
      }} else {{
        CAM.yaw = Math.round((CAM.yaw + dx * 0.16) * 10) / 10;
        CAM.tilt = Math.max(-70, Math.min(70, Math.round((CAM.tilt - dy * 0.14) * 10) / 10));
        applyCam();
      }}
    }});
    function up(e) {{
      if (!pts[e.pointerId]) return;
      delete pts[e.pointerId];
      if (count() === 0 && moved) note('cam tilt=' + CAM.tilt + ' yaw=' + CAM.yaw + ' zoom=' + CAM.zoom + ' top=' + CAM.top);
    }}
    stage.addEventListener('pointerup', up);
    stage.addEventListener('pointercancel', up);
    // 双击空白处：机位复位到默认
    var lastTap = 0;
    stage.addEventListener('click', function (e) {{
      if (e.target.closest('.item') || e.target.closest('.window')) return;
      var now = Date.now();
      if (now - lastTap < 320) {{
        CAM.tilt = -32; CAM.yaw = -30; CAM.zoom = 0.85; CAM.top = 40;
        applyCam();
        note('cam reset tilt=-32 yaw=-30 zoom=0.85 top=40');
      }}
      lastTap = now;
    }});
  }})();

  function setForm(f) {{
    room.dataset.form = f;
    document.getElementById('btn-block').classList.toggle('on', f === 'block');
    document.getElementById('btn-fox').classList.toggle('on', f === 'fox');
    [foxitem, blockitem].forEach(function (it) {{
      it.style.transition = 'none';
      it.style.transform = 'translate3d(' + HOME.x + 'px,0,' + HOME.z + 'px)';
      it.dataset.curx = HOME.x;
      setTimeout(function () {{ it.style.transition = ''; }}, 60);
    }});
    note('form=' + f);
  }}
  document.getElementById('btn-block').addEventListener('click', function () {{ setForm('block'); }});
  document.getElementById('btn-fox').addEventListener('click', function () {{ setForm('fox'); }});
  setForm('block');

  document.getElementById('gear').addEventListener('click', function () {{
    note('open settings');
    try {{ window.RoomBridge && RoomBridge.openSettings && RoomBridge.openSettings(); }}
    catch (e) {{ say('打不开设置：' + e.message, 1500); }}
  }});
  document.getElementById('close').addEventListener('click', function () {{
    if (window.RoomBridge && window.RoomBridge.close) window.RoomBridge.close();
    else say('（没有找到关闭桥）', 1200);
  }});

  (function blinkLoop() {{
    setTimeout(function () {{
      room.classList.add('blink');
      setTimeout(function () {{ room.classList.remove('blink'); }}, 110);
      if (Math.random() < 0.18) setTimeout(function () {{
        room.classList.add('blink');
        setTimeout(function () {{ room.classList.remove('blink'); }}, 100);
      }}, 230);
      blinkLoop();
    }}, 2600 + Math.random() * 4200);
  }})();

  note('loaded ' + innerWidth + 'x' + innerHeight);
  // 临时：把各个 3D 元素的屏幕投影框报出来（便于 adb 点击验证）
  setTimeout(function () {{
    var out = [];
    ['flooritem','fedge','redge','wbtop','wltop','aob','aol','aoc','rugitem','beditem','bowlitem','radioitem','blockitem','window'].forEach(function (id) {{
      var el = document.getElementById(id); if (!el) return;
      var t = el.querySelector('.sprite') || el.querySelector('.rugface') || el;
      var b = t.getBoundingClientRect();
      out.push(id + '=' + Math.round(b.left) + ',' + Math.round(b.top) + ',' + Math.round(b.width) + 'x' + Math.round(b.height));
    }});
    note('rects ' + out.join(' | '));
  }}, 800);
  setTimeout(function () {{ say('欢迎来小屋～', 2000); }}, 600);
</script>
</body>
</html>
"""


def main():
    html = build()
    if "--stdout" in sys.argv:
        print(html)
        return 0
    dst = os.path.join(ASSETS, "room.html")
    with open(dst, "w") as f:
        f.write(html)
    print("写入", dst, os.path.getsize(dst), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
