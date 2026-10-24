#!/usr/bin/env python3
"""把 eyes.png 拆成「眼珠两张 + 眉毛睫毛一张」（眨眼用）

为什么要拆：眨眼是竖向压扁。原来整张眼睛图层只绕「图层中心」压扁，可画稿里两只眼睛
是斜着的（右眼在上、左眼偏下 40 多 px），一压扁两条闭眼线就飘到脸中间，左眼还会往上跳。

做法：按连通域分组 —— 两个最大的连通域就是眼珠，其余（眉毛、睫毛、高光碎片）统一进
eye-strokes.png 保持静止不动；绝不把一笔切成两半。

为什么眉毛要单独拆出来：眨眼时眉毛不该跟着飞（真狐狸/真人眨眼眉毛基本不动），
原来整层一起压扁，眉毛会被甩下去一大截，看着像「只有睫毛在动」。

⚠️ 注意：**深色眼珠其实烤在 head.png 里**（左眼中心 601 个深色像素、右眼 521 个），
eyes.png 只是叠在上面的虹膜/高光/睫毛。所以光压扁这层眨眼是压不闭的，得配
eye-lid-L/R（肤色盖片，见 tools/fox-eye-lid.py）把那两颗眼珠盖住。

用法：
    python3 tools/fox-eye-split.py           # 生成 eye-L/eye-R/eye-strokes 并打印 transform-origin
    python3 tools/fox-eye-split.py --check   # 只打印分组结果，不写文件
"""
import os
import sys
from collections import deque

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
FOX = os.path.join(HERE, "..", "app", "src", "main", "assets", "fox")
ALPHA_MIN = 8          # 低于这个 alpha 当透明（去白边后的边缘噪点）
MIN_BLOB = 40          # 小于这么多像素的碎点不当独立部件，跟着最近的部件走


def components(im):
    W, H = im.size
    a = im.split()[3].load()
    seen = [[False] * W for _ in range(H)]
    comps = []
    for y in range(H):
        for x in range(W):
            if seen[y][x] or a[x, y] < ALPHA_MIN:
                continue
            q = deque([(x, y)])
            seen[y][x] = True
            pts = []
            while q:
                cx, cy = q.popleft()
                pts.append((cx, cy))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < W and 0 <= ny < H and not seen[ny][nx] and a[nx, ny] >= ALPHA_MIN:
                            seen[ny][nx] = True
                            q.append((nx, ny))
            comps.append(pts)
    return comps


def main():
    check_only = "--check" in sys.argv
    im = Image.open(os.path.join(FOX, "eyes.png")).convert("RGBA")
    comps = components(im)
    big = sorted(comps, key=len, reverse=True)[:2]          # 两个眼睛本体
    if len(big) < 2:
        print("❌ 只找到 %d 块像眼睛的连通域，画稿变了？" % len(big))
        return 1
    eyes = []
    for pts in big:
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        eyes.append({"pts": pts, "cx": cx, "cy": cy,
                     "bbox": (min(p[0] for p in pts), min(p[1] for p in pts),
                              max(p[0] for p in pts), max(p[1] for p in pts))})
    eyes.sort(key=lambda e: e["cx"])                        # 先左后右
    L, R = eyes

    # 每块部件整块归给最近的眼底
    groups = {"L": [], "R": []}
    for pts in comps:
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        dL = (cx - L["cx"]) ** 2 + (cy - L["cy"]) ** 2
        dR = (cx - R["cx"]) ** 2 + (cy - R["cy"]) ** 2
        groups["L" if dL <= dR else "R"].append((len(pts), pts))

    for k, tag in (("L", "左眼"), ("R", "右眼")):
        groups[k].sort(key=lambda t: -t[0])
        total = sum(n for n, _ in groups[k])
        print(f"{tag}: {len(groups[k])} 块部件、{total}px；主眼 bbox={eyes[0 if k=='L' else 1]['bbox']}")
        for n, pts in groups[k][1:]:
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            print(f"    附带部件 {n:4d}px x[{min(xs)},{max(xs)}] y[{min(ys)},{max(ys)}]")

    # 眼底（眨眼支点）= 主眼最下面那一行的中线
    origins = {}
    for k in ("L", "R"):
        main_pts = groups[k][0][1]
        ymax = max(p[1] for p in main_pts)
        xs = [p[0] for p in main_pts if p[1] >= ymax - 2]
        origins[k] = (round((min(xs) + max(xs)) / 2), ymax)
    print("transform-origin（图层坐标 px）："
          f"左眼 {origins['L'][0]}px {origins['L'][1]}px ／ 右眼 {origins['R'][0]}px {origins['R'][1]}px")
    if check_only:
        return 0

    # ① 眼珠：每只只留主连通域
    for k, fname in (("L", "eye-L.png"), ("R", "eye-R.png")):
        out = Image.new("RGBA", im.size, (0, 0, 0, 0))
        src, dst = im.load(), out.load()
        for x, y in groups[k][0][1]:
            dst[x, y] = src[x, y]
        path = os.path.join(FOX, fname)
        out.save(path, optimize=True)
        print("写入", path, os.path.getsize(path), "bytes")

    # ② 眉毛/睫毛等小部件：合成一张静止图层
    strokes = Image.new("RGBA", im.size, (0, 0, 0, 0))
    src, dst = im.load(), strokes.load()
    kept = 0
    for k in ("L", "R"):
        for _, pts in groups[k][1:]:
            for x, y in pts:
                dst[x, y] = src[x, y]
                kept += 1
    path = os.path.join(FOX, "eye-strokes.png")
    strokes.save(path, optimize=True)
    print(f"写入 {path} {os.path.getsize(path)} bytes（{kept}px 眉毛/睫毛，保持静止）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
