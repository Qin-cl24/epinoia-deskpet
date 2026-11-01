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
  .wall {{ position:absolute; left:0; right:0; top:0; bottom:34%;
    background:
      radial-gradient(circle at 20% 30%, rgba(255,255,255,.55) 0 3px, transparent 3px) 0 0/46px 46px,
      radial-gradient(circle at 70% 70%, rgba(255,255,255,.45) 0 3px, transparent 3px) 0 0/46px 46px,
      linear-gradient(#f7e7d3, #eed6bb); }}
  .floor {{ position:absolute; left:0; right:0; bottom:0; height:34%;
    background:
      repeating-linear-gradient(90deg, rgba(0,0,0,.05) 0 1px, transparent 1px 42px),
      repeating-linear-gradient(0deg, rgba(0,0,0,.045) 0 1px, transparent 1px 30px),
      linear-gradient(#d8a677, #c2885b); }}
  .skirting {{ position:absolute; left:0; right:0; bottom:34%; height:9px; background:#b5764a;
    box-shadow: 0 2px 6px rgba(0,0,0,.18); }}

  .window {{ position:absolute; right:8%; top:9%; width:34%; height:26%; border-radius:10px;
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
  .bed {{ position:absolute; left:6%; bottom:34%; width:24%; height:15%; border-radius:14px 14px 6px 6px;
    background:linear-gradient(#f3f0ff, #dcd6f7); box-shadow:0 8px 18px rgba(0,0,0,.18), inset 0 -6px 0 rgba(0,0,0,.06);
    cursor:pointer; }}
  .bed::before {{ content:''; position:absolute; left:5%; top:14%; width:30%; height:44%; border-radius:10px;
    background:linear-gradient(#fff, #f1eefc); box-shadow:0 2px 4px rgba(0,0,0,.12); }}
  .bed::after {{ content:'🛏️'; position:absolute; right:8px; top:6px; font-size:16px; opacity:.55; }}
  .bedleg {{ position:absolute; bottom:-8px; width:8px; height:12px; background:#c9a074; border-radius:2px; }}
  .bedleg.l {{ left:12%; }} .bedleg.r {{ right:12%; }}

  .bowl {{ position:absolute; left:34%; bottom:26%; width:70px; height:34px; border-radius:0 0 36px 36px;
    background:linear-gradient(#f0f0f0, #cfcfcf); box-shadow:0 6px 12px rgba(0,0,0,.2);
    border-top:6px solid #ffb457; cursor:pointer; }}
  .bowl .food {{ position:absolute; left:8px; right:8px; top:-8px; height:12px; border-radius:10px;
    background:radial-gradient(circle at 30% 50%, #ffd08a 0 4px, transparent 4px),
               radial-gradient(circle at 65% 50%, #ffc46b 0 4px, transparent 4px), #ffb457; }}

  .radio {{ position:absolute; right:30%; bottom:26%; width:64px; height:46px; border-radius:8px;
    background:linear-gradient(#8d6e63, #6d4c41); box-shadow:0 6px 12px rgba(0,0,0,.25); cursor:pointer; }}
  .radio::before {{ content:''; position:absolute; left:8px; top:8px; width:26px; height:26px; border-radius:50%;
    background:radial-gradient(circle at 50% 50%, #fff 0 30%, #bdbdbd 32% 60%, #8d8d8d 62%); }}
  .radio::after {{ content:''; position:absolute; right:10px; top:12px; width:12px; height:12px; border-radius:50%;
    background:#ffd54f; box-shadow:0 16px 0 -2px #ffd54f; }}
  .notes {{ position:absolute; right:26%; bottom:38%; font-size:16px; opacity:0; transition:opacity .3s; }}
  .notes.on {{ opacity:1; animation: floatUp 1.4s ease-in-out infinite; }}
  @keyframes floatUp {{ 0% {{ transform: translate(0,0); opacity:0; }} 40% {{ opacity:1; }} 100% {{ transform: translate(10px,-26px); opacity:0; }} }}

  .rug {{ position:absolute; left:50%; bottom:6%; width:52%; height:13%; margin-left:-26%; border-radius:50%;
    background:radial-gradient(ellipse at 50% 40%, #ffe3b8, #f3c98d); opacity:.85;
    box-shadow: inset 0 0 0 5px rgba(255,255,255,.45); }}

  /* ===== 狐狐（图层来自 _layers.json）===== */
  .foxwrap {{ position:absolute; left:50%; bottom:8%; width:0; height:0; }}
  .fox {{ position:absolute; left:0; bottom:0; width:543px; height:626px;
    transform: translateX(-50%) scale(var(--foxs, .52)); transform-origin: bottom center;
    transition: transform .25s ease; }}
  .fox.flip {{ transform: translateX(-50%) scale(var(--foxs, .52)) scaleX(-1); }}
  .fox-inner {{ position:absolute; inset:0; animation: idle 3.2s ease-in-out infinite; }}
  @keyframes idle {{ 0%,100% {{ transform: translateY(0) scaleY(1); }} 50% {{ transform: translateY(-2px) scaleY(.99); }} }}
  .fox img.fx {{ position:absolute; display:block; }}
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
  .bubble {{ position:absolute; left:50%; bottom:calc(8% + var(--bubbleup, 320px)); transform: translateX(-50%) scale(.9);
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
<div class="room pet-room" id="room">
  <div class="wall"></div>
  <div class="skirting"></div>
  <div class="floor"></div>

  <div class="window"><span class="sun"></span><span class="cloud"></span></div>

  <div class="bed" data-act="sleep" data-x="20"><span class="bedleg l"></span><span class="bedleg r"></span></div>
  <div class="bowl" data-act="eat" data-x="42"><span class="food"></span></div>
  <div class="radio" data-act="dance" data-x="62"></div>
  <div class="notes">🎵</div>
  <div class="rug"></div>

  <div class="foxwrap" id="foxwrap">
    <div class="fox" id="fox">
      <div class="fox-inner">
{chr(10).join(dom)}
      </div>
      <span class="zzz">z z Z</span>
    </div>
  </div>

  <div class="bubble" id="bubble"></div>

  <div class="top">
    <span class="title">🏠 狐狐的小屋</span>
    <span class="hint">点床 / 饭碗 / 收音机 / 窗台试试</span>
    <button class="close" id="close">✕</button>
  </div>
</div>
<script>
  var room = document.getElementById('room');
  var wrap = document.getElementById('foxwrap');
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
    fox.classList.toggle('flip', target < now);
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

  function doAct(kind, xPercent) {{
    if (busy) return;
    busy = true;
    room.classList.remove('act-sleep', 'act-eat', 'act-look', 'act-dance');
    say({{ sleep: '去躺一下', eat: '肚子饿了', look: '去看看窗外', dance: '放首歌吧' }}[kind] || '', 1200);
    goTo(xPercent, 900).then(function() {{
      room.classList.add(ACT_CLASS[kind]);
      if (kind === 'dance') notes.classList.add('on');
      say(pick(SAY[kind]), 2200);
      setTimeout(function() {{
        room.classList.remove(ACT_CLASS[kind]);
        notes.classList.remove('on');
        backHome(900).then(function() {{ busy = false; }});
      }}, 2600);
    }});
  }}

  document.querySelectorAll('[data-act]').forEach(function(el) {{
    el.addEventListener('click', function() {{ doAct(el.dataset.act, parseFloat(el.dataset.x)); }});
  }});
  // 窗台也能点
  document.querySelector('.window').addEventListener('click', function() {{ doAct('look', 66); }});
  // 点狐狐：跳一下
  fox.addEventListener('click', function() {{
    room.classList.add('bounce');
    say(pick(SAY.idle), 1500);
    setTimeout(function() {{ room.classList.remove('bounce'); }}, 500);
  }});
  document.getElementById('close').addEventListener('click', function() {{
    if (window.RoomBridge && window.RoomBridge.close) window.RoomBridge.close();
    else say('（没有找到关闭桥）', 1200);
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

  setTimeout(function() {{ say('欢迎来小屋～', 2000); }}, 600);
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
