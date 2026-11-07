#!/usr/bin/env python3
"""生成小屋页面 assets/room.html —— 真 3D 立方体（只留一个角的底面 + 左右两面）

按主人的描述：把小屋想成一个立方体，只保留**一个角的底面和左右两个面**，
其余面全部去掉 —— 就是一个开口的立体盒子，从斜上方看进去。

物理（2026-11-03 新增）：地板/床/碗/收音机/台灯挂 cannon-es 刚体，重力 9.8 m/s²，
开场家具从半空自然下落到地板停住。物理胶水层是独立的 assets/room-physics.js
（不塞进这个生成器，省掉给几百行 JS 转义大括号的麻烦）。
墙上装饰（挂画 / 挂钟 / 窗帘）是贴墙件，不参与自由落体。

实现：CSS 3D（perspective + preserve-3d）
    · .floor       底面：绕 X 轴转 90° 躺平，从角点向 +x / +z 铺开
    · .wall.back   后墙：z=0 平面，从角点向 +x 展开
    · .wall.left   左墙：x=0 平面，从角点向 +z 展开（绕 Y 轴 -90°）
    · 家具/角色都是「立在底面上的帖子」：translate3d(x,0,z) 定位，本体由 .sprite 立着不倒，
      影子是 rotateX(-90deg) 躺在地面上的椭圆
图层坐标不手写：读 assets/fox/_layers.json（fox-build-from-psd.py 生成），
主人重导画稿后跑一次本脚本 + 重新编译，小屋里的狐狐就跟着更新。

用法：
    python3 tools/build-room.py            # 写 app/src/main/assets/room.html
    python3 tools/build-room.py --stdout   # 只打印

⚠️ 改小屋的正确姿势：改这个脚本 → 跑一遍。room.html 是产物，别直接手改（会被覆盖）。
"""
import json
import math
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

# ===== 墙面装饰 + 台灯：纯字符串（不用在 f-string 里写双层大括号）=====
# 挂画/挂钟/窗帘都挂在墙上——它们是「贴墙件」，不参与物理自由落体；
# 台灯是地面家具，和床/碗/收音机一样挂刚体（见 room-physics.js）。
DECOR_CSS = """
  /* ===== 转到房间外时：墙和墙上挂件隐藏背面 =====
     yaw 放宽到 200° 后，镜头会绕到墙的另一侧；如果不隐藏背面，
     挂钟/挂画会以镜像形式出现（挂钟是特意 rotateY(180) 面向屋里的）。
     隐藏背面 = 转过去那面墙直接消失，露出屋里（像拆掉的玩具屋），不会出现反字。 */
  /* ⚠️ 只对「墙里的内容」隐藏背面，不能加上 .wall 本身：
     左墙元素的朝向本来就朝屋外（一直靠双面都能画混着用），
     一给墙本身加 backface hidden，整面左墙会直接消失（真机踩过）。*/
  .wall * { -webkit-backface-visibility: hidden; backface-visibility: hidden; }

  /* ===== 墙面装饰通用：.deco 里的每个面都绝对定位、用负 margin 把盒子中心对齐锚点 ===== */
  .deco { position:absolute; left:0; top:0; transform-style:preserve-3d; }
  .deco > * { position:absolute; left:0; top:0; }

  /* ===== 挂画（后墙左侧）：正面画框 + 顶面 + 右侧面，厚 10px ===== */
  .pic-front { width:104px; height:78px; margin:-39px 0 0 -52px; cursor:pointer; padding:6px;
    transform: translate3d(82px,74px,9px);
    background:linear-gradient(160deg,#c79a68,#a9784b); border-radius:3px;
    box-shadow:0 6px 14px rgba(60,35,15,.28); }
  .pic-front .art { position:absolute; inset:6px; display:block; border-radius:2px; overflow:hidden;
    background:linear-gradient(180deg,#bfe3f7 0 44%, #ffe6b8 44% 52%, #cfe6b8 52% 70%, #a8c98a 70% 100%); }
  .pic-front .art::before { content:''; position:absolute; left:66%; top:14%; width:20px; height:20px;
    border-radius:50%; background:radial-gradient(circle,#fff3b0,#ffd24d); box-shadow:0 0 12px rgba(255,214,64,.8); }
  .pic-front .art::after { content:''; position:absolute; left:-16%; bottom:-42%; width:150%; height:80%;
    border-radius:50%; background:linear-gradient(#9fc47f,#7ea863); }
  .pic-top { width:104px; height:10px; margin:-5px 0 0 -52px;
    background:linear-gradient(#d3a978,#b98b5e); transform: translate3d(82px,35px,4px) rotateX(-90deg); }
  .pic-side { width:10px; height:78px; margin:-39px 0 0 -5px;
    background:linear-gradient(90deg,#c2915f,#93683c); transform: translate3d(134px,74px,4px) rotateY(90deg); }

  /* ===== 窗帘（后墙，围住那扇窗）：帘杆 + 左右两片帘，帘面有褶皱、会轻轻晃 ===== */
  .curtain-rod { width:200px; height:7px; margin:-3.5px 0 0 -100px; border-radius:4px;
    background:linear-gradient(#d8ac7d,#a9794f); transform: translate3d(242px,26px,11px); }
  .curtain-rod::before, .curtain-rod::after { content:''; position:absolute; top:-4px; width:15px; height:15px;
    border-radius:50%; background:radial-gradient(circle at 38% 32%, #eec49a, #a9794f); }
  .curtain-rod::before { left:-10px; } .curtain-rod::after { right:-10px; }
  .curtain-panel { width:26px; height:0; transform-style:preserve-3d; }
  .curtain-panel .folds { display:block; width:26px; height:128px; border-radius:0 0 13px 13px;
    transform-origin:50% 0; animation: curtainSway 5.4s ease-in-out infinite;
    background:repeating-linear-gradient(90deg,#f0b3b3 0 5px,#dd9191 5px 9px,#f8c6c6 9px 13px);
    box-shadow: inset 0 -8px 12px rgba(120,60,60,.22), 2px 2px 8px rgba(90,50,25,.18); }
  .curtain-panel.cl { transform: translate3d(150px,33px,10px); }
  .curtain-panel.cr { transform: translate3d(308px,33px,10px); }
  .curtain-panel.cr .folds { animation-delay:-2.7s; }
  @keyframes curtainSway { 0%,100% { transform: rotate(-1.5deg); } 50% { transform: rotate(1.5deg); } }

  /* ===== 挂钟（左墙）=====
     左墙是 rotateY(-90deg) 立起来的，子元素本地 +z 指向屋外(-x)：
     所以整只钟先 translateZ(-10px) 挪进屋里、再 rotateY(180deg) 把表盘翻向屋内，
     指针才是顺时针走（翻转后子元素的 translateZ 方向也自动反过来了，正好朝屋里）。 */
  .clock { width:76px; height:76px; margin:-38px 0 0 -38px; cursor:pointer;
    transform: translate3d(300px,96px,-10px) rotateY(180deg); transform-style:preserve-3d; }
  .clock .disc { position:absolute; inset:0; border-radius:50%;
    background:radial-gradient(circle at 38% 32%, #fffdf5, #f4e7cd 62%, #e6d4b4);
    box-shadow: inset 0 0 0 5px #b98b5e, inset 0 0 0 7px #d3a978, 0 4px 10px rgba(60,35,15,.3);
    transform: translateZ(2px); }
  .clock .tk { position:absolute; left:50%; top:50%; width:2px; height:7px; margin:-3.5px 0 0 -1px;
    background:#8a6742; border-radius:1px; }
  .clock .tk.major { width:3px; height:10px; margin:-5px 0 0 -1.5px; background:#6b5341; }
  .clock .hands { position:absolute; inset:0; transform: translateZ(4px); }
  .clock .hand { position:absolute; left:50%; bottom:50%; transform-origin:50% 100%; border-radius:2px; }
  .clock .h-hour { width:4px; height:19px; margin-left:-2px; background:#6b5341; }
  .clock .h-min { width:3px; height:27px; margin-left:-1.5px; background:#6b5341; }
  .clock .h-sec { width:1.5px; height:31px; margin-left:-.75px; background:#c0392b; }
  .clock .cap { position:absolute; left:50%; top:50%; width:8px; height:8px; margin:-4px 0 0 -4px;
    border-radius:50%; background:radial-gradient(circle at 40% 35%, #8a6742, #5a4030); }

  /* ===== 台灯（地面家具，挂物理刚体）：底座 + 灯杆 + 灯罩 + 暖光 + 地面光斑 ===== */
  .lamp { cursor:pointer; }
  /* 旧的灯罩/灯杆/底座单面贴图已删除：现在这三样都是真盒子（box_css/shade_css），
     ⚠️ 留着 .lamp .shade 会把新的锥形灯罩容器套成 54x34 的贴图（踩过）。 */
  /* 灯泡：亮球（灯罩里的光源，从灯口露出来，比灯口小一圈不挡灯口） */
  .lamp .bulb { position:absolute; left:0; bottom:88px; width:20px; height:20px; margin-left:-10px;
    border-radius:50%; background:radial-gradient(circle at 42% 36%, #fffef7, #ffeaa6 52%, #ffcd57);
    box-shadow:0 0 14px 4px rgba(255,228,145,.95), 0 0 34px 12px rgba(255,214,120,.55); }
  .lamp .glow { position:absolute; left:0; bottom:34px; width:170px; height:120px; margin-left:-85px;
    border-radius:50%; pointer-events:none; filter:blur(4px); transition:opacity .25s;
    background:radial-gradient(ellipse at 50% 45%, rgba(255,220,140,.62), rgba(255,200,110,0) 68%); }
  /* 地面光斑：和影子一样平躺在地面上（挂在 .item 上，不跟 .sprite 上下飞）*/
  .lamp-pool { position:absolute; left:0; top:0; width:260px; height:180px; margin:-90px 0 0 -130px;
    border-radius:50%; pointer-events:none; transform: rotateX(-90deg); filter:blur(6px);
    transition:opacity .25s;
    background:radial-gradient(ellipse at 50% 50%, rgba(255,206,120,.42), rgba(255,206,120,0) 62%); }
  .item.lampoff .glow, .item.lampoff .lamp-pool { opacity:0; }
  .item.lampoff .shade { filter:brightness(.78) saturate(.7); }
"""
# 挂钟的 12 个刻度：绕钟心转 i*30°，再向外推 30px（3/6/9/12 点用粗刻度）
CLOCK_TICKS = "\n".join(
    '            <span class="tk%s" style="transform: translateZ(3px) rotate(%ddeg) translateY(-30px)"></span>'
    % (" major" if i % 3 == 0 else "", i * 30) for i in range(12))

DECOR_DOM_BACK = """
        <div class="deco pic" id="pic">
          <span class="pic-top"></span><span class="pic-side"></span>
          <div class="pic-front"><span class="art"></span></div>
        </div>
        <div class="deco curtain" id="curtain">
          <span class="curtain-rod"></span>
          <div class="curtain-panel cl"><span class="folds"></span></div>
          <div class="curtain-panel cr"><span class="folds"></span></div>
        </div>"""

DECOR_DOM_LEFT = """
        <div class="deco clock" id="clock">
          <div class="disc"></div>
""" + CLOCK_TICKS + """
          <div class="hands">
            <span class="hand h-hour" id="clk-hour"></span>
            <span class="hand h-min" id="clk-min"></span>
            <span class="hand h-sec" id="clk-sec"></span>
            <span class="cap"></span>
          </div>
        </div>"""

# ===== 真 6 面盒子（2026-11-04 宝宝要求：家具做成真立方体，方便以后单个物体旋转）=====
def box_css(name, w, h, d, y0=0, x0=0, z0=0, front='#fff', back=None, side=None,
            top=None, bottom=None, radius='0', side_radius='0'):
    """生成一个真 6 面盒子：w 宽 / h 高 / d 深（CSS px）。
    盒子底边落在锚点上方 y0 处；x0/z0 是相对锚点的偏移。
    面：front 朝观察者(+z)、back 朝后(-z)、left/right 左右、top 朝上、bottom 朝下。
    y 向下为正，所以「上」是负 y：top 面用 rotateX(-90deg)、bottom 用 rotateX(90deg)。"""
    back = back if back is not None else front
    side = side if side is not None else front
    top = top if top is not None else front
    bottom = bottom if bottom is not None else side
    c = name
    return f"""
  .{c} {{ position:absolute; left:0; bottom:{y0}px; width:{w}px; height:{h}px; margin-left:{-w / 2}px;
    transform: translate3d({x0}px,0,{z0}px); transform-style:preserve-3d; }}
  .{c} > i {{ position:absolute; left:50%; top:50%; display:block; }}
  .{c} .bx-f {{ width:{w}px; height:{h}px; margin:{-h / 2}px 0 0 {-w / 2}px; border-radius:{radius};
    background:{front}; transform: translateZ({d / 2}px); }}
  .{c} .bx-b {{ width:{w}px; height:{h}px; margin:{-h / 2}px 0 0 {-w / 2}px; border-radius:{radius};
    background:{back}; transform: translateZ({-d / 2}px) rotateY(180deg); }}
  .{c} .bx-l {{ width:{d}px; height:{h}px; margin:{-h / 2}px 0 0 {-d / 2}px; border-radius:{side_radius};
    background:{side}; transform: translateX({-w / 2}px) rotateY(-90deg); }}
  .{c} .bx-r {{ width:{d}px; height:{h}px; margin:{-h / 2}px 0 0 {-d / 2}px; border-radius:{side_radius};
    background:{side}; transform: translateX({w / 2}px) rotateY(90deg); }}
  .{c} .bx-t {{ width:{w}px; height:{d}px; margin:{-d / 2}px 0 0 {-w / 2}px; background:{top};
    transform: translateY({-h / 2}px) rotateX(-90deg); }}
  .{c} .bx-d {{ width:{w}px; height:{d}px; margin:{-d / 2}px 0 0 {-w / 2}px; background:{bottom};
    transform: translateY({h / 2}px) rotateX(90deg); }}"""


def box_dom(name):
    return ('<div class="' + name + '"><i class="bx-f"></i><i class="bx-b"></i><i class="bx-l"></i>'
            '<i class="bx-r"></i><i class="bx-t"></i><i class="bx-d"></i></div>')


def bowl_css(name='bowl8', r=28, h=32, n=24):
    """半圆中空的圆碗：用「两段半径 + 圆底」拼出碗的收口轮廓。
    上段半径 r（碗沿），下段收到 0.8r，底部再用一块椭圆收口；
    每段 n 个侧面、面宽多给 30% 让相邻面重叠消缝（8 个面会露出棱，24 个才顺）。"""
    bands = [(1.00, -h, 0)]   # 单段圆筒：每面底部半圆角，整体轮廓就是「半个球」
    css = [f"""
  /* 圆碗：两段圆柱 + 圆底收口，{n} 面/段；靠每面亮度差异出球面感 */
  .{name} {{ position:absolute; left:0; top:0; width:0; height:0; transform-style:preserve-3d; }}
  .{name} > i {{ position:absolute; left:0; top:0; display:block; }}"""]
    idx = 0
    for bi, (fr, y_top, y_bot) in enumerate(bands):
        rr = r * fr
        w = 2 * rr * math.sin(math.pi / n) * 1.3
        bh = y_bot - y_top
        for k in range(n):
            phi = (360.0 / n) * k + (180.0 / n) * bi
            rad = math.radians(phi)
            shade = 0.80 + 0.20 * (math.sin(rad) * 0.5 + 0.5)
            top = int(248 * shade); bot = int(196 * shade)
            r_bottom = w / 2
            css.append(f"""
  .{name} .s{idx} {{ width:{w:.2f}px; height:{bh:.2f}px;
    margin:{-bh / 2:.2f}px 0 0 {-w / 2:.2f}px; border-radius:0 0 {r_bottom:.2f}px {r_bottom:.2f}px;
    background:linear-gradient(180deg, rgb({top},{top - 3},{top - 6}), rgb({bot},{bot - 6},{bot - 12}));
    transform: translate3d({rr * math.cos(rad):.2f}px, {y_top + bh / 2:.2f}px, {rr * math.sin(rad):.2f}px)
      rotateY({90 - phi:.2f}deg); }}""")
            idx += 1
    css.append(f"""
  /* 碗口：橘色圆环（中空能看到里面）→ 内壁 → 食物；底部一块椭圆收口 */
  .bowl .rim {{ width:{2 * r}px; height:{2 * r}px; margin:{-r}px 0 0 {-r}px; border-radius:50%;
    border:{max(4, r // 6)}px solid #ffa93f; background:transparent;
    box-shadow:0 0 0 1px rgba(255,236,200,.65) inset;
    transform: translate3d(0,{-h + 0.4}px,0) rotateX(-90deg); }}
  .bowl .hollow {{ width:{int(2.00 * r)}px; height:{int(2.00 * r)}px;
    margin:{-int(1.00 * r)}px 0 0 {-int(1.00 * r)}px; border-radius:50%;
    background:radial-gradient(circle at 50% 62%, #f6d9a8 0 26%, #d8b077 46%, #b8894c 74%, #9a6c36 100%);
    transform: translate3d(0,{-h + 1.2}px,0) rotateX(-90deg); }}
  /* 碗先做成空的（宝宝要空饭碗）：食物先不做，要加回来把 .meal 规则和 span 贴回来 */
  .bowl .bdisc {{ width:{int(2.06 * r)}px; height:{int(2.06 * r)}px;
    margin:{-int(1.03 * r)}px 0 0 {-int(1.03 * r)}px; border-radius:50%;
    background:radial-gradient(circle at 50% 40%, #e2e2e2, #adadad);
    transform: translate3d(0,-0.5px,0) rotateX(-90deg); }}""")
    return ''.join(css)


def bowl_dom(name='bowl8', n=24, extra=''):
    # ⚠️ 碗沿/内壁/碗底必须和侧面**同属 .bowl8 这个 3D 上下文**，
    # 否则容器自身 z=0、和平面深度相同就按 DOM 顺序画，内壁会整片盖住碗身（低角度看像少一块）
    return ('<div class="' + name + '">' + ''.join(f'<i class="s{k}"></i>' for k in range(n)) +
            extra + '</div>')


def shade_css(name='shade', r=26, r_top=17, h=32, n=16, y0=72):
    """锥形灯罩：n 个面围一圈、每面上窄下宽（clip 梯形），面宽重叠 45% 盖住角缝。
    只用 4 个面切梯形时，顶上四个角对不上 → 会「开花」，所以必须多面 + 重叠。"""
    w = 2 * r * math.sin(math.pi / n) * 1.35
    theta = math.degrees(math.atan((r - r_top) / float(h)))   # 每面向内倾的角度
    slant = math.hypot(r - r_top, h)                          # 斜面长度（面高度）
    css = [f"""
  /* 锥形灯罩：{n} 面围一圈，每面绕自己的底边向内倾 {theta:.1f}°，顶口才真的收到 r_top（只用 clip 裁窄是假收口，顶面会盖不住） */
  .{name} {{ position:absolute; left:0; bottom:{y0}px; width:0; height:0; transform-style:preserve-3d; }}
  .{name} > i {{ position:absolute; left:0; top:0; display:block; width:{w:.2f}px; height:{slant:.2f}px;
    margin:{-slant:.2f}px 0 0 {-w / 2:.2f}px; transform-origin:50% 100%; }}"""]
    for k in range(n):
        phi = (360.0 / n) * k
        rad = math.radians(phi)
        sh = 0.84 + 0.16 * (math.sin(rad) * 0.5 + 0.5)
        c1 = int(255 * sh); c2 = int(226 * sh)
        css.append(f"""
  .{name} .c{k} {{ background:linear-gradient(180deg, rgb({c1},{int(c1 * 0.94)},{int(c1 * 0.78)}), rgb({c2},{int(c2 * 0.87)},{int(c2 * 0.6)}));
    transform: translate3d({r * math.cos(rad):.2f}px, 0, {r * math.sin(rad):.2f}px) rotateY({90 - phi:.2f}deg) rotateX({theta:.2f}deg); }}""")
    css.append(f"""
  .{name} .cap {{ position:absolute; left:0; top:0; width:{2 * r_top - 2}px; height:{2 * r_top - 2}px;
    margin:{-r_top + 1}px 0 0 {-r_top + 1}px; border-radius:50%;
    background:radial-gradient(circle at 50% 45%, #fffdf2, #ffe9b8 70%, #f6cf87);
    box-shadow:0 0 14px rgba(255,225,150,.8);
    transform: translate3d(0,{-h - 1.2}px,0) rotateX(-90deg); }}""")
    return ''.join(css)


def shade_dom(name='shade', n=16):
    return ('<div class="' + name + '">' + ''.join(f'<i class="c{k}"></i>' for k in range(n)) +
            '<span class="cap"></span></div>')


BOWL8_SPRITE = ('<div class="sprite">' + bowl_dom(
    extra='<span class="bdisc"></span><span class="rim"></span><span class="hollow"></span>') + '</div>')



# ── 四件家具按真盒子重建 ──
FURN_CSS = (
    box_css('bed-m', 150, 40, 110, front='linear-gradient(#ffffff,#ece7fb)',
            back='#e2dbf3', side='linear-gradient(90deg,#e6e0f8,#d8cff1)',
            top='linear-gradient(#ffffff,#f2eefc)', bottom='#cfc7e6', radius='5px') +
    box_css('bed-h', 13, 92, 110, x0=-74, front='linear-gradient(100deg,#d8ac7d,#a9794f)',
            back='#b8865a', side='#c9a070', top='#e2bd90', bottom='#a9794f', radius='6px 6px 3px 3px') +
    box_css('bed-q', 92, 7, 114, x0=28, y0=40, front='linear-gradient(#b6a2f1,#9d86e8)',
            back='#9d86e8', side='#a790ec', top='linear-gradient(#cbbcf6,#a893ec)',
            bottom='#8b73dd', radius='4px') +
    box_css('bed-p', 44, 9, 56, x0=-46, y0=40, front='#fbfaff', back='#eeeaf8',
            side='#eae6f8', top='linear-gradient(#ffffff,#f4f1fd)', bottom='#e4dff4', radius='8px') +
    bowl_css() +
    box_css('radio3d', 66, 50, 40, front='linear-gradient(#8d6e63,#6d4c41)',
            back='#5a3f36', side='linear-gradient(90deg,#7a5a4f,#57403a)',
            top='linear-gradient(#a1887f,#8d6e63)', bottom='#46302a', radius='6px') +
    box_css('lamp-base3d', 46, 6, 46, front='#c98f4f', back='#a9743c', side='#bb8347',
            top='linear-gradient(#e0ad74,#c98f4f)', bottom='#8a5a2e', radius='50%/40%') +
    box_css('lamp-pole3d', 7, 62, 7, y0=6, front='linear-gradient(#d8a878,#8a5a2e)',
            back='#9a6a38', side='#b07f45', top='#d8a878', bottom='#8a5a2e', radius='3px') +
    shade_css() +
    """
  /* 收音机细节：喇叭 + 两个旋钮 + 天线 */
  .radio .dial { position:absolute; left:9px; bottom:13px; width:24px; height:24px; border-radius:50%;
    background:radial-gradient(circle at 50% 50%, #fff 0 30%, #bdbdbd 32% 60%, #8d8d8d 62%);
    transform: translateZ(20.5px); }
  .radio .lamp { position:absolute; left:44px; bottom:20px; width:9px; height:9px; border-radius:50%;
    background:#ffd54f; box-shadow:0 12px 0 -1px #ffd54f; transform: translateZ(20.5px); }
  .radio .ant { position:absolute; left:47px; bottom:50px; width:3px; height:34px;
    background:linear-gradient(#e0e0e0,#9e9e9e); border-radius:2px; transform-origin:50% 100%;
    transform: translateZ(4px) rotate(12deg); }
  /* 碗口/食物椭圆：绝对定位 + 锚点居中（老坑：漏了会参与正常流被顶偏） */
  .bowl .rim, .bowl .hollow, .bowl .meal, .bowl .bdisc { position:absolute; left:0; top:0; }
  """)

BED_SPRITE = '<div class="sprite">' + box_dom('bed-m') + box_dom('bed-h') + box_dom('bed-q') + box_dom('bed-p') + '</div>'
BOWL_SPRITE = BOWL8_SPRITE
RADIO_SPRITE = ('<div class="sprite">' + box_dom('radio3d') +
                '<span class="dial"></span><span class="lamp"></span><span class="ant"></span></div>')
LAMP_SPRITE = ('<div class="sprite">' + box_dom('lamp-base3d') + box_dom('lamp-pole3d') +
               shade_dom() + '<span class="bulb"></span><span class="glow"></span></div>')


LAMP_DOM = f"""
      <div class="item lamp" id="lampitem" data-x="60" data-z="330" data-phys="44,44,100"
           data-drop="280" data-mass="3" style="transform: translate3d(60px,0,330px)">
        <span class="pshadow" style="width:96px;height:76px"></span>
        <span class="lamp-pool"></span>
        {LAMP_SPRITE}
      </div>"""


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
}}
  /* 左墙（x=0 平面，绕底边转 -90° 立起来） */
  .wall.left {{ position:absolute; left:0; top:-{H}px; width:{D}px; height:{H}px;
    transform-origin:0 100%; transform: rotateY(-90deg); transform-style: preserve-3d;
    background:
      radial-gradient(circle at 22% 30%, rgba(255,255,255,.45) 0 3px, transparent 3px) 0 0/48px 48px,
      linear-gradient(180deg, #f2e2cb, #dcc2a0);
}}
  /* 踢脚线 */
  .base {{ position:absolute; background:#b57f52; }}
  .base.back {{ left:0; bottom:0; width:{W}px; height:12px; }}
  .base.left {{ left:0; bottom:0; width:{D}px; height:12px; }}

  /* 窗：贴在后墙上 */
  .window {{ position:absolute; left:42%; top:16%; width:132px; height:104px; border-radius:8px; cursor:pointer;
    background: linear-gradient(#bfe3f7, #e7f6ff); border:6px solid #d9b08c; overflow:hidden;
    box-shadow: 0 4px 12px rgba(0,0,0,.16), inset 0 0 0 2px rgba(255,255,255,.6); }}
  .window::before {{ content:''; position:absolute; left:50%; top:0; bottom:0; width:5px; margin-left:-2.5px; background:#d9b08c; }}
  .window::after {{ content:''; position:absolute; top:50%; left:0; right:0; height:5px; margin-top:-2.5px; background:#d9b08c; }}
  .sun {{ position:absolute; right:10px; top:10px; width:26px; height:26px; border-radius:50%;
    background:radial-gradient(circle, #ffe680, #ffcf40); box-shadow:0 0 16px rgba(255,214,64,.85); }}
  .cloud {{ position:absolute; left:8px; top:12px; width:40px; height:12px; border-radius:20px;
    background:rgba(255,255,255,.92); box-shadow:11px -6px 0 -2px rgba(255,255,255,.92); animation: drift 9s ease-in-out infinite; }}
  @keyframes drift {{ 0%,100% {{ transform: translateX(0); }} 50% {{ transform: translateX(20px); }} }}

  /* ===== 地板和墙的厚度（薄板 24 / 18）=====
     厚度值只在这里定义一次：T_FLOOR=24、T_WALL=18，改薄改厚都动这两个数。 */
  .slab {{ position:absolute; left:0; top:0; }}
  /* 地面前沿厚板：盒心落在锚点（margin -h/2）后下移 h/2，正好贴住地板面 0..24；
     高度多给 1px 并上移 0.5，压掉地板面与厚度板之间那条抗锯齿虚缝 */
  .floor-front {{ width:{W + 9}px; height:13px; margin:-6.5px 0 0 -{(W + 9)//2}px;
    background:linear-gradient(#b0763f, #7d4f28);
    transform: translate3d({W//2 - 4.5}px, 6px, {D}px); }}
  /* 与左墙侧同理：向右加宽一个墙厚（9px）到 z=-9，铺到后墙右端面正下方，右后角连成一条 */
  .floor-right {{ width:{D + 9}px; height:13px; margin:-6.5px 0 0 -{(D + 9)//2}px;
    background:linear-gradient(#bd8248, #8a5a2e);
    transform: translate3d({W}px, 6px, {D//2 - 4.5}px) rotateY(-90deg); }}
  /* 墙顶厚板：盒心 -h/2，translate -H 后平面正好落在墙顶 y=-H */
  .wall-back-top {{ width:{W}px; height:9px; margin:-4.5px 0 0 -{W//2}px;
    background:linear-gradient(#a98a63, #8a6c47);
    transform: translate3d({W//2}px, -{H}px, -4.5px) rotateX(-90deg); }}
  .wall-left-top {{ width:{D}px; height:9px; margin:-4.5px 0 0 -{D//2}px;
    background:linear-gradient(#9d7f5c, #7f6242);
    transform: translate3d(-4.5px, -{H}px, {D//2}px) rotateX(-90deg) rotateZ(90deg); }}

  /* ===== 转折处填角 =====
     两块墙顶厚板在墙角会留一个 18x18 的方缺口，地面前沿/右侧厚板在地板右前角
     只会碰到一条棱。各补一块填角，把转折接顺。 */
  .corner-top {{ position:absolute; left:0; top:0; width:9px; height:9px; margin:-4.5px 0 0 -4.5px;
    background:linear-gradient(135deg, #b08f68, #7f6242);
    transform: translate3d(-4.5px, -{H}px, -4.5px) rotateX(-90deg); }}
  /* 地板角条：只负责盖住两条厚板交汇处的那道细缝，尺寸略小于台阶（0..24）不出尖 */
  .corner-floor {{ position:absolute; left:0; top:0; width:3px; height:13px; margin:-6.5px 0 0 -1.5px;
    background:linear-gradient(135deg, #a2683a, #6d4522);
    transform: translate3d({W}px, 6px, {D}px) rotateY(-45deg); }}

  /* 墙的端面（后墙右端、左墙近端）：让墙看起来是有厚度的板 */
  .wall-end {{ position:absolute; left:0; top:0; }}
  .wall-end.back {{ width:9px; height:{H}px; margin:-{H//2}px 0 0 -4.5px;
    background:linear-gradient(90deg, #c9ab84, #a98a63);
    transform: translate3d({W}px, -{H//2}px, -4.5px) rotateY(-90deg); }}
  .wall-end.left {{ width:9px; height:{H}px; margin:-{H//2}px 0 0 -4.5px;
    background:linear-gradient(90deg, #c3a582, #a3855f);
    transform: translate3d(-4.5px, -{H//2}px, {D}px); }}

  /* 两块墙在墙角外侧会留一个 9x9 的竖缺口（墙皮只各管一个方向），补一根角柱封住 */
  .wall-outer-corner {{ position:absolute; left:0; top:0; width:13px; height:{H}px; margin:-{H//2}px 0 0 -6.5px;
    background:linear-gradient(90deg, #cbb28e, #9d7f5c);
    transform: translate3d(-4.5px, -{H//2}px, -4.5px) rotateY(-135deg); }}

  /* ===== 地面上的东西 ===== */
  .item {{ position:absolute; left:0; top:0; transform-style:preserve-3d; }}
  /* 家具影子：主人说先不要（要恢复就把下面 display:none 删掉、把原规则贴回来）*/
  .pshadow {{ display:none; }}
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

{FURN_CSS}

  .notes {{ position:absolute; left:0; bottom:62px; transform:translateX(-50%); font-size:15px; opacity:0; }}
  .notes.on {{ opacity:1; animation: floatUp 1.4s ease-in-out infinite; }}
  @keyframes floatUp {{ 0% {{ transform:translate(-50%,0); opacity:0; }} 40% {{ opacity:1; }}
                        100% {{ transform:translate(-50%,-26px); opacity:0; }} }}

  /* ===== 方块形态 ===== */{DECOR_CSS}
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

  /* 桌宠显示/隐藏：主人要先只看屋子，屋子弄好再放进来（顶栏 👀 隐藏 / 🐣 / 🦊 三选一） */
  .room[data-pet="off"] #foxitem,
  .room[data-pet="off"] #blockitem {{ display:none; }}

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
  /* ===== 交互菜单：点角色时在它头顶弹出的一排按钮 ===== */
  .actmenu {{ position:fixed; left:0; top:0; display:flex; flex-wrap:wrap; justify-content:center;
    gap:6px; padding:8px 10px; border-radius:16px; max-width:min(320px, 84vw);
    background:rgba(60,40,24,.86); box-shadow:0 8px 22px rgba(0,0,0,.35); z-index:30;
    transform:translate(-50%,-100%) scale(.92); transform-origin:50% 100%;
    opacity:0; pointer-events:none; transition:opacity .14s, transform .14s; }}
  .actmenu.on {{ opacity:1; pointer-events:auto; transform:translate(-50%,-100%) scale(1); }}
  .actmenu button {{ border:none; border-radius:12px; padding:8px 9px; font-size:12px; cursor:pointer;
    background:#f0dcc8; color:#5a4636; white-space:nowrap; }}
  .actmenu button:active {{ background:#e6a86b; color:#fff; }}
  .bubble {{ position:fixed; left:50%; top:22%; transform:translateX(-50%); background:#fff; color:#5a4636;
    padding:8px 14px; border-radius:16px; font-size:14px; box-shadow:0 6px 16px rgba(0,0,0,.22);
    opacity:0; transition: opacity .18s, transform .18s; pointer-events:none; white-space:nowrap; z-index:20; }}
  .bubble.on {{ opacity:1; transform:translateX(-50%) translateY(-3px); }}
</style>
</head>
<body>
<div class="room pet-room" id="room" data-form="block" data-pet="off">
  <div class="stage">
    <div class="world">
      <div class="wall back"><span class="base back"></span>
        <div class="window" id="window"><span class="sun"></span><span class="cloud"></span></div>{DECOR_DOM_BACK}
      </div>
      <div class="wall left"><span class="base left"></span>{DECOR_DOM_LEFT}
      </div>
      <span class="slab floor-front" id="fedge"></span>
      <span class="slab floor-right" id="redge"></span>
      <span class="slab wall-back-top" id="wbtop"></span>
      <span class="slab wall-left-top" id="wltop"></span>
      <span class="wall-end back" id="weback"></span>
      <span class="wall-end left" id="weleft"></span>
      <span class="corner-top" id="ctop"></span>
      <span class="corner-floor" id="cfloor"></span>
      <span class="wall-outer-corner" id="woc"></span>
      <div class="floor" id="flooritem"></div>

      <div class="item" id="rugitem" style="transform: translate3d({RUGR[0]}px,-1px,{RUGR[1]}px)">
        <span class="rugface"></span>
      </div>

      <div class="item bed" id="beditem" data-act="sleep" data-x="78" data-z="140"
           data-phys="150,110,44" data-drop="160" data-mass="24"
           style="transform: translate3d(78px,0,140px)">
        <span class="pshadow" style="width:180px;height:140px"></span>
        {BED_SPRITE}
      </div>

      <div class="item bowl" id="bowlitem" data-act="eat" data-x="272" data-z="352"
           data-phys="56,56,36" data-drop="240" data-mass="1.5"
           style="transform: translate3d(272px,0,352px)">
        <span class="pshadow" style="width:110px;height:90px"></span>
        {BOWL_SPRITE}
      </div>

      <div class="item radio" id="radioitem" data-act="dance" data-x="350" data-z="140"
           data-phys="66,40,50" data-drop="200" data-mass="6"
           style="transform: translate3d(350px,0,140px)">
        <span class="pshadow" style="width:120px;height:90px"></span>
        {RADIO_SPRITE}
        <span class="notes" id="notes">🎵</span>
      </div>{LAMP_DOM}

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

  <div class="actmenu" id="actmenu">
    <button data-menu="sleep">😴 睡</button>
    <button data-menu="eat">🍚 吃</button>
    <button data-menu="dance">🎵 听</button>
    <button data-menu="look">🪟 窗</button>
    <button data-menu="form">🔁 换</button>
    <button data-menu="hide">🙈 收</button>
  </div>
  <div class="bubble" id="bubble"></div>

  <div class="top">
    <span class="title">🏠 小屋</span>
    <button class="formbtn on" id="btn-block">🐣 方块</button>
    <button class="formbtn" id="btn-fox">🦊 狐狐</button>
    <button class="formbtn" id="btn-none">👀 隐藏</button>
    <button class="formbtn" id="btn-drop">🔄 重落</button>
    <span class="hint">点角色试试</span>
    <button class="close" id="gear">⚙️</button>
    <button class="close" id="close">✕</button>
  </div>
</div>
<script src="vendor/cannon-es.js"></script>
<script src="room-physics.js"></script>
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
  document.getElementById('window').addEventListener('click', function () {{ doAct('look', 242, 120); }});

  // 调试：记录每次按下到底命中了哪个元素（点击不灵时用它定位，正式版可删）
  document.addEventListener('pointerdown', function (e) {{
    var t = e.target;
    note('hit ' + (t.id ? '#' + t.id : '') + (typeof t.className === 'string' && t.className ? '.' + t.className.split(' ')[0] : '') + ' <' + t.tagName + '>'
      + ' @' + Math.round(e.clientX) + ',' + Math.round(e.clientY));
  }}, true);

  // 挂钟：按真实时间走（分针/时针连续，秒针每秒跳一格）
  var clkH = document.getElementById('clk-hour'), clkM = document.getElementById('clk-min'),
      clkS = document.getElementById('clk-sec');
  function tickClock() {{
    var d = new Date();
    var s = d.getSeconds(), m = d.getMinutes() + s / 60, h = (d.getHours() % 12) + m / 60;
    clkS.style.transform = 'rotate(' + (s * 6).toFixed(1) + 'deg)';
    clkM.style.transform = 'rotate(' + (m * 6).toFixed(2) + 'deg)';
    clkH.style.transform = 'rotate(' + (h * 30).toFixed(2) + 'deg)';
  }}
  tickClock();
  setInterval(tickClock, 1000);
  document.getElementById('clock').addEventListener('click', function () {{
    var d = new Date();
    say('现在 ' + d.getHours() + ':' + ('0' + d.getMinutes()).slice(-2), 1600);
  }});

  // 台灯：点一下开/关（暖光 + 地面光斑一起灭）
  function toggleLamp() {{
    var el = document.getElementById('lampitem');
    var off = el.classList.toggle('lampoff');
    say(off ? '灯关掉了…' : '灯亮了', 1300);
    note('lamp ' + (off ? 'off' : 'on'));
  }}
  document.getElementById('lampitem').addEventListener('click', toggleLamp);

  // ===== 3D 命中兜底 =====
  // preserve-3d 里，绘制是「逐像素」排序、命中测试却按「元素中心」排序：
  // 左墙这种大平面的中心离镜头更近，就会把画在它前面的家具的点击抢走
  // （真机实测：点台灯灯罩，elementFromPoint 说 .shade，真实点击说 .wall left）。
  // 所以点击没落到任何 .item/.window/.deco 上时，再按屏幕矩形判一次，谁命中算谁的。
  var HIT_FALLBACK = [
    {{ id: 'beditem', act: 'sleep' }},
    {{ id: 'bowlitem', act: 'eat' }},
    {{ id: 'radioitem', act: 'dance' }},
    {{ id: 'lampitem', lamp: true }}
  ];
  document.querySelector('.stage').addEventListener('click', function (e) {{
    // ① 角色优先：用屏幕矩形判（大平面会按「元素中心」抢走命中，见 docs/memory.md）
    var pet = activeItem();
    var pr = unionRect(pet.querySelector('.sprite') || pet);
    if (pr.width > 2 && e.clientX >= pr.left && e.clientX <= pr.right
        && e.clientY >= pr.top && e.clientY <= pr.bottom) {{
      note('tap ' + (room.dataset.form === 'fox' ? 'fox' : 'block'));
      room.classList.add('bounce'); say(pick(SAY.idle), 1200);
      setTimeout(function () {{ room.classList.remove('bounce'); }}, 500);
      openMenu();
      return;
    }}
    if (e.target.closest('.item') || e.target.closest('.window') || e.target.closest('.deco')) return;
    for (var i = 0; i < HIT_FALLBACK.length; i++) {{
      var f = HIT_FALLBACK[i], el = document.getElementById(f.id);
      if (!el) continue;
      var r = unionRect(el.querySelector('.sprite') || el);
      if (r.width < 2 || r.height < 2) continue;
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) continue;
      note('hit-fallback ' + f.id);
      if (f.lamp) toggleLamp();
      else doAct(f.act, parseFloat(el.dataset.x), parseFloat(el.dataset.z));
      return;
    }}
  }});

  // 物理重落：顶栏「🔄 重落」按钮（原来挂在地毯上，会抢角色的点击，已挪走）
  document.getElementById('btn-drop').addEventListener('click', function () {{
    if (window.RoomPhys && window.RoomPhys.drop) {{ window.RoomPhys.drop(); say('再落一遍～', 1200); }}
    else say('（物理引擎没起来）', 1400);
  }});

  // 挂画 / 窗帘：点一下要有反馈，不然像贴图
  document.getElementById('pic').addEventListener('click', function () {{
    say(pick(['画里是日落的山', '主人画的～', '这幅挂了好久']), 1600);
  }});
  document.getElementById('curtain').addEventListener('click', function () {{
    say(pick(['有风', '窗帘在动']), 1200);
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
        // 机位范围是夹紧的：yaw 越过墙平面就会看到墙背面（挂钟/挂画镜像），
        // tilt 转到正数就等于从地板底下往上看（地板背面盖住整个房间、家具全点不到）。
        CAM.yaw = Math.max(-160, Math.min(40, Math.round((CAM.yaw + dx * 0.16) * 10) / 10));
        CAM.tilt = Math.max(-88, Math.min(-2, Math.round((CAM.tilt - dy * 0.14) * 10) / 10));
        applyCam();
      }}
    }});
    function up(e) {{
      if (!pts[e.pointerId]) return;
      delete pts[e.pointerId];
      if (count() === 0 && moved) {{
        note('cam tilt=' + CAM.tilt + ' yaw=' + CAM.yaw + ' zoom=' + CAM.zoom + ' top=' + CAM.top);
        dumpRects('cam');
      }}
    }}
    stage.addEventListener('pointerup', up);
    stage.addEventListener('pointercancel', up);
    // 双击空白处：机位复位到默认
    var lastTap = 0;
    stage.addEventListener('click', function (e) {{
      // 点在物件/角色上不动菜单（角色点自己会开菜单）；只有点空地才收起
      if (!e.target.closest('.item') && !e.target.closest('.window') && !e.target.closest('.deco')) {{
        if (actmenu.classList.contains('on')) openMenu(false);
      }}
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

  // ===== 交互菜单：点角色 → 头顶弹出一排交互键 =====
  var actmenu = document.getElementById('actmenu');
  function openMenu(force) {{
    var on = (force === undefined) ? !actmenu.classList.contains('on') : !!force;
    if (on) {{
      // 定位到当前角色头顶
      var it = activeItem();
      var r = unionRect(it.querySelector('.sprite') || it);
      var cx = r.width > 2 ? r.left + r.width / 2 : innerWidth / 2;
      var ty = r.height > 2 ? r.top : innerHeight * 0.5;
      actmenu.style.left = Math.round(cx) + 'px';
      actmenu.style.top = Math.round(ty - 10) + 'px';
      note('menu open at ' + Math.round(cx) + ',' + Math.round(ty));
    }} else {{
      note('menu close');
    }}
    actmenu.classList.toggle('on', on);
  }}
  actmenu.addEventListener('click', function (e) {{
    var b = e.target.closest('button'); if (!b) return;
    var k = b.getAttribute('data-menu');
    openMenu(false);
    if (k === 'sleep') doAct('sleep', 78, 140);
    else if (k === 'eat') doAct('eat', 272, 352);
    else if (k === 'dance') doAct('dance', 350, 140);
    else if (k === 'look') doAct('look', 242, 120);
    else if (k === 'form') setForm(room.dataset.form === 'fox' ? 'block' : 'fox');
    else if (k === 'hide') setPetVisible(false);
    note('menu pick ' + k);
  }});

  function syncPetButtons() {{
    var on = room.dataset.pet !== 'off';
    document.getElementById('btn-block').classList.toggle('on', on && room.dataset.form === 'block');
    document.getElementById('btn-fox').classList.toggle('on', on && room.dataset.form === 'fox');
    document.getElementById('btn-none').classList.toggle('on', !on);
  }}
  function setPetVisible(on) {{
    room.dataset.pet = on ? 'on' : 'off';
    syncPetButtons();
    note('pet=' + (on ? 'on' : 'off'));
  }}
  function setForm(f) {{
    room.dataset.form = f;
    room.dataset.pet = 'on';          // 选了形态就是要看桌宠
    syncPetButtons();
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
  document.getElementById('btn-none').addEventListener('click', function () {{ setPetVisible(false); }});
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

  note('loaded ' + innerWidth + 'x' + innerHeight + ' dpr=' + (window.devicePixelRatio || 1));
  // 临时：把各个 3D 元素的屏幕投影框报出来（便于 adb 点击验证）
  // 拼装体（床/台灯）的 .sprite 自身是 0x0，所以量不到就退化成「子元素并集」
  function unionRect(el) {{
    var r = el.getBoundingClientRect();
    if (r.width > 1 || r.height > 1) return r;
    // 拼装体（碗的多面体/床的盒子）自身是 0x0，而且零件可能嵌在多层容器里 →
    // 遍历**所有后代**取并集，别只看直接子元素（只看一层会量到 0x0）
    var l = 1e9, t = 1e9, ri = -1e9, bo = -1e9, any = false;
    var all = el.querySelectorAll('*');
    for (var i = 0; i < all.length; i++) {{
      var c = all[i].getBoundingClientRect();
      if (c.width < 1 && c.height < 1) continue;
      any = true;
      l = Math.min(l, c.left); t = Math.min(t, c.top);
      ri = Math.max(ri, c.right); bo = Math.max(bo, c.bottom);
    }}
    return any ? {{ left: l, top: t, width: ri - l, height: bo - t }} : r;
  }}
  function dumpRects(tag) {{
    var out = [];
    ['flooritem','fedge','redge','wbtop','wltop','aob','aol','aoc','rugitem','beditem','bowlitem','radioitem','blockitem','window','pic','clock','curtain','lampitem'].forEach(function (id) {{
      var el = document.getElementById(id); if (!el) return;
      var t = el.querySelector('.sprite') || el.querySelector('.pic-front')
        || el.querySelector('.disc') || el.querySelector('.curtain-rod')
        || el.querySelector('.rugface') || el;
      var b = unionRect(t);
      out.push(id + '=' + Math.round(b.left) + ',' + Math.round(b.top) + ',' + Math.round(b.width) + 'x' + Math.round(b.height));
    }});
    // 单独量几个「拼装体」的零件：帘子两片、台灯三个可点部位
    [['curtain-L', '#curtain .curtain-panel.cl .folds'],
     ['curtain-R', '#curtain .curtain-panel.cr .folds'],
     ['lamp-base', '#lampitem .lampbase'],
     ['lamp-pole', '#lampitem .pole'],
     ['lamp-shade', '#lampitem .shade']].forEach(function (pair) {{
      var e = document.querySelector(pair[1]); if (!e) return;
      var b = unionRect(e);
      out.push(pair[0] + '=' + Math.round(b.left) + ',' + Math.round(b.top) + ',' + Math.round(b.width) + 'x' + Math.round(b.height));
    }});
    // 命中图：直接用浏览器的 elementFromPoint 问「这个 CSS 点最上层可点的是谁」，
    // 用来分辨「是坐标算错了」还是「真有东西挡住了」（真机踩过：灯罩点不动）
    function hitMap(sel, label) {{
      var el = document.querySelector(sel); if (!el) return label + '=无';
      var r = unionRect(el);
      var hits = [];
      for (var i = 0; i < 3; i++) {{
        for (var j = 0; j < 3; j++) {{
          var hx = r.left + r.width * (i + 0.5) / 3;
          var hy = r.top + r.height * (j + 0.5) / 3;
          var t = document.elementFromPoint(hx, hy);
          hits.push(t ? (t.id ? '#' + t.id : (typeof t.className === 'string' && t.className ? '.' + t.className.split(' ')[0] : t.tagName))
                      : 'null');
        }}
      }}
      return label + '[' + hits.join(' ') + ']';
    }}
    out.push('hitmap ' + [hitMap('#lampitem .sprite', 'lamp'),
                          hitMap('#beditem .sprite', 'bed'),
                          hitMap('#bowlitem .sprite', 'bowl'),
                          hitMap('#radioitem .sprite', 'radio')].join(' '));
    note('rects' + (tag ? ' ' + tag : '') + ' ' + out.join(' | '));
  }}
  setTimeout(function () {{ dumpRects(''); }}, 3000);   // 3000ms：等物理落定后再量，否则量到的是半空坐标
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
