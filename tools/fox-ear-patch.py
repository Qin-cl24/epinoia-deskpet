#!/usr/bin/env python3
"""狐狐左耳耳根补片工具（生成 + 验证）

背景：pet.html 里左耳 `.fx-ear-L` 绕耳根（transform-origin 70% 92%）旋转，
角度范围 -16°（生气）.. +12°（受惊）。旋转时耳朵内侧会离开 hair-back/layer13，
露出一条背景色的缝（原画是静止的分层，没有为摆动留余量）。

做法：补片 = ear-L 自己的像素，只保留「任何角度下会露缝」的那块，
作为静止图片垫在旋转的耳朵下面（DOM 里在 .fx-ear-L 之前）：
- 静止时被耳朵完全盖住（露出 0 像素，看不出多了一层）
- 摆动时正好把缝填上

用法：
    python3 tools/fox-ear-patch.py make     # 重新生成 assets/fox/ear-L-base.png
    python3 tools/fox-ear-patch.py verify   # 校验每个角度残余的缝像素

什么时候要重跑 make：主人重画了 ear-L.png / hair-back.png / layer13.png，
或者改了耳朵的 transform-origin、旋转角度范围。
"""
import os
import sys

from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
FOX = os.path.join(HERE, "..", "app", "src", "main", "assets", "fox")
CANVAS = (543, 626)
BG = (250, 235, 225, 255)          # 合成校验用底色，只为区分「没人画的地方」
EAR_BOX = (0, 137, 142, 176)       # left, top, w, h（和 pet.html 的 .fx-ear-L 一致）
EAR_PIVOT = (0.70, 0.92)           # 和 pet.html 的 transform-origin 一致
ANGLE_RANGE = range(-16, 13)       # pet.html 里左耳实际出现的角度

# 图层顺序（后者盖前者），与 pet.html 的 DOM 顺序一致：(名, left, top, w, h)
LAYERS = [
    ("shoes", 188, 514, 167, 111), ("tail", 306, 369, 236, 216), ("pants", 178, 347, 201, 268),
    ("layer19", 232, 390, 101, 94), ("hair-back", 61, 81, 391, 315), ("neck-hands", 262, 302, 55, 65),
    ("top", 198, 296, 188, 159), ("sleeves", 211, 299, 145, 143),
    ("ear-L", 0, 137, 142, 176), ("fur-under-ear-L", 45, 202, 105, 121), ("head", 127, 126, 251, 268),
    ("part25", 196, 264, 139, 72), ("mouth", 252, 300, 26, 19), ("layer13", 70, 58, 126, 116),
    ("eyes", 154, 192, 180, 131), ("bangs", 63, 82, 375, 293), ("ear-R", 210, 0, 188, 165),
    ("fur-under-ear-R", 263, 76, 92, 98), ("hair-highlight", 124, 177, 211, 98),
    ("hair-tuft", 150, 170, 104, 45),
]


def load(name):
    return Image.open(os.path.join(FOX, name + ".png")).convert("RGBA")


def rotate(img, deg, px, py):
    """绕图内相对点 (px, py) 旋转 deg 度（PIL 正数=逆时针）"""
    w, h = img.size
    big = Image.new("RGBA", (w * 3, h * 3), (0, 0, 0, 0))
    big.paste(img, (w, h))
    big = big.rotate(deg, center=(w + px * w, h + py * h), resample=Image.BICUBIC)
    return big.crop((w, h, w * 2, h * 2))


def compose(css_angle=0.0, patch=None):
    """合成整只狐狐；css_angle 是 pet.html 里 .fx-ear-L 的旋转角"""
    canvas = Image.new("RGBA", CANVAS, BG)
    cache = {name: load(name) for name, *_ in LAYERS}
    for name, l, t, w, h in LAYERS:
        img = cache[name]
        if img.size != (w, h):
            img = img.resize((w, h), Image.LANCZOS)
        if name == "ear-L":
            if patch is not None:
                canvas.alpha_composite(patch, (l, t))
            img = rotate(img, -css_angle, *EAR_PIVOT)          # CSS 顺时针为正
        elif name == "ear-R":
            img = rotate(img, 0.0, 0.0, 0.0)                   # 右耳不参与本次校验
        canvas.alpha_composite(img, (l, t))
    return canvas


def bg_mask(im):
    """哪些像素是「背景色」（=没有任何图层画到）"""
    px = im.load()
    m = Image.new("L", im.size, 0)
    mp = m.load()
    for y in range(im.size[1]):
        for x in range(im.size[0]):
            if px[x, y] == BG:
                mp[x, y] = 255
    return m


def seam_pixels(css_angle, patch=None):
    """该角度下、耳朵内侧（靠头发一侧 x>=60）新露出的背景像素数"""
    rest = bg_mask(compose(0.0))
    cur = bg_mask(compose(css_angle, patch))
    R, C = rest.load(), cur.load()
    return sum(1 for y in range(120, 340) for x in range(60, 160)
               if C[x, y] == 255 and R[x, y] != 255)


def make():
    rest = bg_mask(compose(0.0)).load()
    union = Image.new("L", CANVAS, 0)
    U = union.load()
    for a in ANGLE_RANGE:
        P = bg_mask(compose(a)).load()
        for y in range(120, 340):
            for x in range(60, 160):                 # 只补内侧，外侧是耳廓正常移动
                if P[x, y] == 255 and rest[x, y] != 255:
                    U[x, y] = 255
    grow = union.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(1.2))

    ear = load("ear-L")
    y0 = EAR_BOX[1]
    mask = grow.crop((0, y0, EAR_BOX[2], y0 + EAR_BOX[3]))
    src_a, m, out_a = ear.split()[3].load(), mask.load(), None
    alpha = Image.new("L", ear.size, 0)
    out_a = alpha.load()
    for y in range(ear.size[1]):
        for x in range(ear.size[0]):
            out_a[x, y] = src_a[x, y] * m[x, y] // 255
    patch = ear.copy()
    patch.putalpha(alpha)

    dst = os.path.join(FOX, "ear-L-base.png")
    patch.save(dst, optimize=True)
    print("补片 alpha bbox:", alpha.getbbox(), "| 文件:", dst, os.path.getsize(dst), "bytes")
    return patch


def verify():
    patch = load("ear-L-base")
    pa = patch.split()[3].load()
    print("角度  无补片缝  有补片缝  补片填上的像素(=静止时被耳朵盖住的量)")
    ok = True
    for a in ANGLE_RANGE:
        gap = bg_mask(compose(a)).load()            # 不打补片时空出来的地方
        filled = sum(1 for y in range(176) for x in range(142)
                     if pa[x, y] > 200 and gap[x, y + EAR_BOX[1]] == 255)
        before, after = seam_pixels(a), seam_pixels(a, patch)
        ok = ok and after == 0
        print(f"{a:+3d}°     {before:4d}      {after:4d}      {filled:4d}")
    # 静止时补片必须完全看不见
    at_rest = seam_pixels(0, patch)
    print("\n静止(0°) 缝:", at_rest, "| 结论:", "✅ 全角度无缝" if ok and at_rest == 0 else "❌ 还有缝，检查参数")
    return 0 if ok else 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    if cmd == "make":
        make()
        verify()
    elif cmd == "verify":
        sys.exit(verify())
    else:
        print(__doc__)
        sys.exit(2)
