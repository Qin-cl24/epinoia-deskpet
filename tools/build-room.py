#!/usr/bin/env python3
"""生成小屋页面 assets/room.html（占位美术，全部用 CSS 画）

图层和坐标不算第二份：直接读 assets/fox/_layers.json（fox-build-from-psd.py 生成的那份），
所以主人重导画稿之后，跑一次这个脚本 + 重新编译，小屋里的狐狐就跟着更新了。

用法：
    python3 tools/build-room.py            # 写 app/src/main/assets/room.html
    python3 tools/build-room.py --stdout   # 只打印
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
ASSETS = os.path.join(PROJ, "app", "src", "main", "assets")
LAYERS = os.path.join(ASSETS, "fox", "_layers.json")

# 绘制顺序（从下到上），和 pet.html 的 DOM 顺序一致
ORDER = ["tail-outer", "tail-inner", "shoes", "pants", "pants-front", "leg-detail-L", "leg-detail-R",
         "hair-back", "neck-hands", "top", "sleeves", "ear-L", "fur-under-ear-L", "head", "part25",
         "mouth", "eye-white-R", "eye-white-L", "iris-R", "iris-L", "lash-R-upper", "lash-L-lower",
         "lash-L-upper", "eyelid-R", "brow-C", "brow-L", "brow-R", "lash-L-extra", "ear-R", "bangs",
         "fur-under-ear-R", "hair-highlight", "hair-tuft", "ahoge"]
EYE_GROUP = {
    "R": ["eye-white-R", "iris-R", "lash-R-upper", "brow-R", "eyelid-R"],
    "L": ["eye-white-L", "iris-L", "lash-L-upper", "lash-L-lower", "lash-L-extra"],
}


def build():
    meta = json.load(open(LAYERS))
    lay = meta["layers"]
    order = [n for n in ORDER if n in lay]

    # 几何 + 眨眼枢轴（眼白底边中点）
    geo, dom = [], []
    for n in order:
        l, t, w, h = lay[n]["app"]
        geo.append(f'    .fx-{n} {{ left:{l}px; top:{t}px; width:{w}px; height:{h}px; }}')
        dom.append(f'    <img class="fx fx-{n}" src="fox/{n}.png" alt="">')

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
            blink.append(f"    .fx-{n} {{ transform-origin: {ax - l}px {ay - t}px; transition: transform .09s ease-out; }}")
    blink_sel = ",\n    ".join(f".pet-room.blink .fx-{n}" for s in EYE_GROUP for n in EYE_GROUP[s] if n in lay)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>狐狐的小屋</title>
<style>
  * {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
  html, body {{ margin:0; height:100%; overflow:hidden; font-family: system-ui, sans-serif;
    background:#f6e3cf; user-select:none; }}

  /* ===== 房间：墙 + 地板 + 窗 ===== */
  .room {{ position:fixed; inset:0; overflow:hidden; }}
  /* 墙（斜俯视）：两面墙在 56% 处有个转角，踢脚线跟着墙歪一点 */
  .wall {{ position:absolute; left:0; right:0; top:0; bottom:44%;
    background:
      radial-gradient(circle at 20% 30%, rgba(255,255,255,.5) 0 3px, transparent 3px) 0 0/52px 52px,
      radial-gradient(circle at 70% 70%, rgba(255,255,255,.4) 0 3px, transparent 3px) 0 0/52px 52px,
      linear-gradient(170deg, #f9ecd9, #ecd3b6); }}
  .wall .corner {{ position:absolute; left:56%; top:0; bottom:0; width:3px;
    background:linear-gradient(rgba(120,85,55,.10), rgba(120,85,55,.28)); }}
  .wall .base-l {{ position:absolute; left:0; width:56%; bottom:0; height:11px; background:#c48b5c;
    transform: skewY(-2.4deg); transform-origin: bottom right; }}
  .wall .base-r {{ position:absolute; left:56%; right:0; bottom:0; height:11px; background:#b87f51;
    transform: skewY(2.4deg); transform-origin: bottom left; }}
  /* 地面（斜俯视）：后窄前宽的梯形，砖块纹路，越远越暗 */
  .floor {{ position:absolute; left:0; right:0; bottom:0; height:56%;
    clip-path: polygon(17% 0, 83% 0, 100% 100%, 0 100%);
    background:
      repeating-linear-gradient(90deg, rgba(85,52,28,.16) 0 2px, transparent 2px 40px),
      repeating-linear-gradient(0deg, rgba(85,52,28,.13) 0 2px, transparent 2px 30px),
      linear-gradient(#cf9a6a, #e8c298 62%, #f0d0aa); }}
  .floor .haze {{ position:absolute; inset:0; background: linear-gradient(rgba(70,40,18,.32), rgba(70,40,18,0) 42%); }}

  .skirting {{ position:absolute; left:0; right:0; bottom:44%; height:9px; background:#b5764a;
    box-shadow: 0 2px 6px rgba(0,0,0,.18); }}
  /* 墙脚环境阴影（AO）：贴墙那条暗，让墙和地有转角感 */
  .ao {{ position:absolute; left:0; right:0; bottom:44%; height:34px; pointer-events:none;
    background: linear-gradient(rgba(70,40,20,0), rgba(70,40,20,.22)); }}
  /* 窗口方向的光 + 四角暗角：给整个房间一点体积感 */
  .light {{ position:absolute; inset:0; pointer-events:none;
    background: radial-gradient(ellipse at 78% 18%, rgba(255,246,220,.55), rgba(255,246,220,0) 45%); }}
  .vignette {{ position:absolute; inset:0; pointer-events:none;
    background: radial-gradient(ellipse at 50% 55%, rgba(0,0,0,0) 55%, rgba(60,35,15,.20)); }}

  .window {{ position:absolute; right:9%; top:11%; width:30%; height:22%; border-radius:10px;
    transform: skewY(2.4deg);
    background: linear-gradient(#bfe3f7, #e7f6ff); border:7px solid #d9b08c;
    box-shadow: 0 6px 14px rgba(0,0,0,.14), inset 0 0 0 2px rgba(255,255,255,.6); overflow:hidden; }}
  .window::before {{ content:''; position:absolute; left:50%; top:0; bottom:0; width:6px; margin-left:-3px;
    background:#d9b08c; }}
  .window::after {{ content:''; position:absolute; top:50%; left:0; right:0; height:6px; margin-top:-3px;
    background:#d9b08c; }}
  .sun {{ position:absolute; right:12px; top:12px; width:34px; height:34px; border-radius:50%;
    background:radial-gradient(circle, #ffe680, #ffcf40); box-shadow:0 0 18px rgba(255,214,64,.8); }}
  .cloud {{ position:absolute; left:10px; top:16px; width:52px; height:16px; border-radius:20px;
    background:rgba(255,255,255,.9); box-shadow:14px -8px 0 -2px rgba(255,255,255,.9); animation: drift 9s ease-in-out infinite; }}
  @keyframes drift {{ 0%,100% {{ transform: translateX(0); }} 50% {{ transform: translateX(26px); }} }}

  /* ===== 家具 ===== */
  /* 床（2026-11-03 第二版）：床头板 + 床架 + 床垫 + 被子（带折边）+ 枕头 + 两条床腿 */
  .bed {{ position:absolute; left:7%; bottom:36%; width:30%; height:20%; cursor:pointer;
    filter: drop-shadow(0 10px 14px rgba(90,55,30,.35)); }}
  .bed .headboard {{ position:absolute; left:0; bottom:6%; width:14%; height:104%; border-radius:10px 6px 4px 10px;
    background:linear-gradient(100deg, #d0a273, #a9794f); box-shadow:inset 0 3px 0 rgba(255,255,255,.28); }}
  .bed .frame {{ position:absolute; left:10%; bottom:14%; width:90%; height:26%; border-radius:6px;
    background:linear-gradient(#b98a5e, #9c6f47); }}
  .bed .mattress {{ position:absolute; left:12%; bottom:34%; width:88%; height:28%; border-radius:8px;
    background:linear-gradient(#ffffff, #f0ecfb); box-shadow:0 3px 8px rgba(0,0,0,.14); }}
  .bed .pillow {{ position:absolute; left:16%; bottom:46%; width:23%; height:22%; border-radius:8px;
    background:linear-gradient(#fff, #f5f2fe); box-shadow:0 2px 5px rgba(0,0,0,.12); }}
  .bed .blanket {{ position:absolute; left:38%; bottom:36%; width:62%; height:34%; border-radius:6px 9px 9px 6px;
    background:linear-gradient(#bcaaf2, #9d86e8); box-shadow:inset 0 -4px 0 rgba(0,0,0,.10); }}
  .bed .blanket::after {{ content:''; position:absolute; left:0; right:0; top:26%; height:3px;
    background:rgba(255,255,255,.5); box-shadow:0 9px 0 rgba(255,255,255,.32); }}
  .bedleg {{ position:absolute; bottom:2%; width:8%; height:14%; background:#8f6440; border-radius:0 0 4px 4px; }}
  .bedleg.l {{ left:16%; }} .bedleg.r {{ right:4%; }}

  .bowl {{ position:absolute; left:9%; bottom:9%; width:84px; height:40px;
    filter: drop-shadow(0 8px 10px rgba(90,55,30,.38)); border-radius:0 0 36px 36px;
    background:linear-gradient(#f0f0f0, #cfcfcf); box-shadow:0 6px 12px rgba(0,0,0,.2);
    border-top:6px solid #ffb457; cursor:pointer; }}
  .bowl .food {{ position:absolute; left:8px; right:8px; top:-8px; height:12px; border-radius:10px;
    background:radial-gradient(circle at 30% 50%, #ffd08a 0 4px, transparent 4px),
               radial-gradient(circle at 65% 50%, #ffc46b 0 4px, transparent 4px), #ffb457; }}

  .radio {{ position:absolute; right:9%; bottom:10%; width:74px; height:54px;
    filter: drop-shadow(0 8px 10px rgba(90,55,30,.42)); border-radius:8px;
    background:linear-gradient(#8d6e63, #6d4c41); box-shadow:0 6px 12px rgba(0,0,0,.25); cursor:pointer; }}
  .radio::before {{ content:''; position:absolute; left:8px; top:8px; width:26px; height:26px; border-radius:50%;
    background:radial-gradient(circle at 50% 50%, #fff 0 30%, #bdbdbd 32% 60%, #8d8d8d 62%); }}
  .radio::after {{ content:''; position:absolute; right:10px; top:12px; width:12px; height:12px; border-radius:50%;
    background:#ffd54f; box-shadow:0 16px 0 -2px #ffd54f; }}
  .radio .side {{ position:absolute; right:0; top:0; bottom:0; width:12px; border-radius:0 8px 8px 0;
    background:linear-gradient(90deg, rgba(0,0,0,0), rgba(0,0,0,.35)); }}
  .bowl .side {{ position:absolute; right:0; top:0; bottom:0; width:18px; border-radius:0 0 30px 0;
    background:linear-gradient(90deg, rgba(0,0,0,0), rgba(0,0,0,.22)); }}
  .notes {{ position:absolute; right:5%; bottom:20%; font-size:16px; opacity:0; transition:opacity .3s; }}
  .notes.on {{ opacity:1; animation: floatUp 1.4s ease-in-out infinite; }}
  @keyframes floatUp {{ 0% {{ transform: translate(0,0); opacity:0; }} 40% {{ opacity:1; }} 100% {{ transform: translate(10px,-26px); opacity:0; }} }}

  /* 地毯：铺在底部、比家具先画，碗和收音机就是「放在毯子上」，不会被毯子压住 */
  .rug {{ position:absolute; left:50%; bottom:6%; width:74%; height:15%; margin-left:-37%; border-radius:50%;
    background:radial-gradient(ellipse at 50% 40%, #ffe9c6, #f0c88b);
    box-shadow: inset 0 0 0 6px rgba(255,255,255,.5), 0 6px 18px rgba(0,0,0,.08); }}


  /* ===== 方块形态（2026-11-03 加，默认用它测交互）=====
     和桌面上那个方块小人同一套画法：56x36 的橙色方块 + 竖眼睛 + 短手 + 四条腿。 */
  .blockwrap {{ position:absolute; left:50%; bottom:14%; width:0; height:0; }}
  .blockshadow {{ position:absolute; left:0; bottom:-4px; width:150px; height:26px; margin-left:-75px;
    border-radius:50%; background:rgba(80,45,20,.32); filter:blur(7px); }}
  .blockpet {{ position:absolute; left:0; bottom:0; transform: translateX(-50%) scale(2.0); transform-origin: bottom center;
    transition: transform .25s ease; width:72px; height:50px; }}
  .blockpet .body {{ position:relative; width:56px; height:36px; margin:4px auto 0; border-radius:4px;
    background:#e67e22; box-shadow: inset 0 2px 0 rgba(255,255,255,.22), inset 0 -3px 0 rgba(0,0,0,.10); }}
  .blockpet .eye {{ position:absolute; width:5px; height:10px; background:#000; top:9px; border-radius:2px;
    transition: height .1s; }}
  .blockpet .eye-left {{ left:12px; }} .blockpet .eye-right {{ right:12px; }}
  .pet-room.blink .blockpet .eye {{ height:2px; }}
  .blockpet .arm {{ position:absolute; width:10px; height:10px; top:12px; background:#e67e22;
    background-image: linear-gradient(180deg, rgba(255,255,255,.20), rgba(255,255,255,.05)); }}
  .blockpet .arm-left {{ left:-10px; }} .blockpet .arm-right {{ right:-10px; }}
  .blockpet .leg {{ position:absolute; width:5px; height:10px; bottom:-10px;
    background: linear-gradient(180deg, #e67e22 0%, #d35400 58%); }}
  .blockpet .leg-l1 {{ left:8px; }} .blockpet .leg-l2 {{ left:17px; }}
  .blockpet .leg-r1 {{ right:8px; }} .blockpet .leg-r2 {{ right:17px; }}
  .blockpet .body {{ animation: blockIdle 2.6s ease-in-out infinite; }}
  @keyframes blockIdle {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-2px); }} }}
  .walking .blockpet .body {{ animation: blockWalk .45s ease-in-out infinite; }}
  @keyframes blockWalk {{ 0%,100% {{ transform: rotate(-4deg); }} 50% {{ transform: rotate(4deg); }} }}
  .room.act-sleep .blockpet {{ transform: translateX(-50%) scale(2.0) rotate(-12deg) translateY(14px); }}
  .room.act-eat .blockpet .body {{ animation: blockEat .5s ease-in-out infinite; }}
  @keyframes blockEat {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(4px) scaleY(.97); }} }}
  .room.act-look .blockpet {{ transform: translateX(-50%) scale(2.0) translateY(-6px); }}
  .room.act-dance .blockpet {{ animation: blockDance .5s ease-in-out infinite; }}
  @keyframes blockDance {{ 0%,100% {{ transform: translateX(-50%) scale(2.0) rotate(-7deg); }}
                           50% {{ transform: translateX(-50%) scale(2.0) rotate(7deg) translateY(-4px); }} }}
  .room.bounce .blockpet {{ animation: blockHop .45s ease-out; }}
  @keyframes blockHop {{ 0%,100% {{ transform: translateX(-50%) scale(2.0) translateY(0); }}
                         40% {{ transform: translateX(-50%) scale(2.0) translateY(-16px); }} }}
  /* 形态切换：默认方块，切到狐狐才显示那 34 层 */
  .foxwrap {{ display:none; }}
  .room[data-form="fox"] .foxwrap {{ display:block; }}
  .room[data-form="fox"] .blockwrap {{ display:none; }}
  .formbtn {{ border:none; border-radius:14px; padding:4px 10px; font-size:12px; cursor:pointer;
    background:#f0dcc8; color:#6b5341; }}
  .formbtn.on {{ background:#e6a86b; color:#fff; }}

  /* ===== 狐狐（图层来自 _layers.json）===== */
  .foxwrap {{ position:absolute; left:50%; bottom:12%; width:0; height:0; }}
  .fox {{ position:absolute; left:0; bottom:0; width:543px; height:626px;
    transform: translateX(-50%) scale(var(--foxs, .30)); transform-origin: bottom center;
    transition: transform .25s ease; }}
  .fox.flip {{ transform: translateX(-50%) scale(var(--foxs, .30)) scaleX(-1); }}
  .fox-inner {{ position:absolute; inset:0; animation: idle 3.2s ease-in-out infinite; pointer-events:none; }}  /* 不然它盖住 .fox-hit，点不到狐狐 */
  @keyframes idle {{ 0%,100% {{ transform: translateY(0) scaleY(1); }} 50% {{ transform: translateY(-2px) scaleY(.99); }} }}
  .fox img.fx {{ position:absolute; display:block; pointer-events:none; }}   /* 透明区域不该吃点击 */
  .fox .fox-hit {{ position:absolute; left:27%; top:18%; width:48%; height:71%; cursor:pointer;
    border-radius:45% 45% 40% 40%; }}
{chr(10).join(geo)}

  /* 走 / 各动作 */
  .walking .fox-inner {{ animation: sway .5s ease-in-out infinite; }}
  @keyframes sway {{ 0%,100% {{ transform: rotate(-3deg); }} 50% {{ transform: rotate(3deg); }} }}
  .act-sleep .fox-inner {{ animation: lie 3s ease-in-out infinite; }}
  @keyframes lie {{ 0%,100% {{ transform: rotate(-9deg) translateY(10px) scaleY(.92); }}
                    50% {{ transform: rotate(-11deg) translateY(11px) scaleY(.9); }} }}
  .act-eat .fox-inner {{ animation: chew .6s ease-in-out infinite; }}
  @keyframes chew {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(3px) scaleY(.98); }} }}
  .act-look .fox-inner {{ animation: lookout 2.4s ease-in-out infinite; }}
  @keyframes lookout {{ 0%,100% {{ transform: translateY(0) rotate(0); }} 50% {{ transform: translateY(-4px) rotate(2deg); }} }}
  .act-dance .fox-inner {{ animation: dance .55s ease-in-out infinite; }}
  @keyframes dance {{ 0%,100% {{ transform: rotate(-6deg) translateY(0); }}
                      50% {{ transform: rotate(6deg) translateY(-3px); }} }}
  .pet-room.bounce .fox-inner {{ animation: hop .45s ease-out; }}
  @keyframes hop {{ 0%,100% {{ transform: translateY(0); }} 40% {{ transform: translateY(-14px) scaleY(1.04); }} }}

  /* 眨眼：眼白/虹膜/睫毛收成一条线（枢轴=眼白底边中点）*/
{chr(10).join(blink)}
  {blink_sel} {{ transform: scaleY(.12); }}

  .zzz {{ position:absolute; left:56%; top:8%; font-size:18px; opacity:0; }}
  .act-sleep .zzz {{ opacity:1; animation: zfloat 2.2s ease-in-out infinite; }}
  @keyframes zfloat {{ 0% {{ transform: translate(0,0) scale(.8); opacity:.3; }}
                       50% {{ transform: translate(10px,-16px) scale(1); opacity:1; }}
                       100% {{ transform: translate(20px,-32px) scale(.9); opacity:0; }} }}

  /* ===== 说话气泡 ===== */
  .bubble {{ position:absolute; left:50%; bottom:calc(8% + var(--bubbleup, 150px)); transform: translateX(-50%) scale(.9);
    background:#fff; color:#5a4636; padding:8px 14px; border-radius:16px; font-size:15px;
    box-shadow:0 6px 16px rgba(0,0,0,.16); opacity:0; transition: opacity .18s ease, transform .18s ease;
    pointer-events:none; white-space:nowrap; }}
  .bubble.on {{ opacity:1; transform: translateX(-50%) scale(1); }}

  /* ===== 顶栏 ===== */
  .top {{ position:absolute; left:0; right:0; top:0; height:52px; display:flex; align-items:center;
    padding:0 12px; gap:10px; background:linear-gradient(rgba(255,248,240,.92), rgba(255,248,240,0)); }}
  .title {{ font-size:16px; font-weight:600; color:#6b5341; }}
  .hint {{ font-size:12px; color:#a58b74; margin-left:auto; }}
  .close {{ width:36px; height:36px; border:none; border-radius:50%; background:#f0dcc8; color:#6b5341;
    font-size:18px; line-height:1; cursor:pointer; }}
</style>
</head>
<body>
<script>console.log('BOOT ' + innerWidth + 'x' + innerHeight + ' RoomBridge=' + (typeof window.RoomBridge));</script>
<div class="room pet-room" id="room" data-form="block">
  <div class="wall"><span class="corner"></span><span class="base-l"></span><span class="base-r"></span></div>
  <div class="skirting"></div>
  <div class="floor"><span class="plane"></span><span class="haze"></span></div>
  <div class="rug"></div>

  <div class="ao"></div>
  <div class="light"></div>
  <div class="vignette"></div>
  <div class="window"><span class="sun"></span><span class="cloud"></span></div>

  <div class="bed" data-act="sleep" data-x="14">
    <span class="headboard"></span><span class="frame"></span><span class="mattress"></span>
    <span class="blanket"></span><span class="pillow"></span>
    <span class="bedleg l"></span><span class="bedleg r"></span>
  </div>
  <div class="bowl" data-act="eat" data-x="18"><span class="food"></span><span class="side"></span></div>
  <div class="radio" data-act="dance" data-x="82"><span class="side"></span></div>
  <div class="notes">🎵</div>

  <div class="blockwrap" id="blockwrap">
    <span class="blockshadow"></span>
    <div class="blockpet">
      <div class="body">
        <div class="eye eye-left"></div><div class="eye eye-right"></div>
        <div class="arm arm-left"></div><div class="arm arm-right"></div>
        <div class="leg leg-l1"></div><div class="leg leg-l2"></div>
        <div class="leg leg-r1"></div><div class="leg leg-r2"></div>
      </div>
    </div>
  </div>
  <div class="foxwrap" id="foxwrap">
    <div class="fox" id="fox">
      <div class="fox-hit" id="foxhit"></div>
      <div class="fox-inner">
{chr(10).join(dom)}
      </div>
      <span class="zzz">z z Z</span>
    </div>
  </div>

  <div class="bubble" id="bubble"></div>

  <div class="top">
    <span class="title">🏠 狐狐的小屋</span>
    <button class="formbtn on" id="btn-block">🐣 方块</button>
    <button class="formbtn" id="btn-fox">🦊 狐狐</button>
    <span class="hint">点家具试试</span>
    <button class="close" id="gear" title="设置">⚙️</button>
    <button class="close" id="close">✕</button>
  </div>
</div>
<script>
  console.log('MAIN start');
  window.onerror = function (m, f, l) {{ console.log('JSERR ' + m + ' @' + l); }};
  try {{
  var room = document.getElementById('room');
  var foxwrap = document.getElementById('foxwrap');
  var blockwrap = document.getElementById('blockwrap');
  function activeWrap() {{ return room.dataset.form === 'fox' ? foxwrap : blockwrap; }}
  var wrap = blockwrap;   // 默认方块形态
  var fox = document.getElementById('fox');
  var bubble = document.getElementById('bubble');
  var notes = document.querySelector('.notes');
  var busy = false;

  var SAY = {{
    sleep: ['有点困…', '睡一会儿', '（抱着尾巴睡着）'],
    eat: ['好香！', '开动啦', '呼噜呼噜～'],
    look: ['外面好亮', '云飘过去了', '有人路过呢'],
    dance: ['一起听！', '这段好听', '啦啦啦～'],
    idle: ['在屋里转转', '今天待在小屋', '要不要一起玩']
  }};
  function say(t, ms) {{
    bubble.textContent = t;
    bubble.classList.add('on');
    clearTimeout(say._t);
    say._t = setTimeout(function() {{ bubble.classList.remove('on'); }}, ms || 1800);
  }}
  function pick(a) {{ return a[Math.floor(Math.random() * a.length)]; }}

  // 走：用 transform 平移，顺便按方向翻转（和桌面上「朝向跟随移动」一致）
  function goTo(xPercent, ms) {{
    var target = (xPercent - 50) * 0.62;      // 百分比 → vw 偏移，0.62 是手感系数
    var now = wrap.dataset.x ? parseFloat(wrap.dataset.x) : 0;
    if (room.dataset.form === 'fox') fox.classList.toggle('flip', target < now);
    wrap.dataset.x = target;
    wrap.style.transition = 'transform ' + ms + 'ms ease-in-out';
    wrap.style.transform = 'translateX(' + target + 'vw)';
    fox.classList.add('walking');
    return new Promise(function(res) {{
      setTimeout(function() {{ fox.classList.remove('walking'); res(); }}, ms);
    }});
  }}
  function backHome(ms) {{ return goTo(50, ms); }}

  var ACT_CLASS = {{ sleep: 'act-sleep', eat: 'act-eat', look: 'act-look', dance: 'act-dance' }};

  function note(s) {{ try {{ window.RoomBridge && RoomBridge.note(s); }} catch (e) {{}} }}
  var actTimer = null;
  function doAct(kind, xPercent) {{
    note('click act=' + kind + ' target=' + xPercent + ' busy=' + busy);
    // 允许打断：清掉上一个动作的计时器，直接开始新的
    clearTimeout(actTimer);
    room.classList.remove('act-sleep', 'act-eat', 'act-look', 'act-dance');
    notes.classList.remove('on');
    busy = true;
    room.classList.remove('act-sleep', 'act-eat', 'act-look', 'act-dance');
    say({{ sleep: '去躺一下', eat: '肚子饿了', look: '去看看窗外', dance: '放首歌吧' }}[kind] || '', 1200);
    goTo(xPercent, 900).then(function() {{
      note('arrived act=' + kind + ' dx=' + (wrap.dataset.x || 0));
      room.classList.add(ACT_CLASS[kind]);
      if (kind === 'dance') notes.classList.add('on');
      say(pick(SAY[kind]), 2200);
      actTimer = setTimeout(function() {{
        room.classList.remove(ACT_CLASS[kind]);
        notes.classList.remove('on');
        backHome(900).then(function() {{ busy = false; note('home'); }});
      }}, 2600);
    }});
  }}

  document.querySelectorAll('[data-act]').forEach(function(el) {{
    el.addEventListener('click', function() {{ doAct(el.dataset.act, parseFloat(el.dataset.x)); }});
  }});
  // 窗台也能点
  document.querySelector('.window').addEventListener('click', function() {{ doAct('look', 66); }});
  // 点狐狐：跳一下
  document.getElementById('foxhit').addEventListener('click', function() {{ note('tap fox');
    room.classList.add('bounce');
    say(pick(SAY.idle), 1500);
    setTimeout(function() {{ room.classList.remove('bounce'); }}, 500);
  }});
  document.getElementById('gear').addEventListener('click', function() {{
    note('open settings');
    try {{ window.RoomBridge && RoomBridge.openSettings && RoomBridge.openSettings(); }}
    catch (e) {{ say('打不开设置：' + e.message, 1500); }}
  }});
  document.getElementById('close').addEventListener('click', function() {{
    if (window.RoomBridge && window.RoomBridge.close) window.RoomBridge.close();
    else say('（没有找到关闭桥）', 1200);
  }});

  // 形态切换：默认方块（先拿它测交互），切到狐狐才显示那 34 层
  function setForm(f) {{
    room.dataset.form = f;
    document.getElementById('btn-block').classList.toggle('on', f === 'block');
    document.getElementById('btn-fox').classList.toggle('on', f === 'fox');
    // 换形态回到中间，免得旧偏移留在另一个容器上
    [foxwrap, blockwrap].forEach(function (w) {{
      w.style.transition = 'none'; w.style.transform = 'translateX(0)'; w.dataset.x = 0;
      setTimeout(function () {{ w.style.transition = ''; }}, 50);
    }});
    note('form=' + f);
  }}
  document.getElementById('btn-block').addEventListener('click', function () {{ setForm('block'); }});
  document.getElementById('btn-fox').addEventListener('click', function () {{ setForm('fox'); }});
  setForm('block');

  // 点方块也能逗它
  document.querySelector('.blockpet .body').addEventListener('click', function () {{
    note('tap block');
    room.classList.add('bounce');
    say(pick(SAY.idle), 1500);
    setTimeout(function () {{ room.classList.remove('bounce'); }}, 500);
  }});

  // 眨眼：随机间隔，偶尔连眨
  (function blinkLoop() {{
    setTimeout(function() {{
      room.classList.add('blink');
      setTimeout(function() {{ room.classList.remove('blink'); }}, 110);
      if (Math.random() < 0.18) setTimeout(function() {{
        room.classList.add('blink');
        setTimeout(function() {{ room.classList.remove('blink'); }}, 100);
      }}, 230);
      blinkLoop();
    }}, 2600 + Math.random() * 4200);
  }})();

  note('loaded size=' + innerWidth + 'x' + innerHeight);
  setTimeout(function() {{ say('欢迎来小屋～', 2000); }}, 600);
  }} catch (e) {{ console.log('FATAL ' + e.message + ' @ ' + (e.stack || '').slice(0,300)); }}
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
