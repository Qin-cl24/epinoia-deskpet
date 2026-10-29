#!/usr/bin/env python3
"""按 PSD 生成狐狐各层素材 + CSS 坐标 + DOM 片段

画世界导出的 PSD 里图层名都是「图层N」、边界都是整张画布，所以：
    · 内容框自己算（只解内容框那几行，快）
    · 部位按「归一化位置 + 颜色」对上旧画稿的语义名（见 MAP）
    · 统一缩放到 app 的 543x626 画布（等比塞进高度、水平居中）

用法：
    python3 tools/fox-build-from-psd.py <文件.psd> [--out 目录] [--dry]
输出：素材写进 app/src/main/assets/fox/（--out 可改），并在标准输出打印 CSS/DOM 片段。
"""
import importlib.util
import json
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
for name in ("psd-layers", "fox-from-psd"):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    globals()[name.replace("-", "_")] = mod

pl = psd_layers
ffp = fox_from_psd

CANVAS = (543, 626)

# PSD 图层序号 → (文件名, class 后缀, 备注)。序号=0 是背景，1 是隐藏参考层，都跳过。
MAP = {
    2:  ("tail-outer", "tail-outer", "尾巴外圈/浅色"),
    3:  ("tail-inner", "tail-inner", "尾巴橙色内层"),
    4:  ("shoes", "shoes", "鞋"),
    5:  ("pants", "pants", "裤子"),
    6:  ("pants-front", "pants-front", "裤子前半片"),
    7:  ("leg-detail-L", "leg-detail-L", "旧 layer19 那一类（用途待确认）"),
    8:  ("leg-detail-R", "leg-detail-R", "同上，另一侧"),
    9:  ("hair-back", "hair-back", "后发"),
    10: ("neck-hands", "neck-hands", "脖子/手"),
    11: ("top", "top", "黑上衣"),
    12: ("top-inner", "top-inner", "上衣内层"),
    13: ("ear-L", "ear-L", "左耳"),
    14: ("fur-under-ear-L", "fur-under-ear-L", "左耳根毛"),
    15: ("head", "head", "头部/脸"),
    16: ("part25", "part25", "领口那块（旧 part25）"),
    17: ("mouth", "mouth", "嘴（待确认）"),
    18: ("eye-white-R", "eye-white-R", "右眼眼白"),
    19: ("eye-white-L", "eye-white-L", "左眼眼白"),
    20: ("iris-R", "iris-R", "右眼虹膜"),
    21: ("iris-L", "iris-L", "左眼虹膜"),
    22: ("lash-R-outer", "lash-R-outer", "右眼外侧睫毛"),
    23: ("lash-L-lower", "lash-L-lower", "左眼下睫毛"),
    24: ("lash-R-upper", "lash-R-upper", "右眼上睫毛"),
    25: ("lash-L-upper", "lash-L-upper", "左眼上睫毛"),
    26: ("brow-C", "brow-C", "两眼之间上方（待确认）"),
    27: ("brow-L", "brow-L", "左眉（待确认）"),
    28: ("brow-R", "brow-R", "右眉（待确认）"),
    29: ("lash-L-extra", "lash-L-extra", "左眼上方细线（待确认）"),
    30: ("ear-R", "ear-R", "右耳"),
    31: ("bangs", "bangs", "刘海"),
    32: ("fur-under-ear-R", "fur-under-ear-R", "右耳根毛"),
    33: ("hair-highlight", "hair-highlight", "发丝高光"),
    34: ("hair-tuft", "hair-tuft", "呆毛"),
    35: ("layer13", "layer13", "旧 layer13（用途待确认）"),
}

# 眨眼时要收起来的层（眼白 + 虹膜）；睫毛/眉毛保持静止，闭眼就剩睫毛线
BLINK_LAYERS = ["eye-white-L", "eye-white-R", "iris-L", "iris-R"]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    dry = "--dry" in sys.argv
    out_dir = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else \
        os.path.join(PROJ, "app", "src", "main", "assets", "fox")
    psd = pl.parse(path)

    # 1) 先把所有可见层的内容框算出来，取并集当画稿外框
    layers = {}
    for lay in psd["layers"]:
        if lay["name"] == "背景" or not lay["visible"]:
            continue
        bb = pl.content_bbox(psd, lay, stride=4)
        if bb is None:
            continue
        layers[lay["index"]] = (lay, bb)
    x0 = min(bb[0] for _, bb in layers.values())
    y0 = min(bb[1] for _, bb in layers.values())
    x1 = max(bb[2] for _, bb in layers.values())
    y1 = max(bb[3] for _, bb in layers.values())
    art_w, art_h = x1 - x0, y1 - y0
    S = CANVAS[1] / art_h                      # 等比塞进画布高度
    off_x = (CANVAS[0] - art_w * S) / 2 - x0 * S
    off_y = -y0 * S
    print(f'画稿外框 {art_w}x{art_h}（PSD 坐标 {x0},{y0} 起），缩放 {S:.4f}，'
          f'在 {CANVAS[0]}x{CANVAS[1]} 画布里水平居中', file=sys.stderr)

    css, dom, meta = [], [], {}
    for idx in sorted(MAP):
        if idx not in layers:
            print(f'⚠️ 图层 {idx} 不在 PSD 里，跳过', file=sys.stderr)
            continue
        lay, bb = layers[idx]
        fname, cls, note = MAP[idx]
        img, realbb = ffp.layer_image(psd, lay, bb, pad=2)
        left = round(off_x + realbb[0] * S)
        top = round(off_y + realbb[1] * S)
        w = max(1, round(img.size[0] * S))
        h = max(1, round(img.size[1] * S))
        thumb = img.resize((w, h), Image.LANCZOS)
        if not dry:
            thumb.save(os.path.join(out_dir, fname + ".png"), optimize=True)
        css.append(f'    .fx-{cls} {{ left: {left}px; top: {top}px; width: {w}px; height: {h}px; }}'
                   f'   /* PSD 第{idx}层 {lay["name"]} — {note} */')
        dom.append(f'      <img class="fx fx-{cls}" src="fox/{fname}.png" alt="">')
        meta[fname] = {"index": idx, "psd_name": lay["name"], "note": note,
                       "psd_bbox": list(realbb), "app": [left, top, w, h]}

    print("\n".join(css))
    print("\n/* ---- DOM ---- */")
    print("\n".join(dom))
    print("\n/* ---- 眨眼层 ---- */ " + " ".join(BLINK_LAYERS))
    if not dry:
        with open(os.path.join(PROJ, "app", "src", "main", "assets", "fox", "_layers.json"), "w") as f:
            json.dump({"scale": S, "offset": [off_x, off_y], "art_bbox": [x0, y0, x1, y1],
                       "layers": meta}, f, ensure_ascii=False, indent=1)
        print("图层清单写入 assets/fox/_layers.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
