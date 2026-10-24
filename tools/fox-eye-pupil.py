#!/usr/bin/env python3
"""把烤在 head.png 里的眼珠拆出来（眨眼用）

背景：狐狐的深色眼珠画在 head.png 上（eyes.png 只是叠在上面的虹膜/高光/睫毛）。
只压扁 eyes.png 那层的话，底下的眼珠一动不动 —— 看起来就像「只有睫毛在动」。

做法：
    pupil-L/R.png = 眼珠包围盒里、head.png 上偏深的那部分原样抠出来
    head-base.png = head.png，把抠走的地方用**框外一圈的肤色**往里推着补上
因为抠走的像素在眼珠层里一比一盖回去，睁眼时画面和原来完全一样；
只有眨眼那一瞬间眼珠跟着压扁，露出补好的肤色 + 压在盖上的睫毛线。

用法：
    python3 tools/fox-eye-pupil.py            # 生成 head-base.png / pupil-L.png / pupil-R.png
    python3 tools/fox-eye-pupil.py --check    # 只打印会抠掉多少像素，不写文件
"""
import os
import sys
from collections import deque

from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
FOX = os.path.join(HERE, "..", "app", "src", "main", "assets", "fox")
EYE_BOXES = {          # eyes.png 里的眼珠包围盒（fox-eye-split.py 的连通域结果）
    "L": (8, 81, 72, 130),
    "R": (106, 37, 179, 88),
}
EYES_ORIGIN = (154, 192)      # .fx-eye-* 在狐坐标里的位置
HEAD_ORIGIN = (127, 126)      # .fx-head 在狐坐标里的位置
MARGIN = 10            # 眼珠包围盒外扩（把睫毛底座也算进来）
DARK_LUM = 150         # 亮度低于这个算「眼珠的一部分」
GUIDE_GROW = 4         # 只在 eyes.png 眼珠形状外扩这么多 px 的范围内抠（避免误伤轮廓线/其它深色笔画）


def guide_mask(head_size):
    """eyes.png 里两颗眼珠的形状，映射到 head 坐标系并外扩 —— 用来限定抠图范围"""
    g = Image.new("L", head_size, 0)
    eyes = Image.open(os.path.join(FOX, "eyes.png")).convert("RGBA")
    a = eyes.split()[3]
    for tag, (x0, y0, x1, y1) in EYE_BOXES.items():
        blob = Image.new("L", eyes.size, 0)
        src, dst = a.load(), blob.load()
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if src[x, y] > 60:
                    dst[x, y] = 255
        dx = EYES_ORIGIN[0] - HEAD_ORIGIN[0]
        dy = EYES_ORIGIN[1] - HEAD_ORIGIN[1]
        g.paste(blob, (dx, dy), blob)
    return g.filter(ImageFilter.MaxFilter(GUIDE_GROW * 2 + 1))


def boxes_in_head():
    dx = EYES_ORIGIN[0] - HEAD_ORIGIN[0]
    dy = EYES_ORIGIN[1] - HEAD_ORIGIN[1]
    out = {}
    for tag, (x0, y0, x1, y1) in EYE_BOXES.items():
        out[tag] = (x0 + dx - MARGIN, y0 + dy - MARGIN, x1 + dx + MARGIN, y1 + dy + MARGIN)
    return out


def inpaint(head, holes):
    """把 holes（head 坐标集合）用框外一圈的颜色往里推着补上"""
    hp, ha = head.load(), head.split()[3].load()
    HW, HH = head.size
    color = {}
    q = deque()
    for x, y in holes:
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < HW and 0 <= ny < HH and (nx, ny) not in holes and ha[nx, ny] > 128:
                color[(nx, ny)] = hp[nx, ny]
                q.append((nx, ny))
    seen = set(color)
    while q:
        cx, cy = q.popleft()
        for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            # 只往「要补的洞」里推进；不加这个判断会从画面边界无限扩散出去
            if (nx, ny) not in holes or (nx, ny) in seen:
                continue
            seen.add((nx, ny))
            color[(nx, ny)] = color[(cx, cy)]
            q.append((nx, ny))
    out = head.copy()
    op = out.load()
    missing = 0
    for x, y in holes:
        c = color.get((x, y))
        if c is None:
            missing += 1
            continue
        op[x, y] = (c[0], c[1], c[2], 255)
    return out, missing


def main():
    check_only = "--check" in sys.argv
    head = Image.open(os.path.join(FOX, "head.png")).convert("RGBA")
    hp, ha = head.load(), head.split()[3].load()
    boxes = boxes_in_head()
    guide = guide_mask(head.size).load()

    holes = {}
    for tag, (x0, y0, x1, y1) in boxes.items():
        pts = []
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if ha[x, y] > 128 and guide[x, y] > 0:
                    r, g, b, _ = hp[x, y]
                    if (r + g + b) / 3 < DARK_LUM:
                        pts.append((x, y))
        holes[tag] = pts
        print(f"眼{tag}: head 坐标框 {boxes[tag]}，判为眼珠的像素 {len(pts)}")
    if check_only:
        return 0

    # 眼珠层：只留自己那部分，裁到包围盒（同一只眼的其它部件不掺进来）
    for tag, pts in holes.items():
        if not pts:
            print(f"⚠️ 眼{tag} 没找到眼珠像素")
            continue
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        bx0, by0, bx1, by1 = min(xs), min(ys), max(xs), max(ys)
        w, h = bx1 - bx0 + 1, by1 - by0 + 1
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ip = img.load()
        for x, y in pts:
            ip[x - bx0, y - by0] = hp[x, y]
        path = os.path.join(FOX, f"pupil-{tag}.png")
        img.save(path, optimize=True)
        print(f"  写入 {path} {os.path.getsize(path)} bytes（{w}x{h}，"
              f"CSS left {bx0 + HEAD_ORIGIN[0]}px top {by0 + HEAD_ORIGIN[1]}px，眼底 y={by1}）")

    all_holes = set()
    for pts in holes.values():
        all_holes.update(pts)
    base, missing = inpaint(head, all_holes)
    if missing:
        print(f"⚠️ {missing} 个补色像素没找到参照")
    path = os.path.join(FOX, "head-base.png")
    base.save(path, optimize=True)
    print(f"写入 {path} {os.path.getsize(path)} bytes（抠掉 {len(all_holes)} 个像素并补上肤色）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
