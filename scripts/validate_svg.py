#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lean Answer SVG 示意图校验器。

用法:
    python validate_svg.py <file.svg|file.html>

检查项 (ERROR 拦截):
  1. 根 viewBox 宽度必须为 680
  2. 图形元素越出画布边界（x/y 双向）
  3. 文字估算宽度溢出所在卡片
  4. 卡片两两相交（互不包含时判错）
  5. 使用 translate 以外的变换（scale/rotate/matrix）→ 坐标不可校验，直接判错
退出码: 0 全部通过 / 1 存在 ERROR
"""

import re
import sys
import xml.etree.ElementTree as ET

CJK = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")
SUPPORTED_TRANSFORM = ("translate",)


def text_width(s: str, size: float) -> float:
    """估算文字渲染宽度：中文 1.0em，ASCII 0.55em。"""
    return sum(size * (1.0 if CJK.match(ch) else 0.55) for ch in s)


def parse_transform(tr):
    """返回 (dx, dy, 不支持变换名列表)。只累加 translate。"""
    dx = dy = 0.0
    bad = []
    for name, args in re.findall(r"([a-zA-Z]+)\(([^)]*)\)", tr or ""):
        name = name.strip()
        nums = [float(v) for v in re.findall(r"-?\d+\.?\d*", args)]
        if name == "translate":
            dx += nums[0] if nums else 0.0
            dy += nums[1] if len(nums) > 1 else 0.0
        elif name not in SUPPORTED_TRANSFORM:
            bad.append(name)
    return dx, dy, bad


def strip_svg(raw: str) -> str:
    """从可能包着 HTML 的文件里截出 <svg>...</svg>。"""
    start = raw.find("<svg")
    end = raw.rfind("</svg>")
    if start < 0:
        raise ValueError("未找到 <svg> 根元素")
    if end < 0:
        return raw[start:]
    return raw[start:end + 6]


def main(path: str) -> int:
    raw = open(path, encoding="utf-8").read()
    try:
        svg = strip_svg(raw)
    except ValueError as e:
        print(f"ERROR {e}")
        return 1

    open_tag = re.search(r"<svg[^>]*>", svg).group(0)
    vm = re.search(r'viewBox="([\d.\-\s]+)"', open_tag)
    if not vm:
        print("ERROR 缺少 viewBox")
        return 1
    vb = [float(x) for x in vm.group(1).split()]
    W, H = vb[2], vb[3]
    errors, warns = [], []
    if abs(W - 680) > 0.5:
        errors.append(f"viewBox 宽度 {W} ≠ 680")

    root = ET.fromstring(svg)
    NS = "{http://www.w3.org/2000/svg}"
    rects = []  # 用于重叠检测: (x, y, w, h)


    def _class_size(el):
        cls = el.get("class") or ""
        return 12 if "ts" in cls else (14 if cls in ("t", "th") else None)

    def add_rect(x, y, w, h, tag="rect"):
        if w <= 0 or h <= 0:
            errors.append(f"{tag} 尺寸为 0: {w}x{h}")
        if x < -0.5 or x + w > W + 0.5 or y < -0.5 or y + h > H + 0.5:
            errors.append(f"{tag} 越出画布: x={x:.0f} y={y:.0f} 右={x + w:.0f} 下={y + h:.0f}")
        elif x < 39.5 or x + w > 640.5:
            warns.append(f"{tag} 触及安全区边缘: x={x:.0f} 右={x + w:.0f}")
        rects.append((x, y, w, h))

    def walk(el, ox=0.0, oy=0.0):
        dx, dy, bad = parse_transform(el.get("transform"))
        for name in bad:
            errors.append(f"不支持的变换 {name}()：坐标无法校验，请改用 translate")
        ox, oy = ox + dx, oy + dy
        for child in el:
            tag = child.tag.replace(NS, "")
            if tag == "g":
                walk(child, ox, oy)
            elif tag in ("rect", "image", "foreignObject"):
                add_rect(ox + float(child.get("x", 0)), oy + float(child.get("y", 0)),
                         float(child.get("width", 0)), float(child.get("height", 0)), tag)
            elif tag in ("circle", "ellipse"):
                cx = ox + float(child.get("cx", 0)); cy = oy + float(child.get("cy", 0))
                rx = float(child.get("r", child.get("rx", 0)) or 0)
                ry = float(child.get("r", child.get("ry", 0)) or 0)
                add_rect(cx - rx, cy - ry, 2 * rx, 2 * ry, tag)
            elif tag == "polygon":
                pts = [float(v) for v in re.findall(r"-?\d+\.?\d*", child.get("points", ""))]
                if len(pts) >= 4:
                    xs, ys = pts[0::2], pts[1::2]
                    add_rect(ox + min(xs), oy + min(ys),
                             max(xs) - min(xs), max(ys) - min(ys), tag)
            elif tag == "path":
                warns.append("path 几何未校验，请目视确认未越界")
            elif tag == "line":
                for k, lim in (("x1", W), ("x2", W)):
                    v = ox + float(child.get(k, 0))
                    if v < -0.5 or v > lim + 0.5:
                        errors.append(f"line {k}={v:.0f} 越出画布宽")
                for k in ("y1", "y2"):
                    v = oy + float(child.get(k, 0))
                    if v < -0.5 or v > H + 0.5:
                        errors.append(f"line {k}={v:.0f} 越出画布高 {H:.0f}")
            elif tag == "text":
                check_text(el, child, ox, oy)

    def check_text(group, el, ox, oy):
        content = "".join(el.itertext()).strip()
        if not content:
            return
        size = float(el.get("font-size") or _class_size(el) or 13)
        tw = text_width(content, size)
        tx = ox + float(el.get("x", 0))
        ty = oy + float(el.get("y", 0))
        anchor = el.get("text-anchor", "start")

        if anchor == "middle":
            left, right = tx - tw / 2, tx + tw / 2
        elif anchor == "end":
            left, right = tx - tw, tx
        else:
            left, right = tx, tx + tw

        box = None
        for sib in group:
            if sib.tag.replace(NS, "") != "rect":
                continue
            rx = ox + float(sib.get("x", 0)); ry = oy + float(sib.get("y", 0))
            rw = float(sib.get("width", 0)); rh = float(sib.get("height", 0))
            if rx - 1 <= tx <= rx + rw + 1 and ry - 1 <= ty <= ry + rh + 1:
                box = (rx, ry, rw, rh)
                break

        if left < -0.5 or right > W + 0.5:
            errors.append(f"文字越出画布: 「{content[:12]}」")
            return
        if not box:
            return
        rx, ry, rw, rh = box
        if left < rx + 6 or right > rx + rw - 6:
            errors.append(
                f"文字溢出卡片: 「{content[:14]}」估算 {tw:.0f}px / 框内可用 {rw - 12:.0f}px"
            )
        if ty < ry + 5 or ty > ry + rh - 5:
            warns.append(f"文字贴近卡片上下边: 「{content[:14]}」y={ty:.0f}")

    walk(root)

    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            a, b = rects[i], rects[j]
            ix = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
            iy = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
            if ix > 2 and iy > 2:
                a_in_b = a[0] >= b[0] - 1 and a[1] >= b[1] - 1 and a[0] + a[2] <= b[0] + b[2] + 1 and a[1] + a[3] <= b[1] + b[3] + 1
                b_in_a = b[0] >= a[0] - 1 and b[1] >= a[1] - 1 and b[0] + b[2] <= a[0] + a[2] + 1 and b[1] + b[3] <= a[1] + a[3] + 1
                if not (a_in_b or b_in_a):
                    errors.append(
                        f"元素重叠: ({a[0]:.0f},{a[1]:.0f},{a[2]:.0f}x{a[3]:.0f}) 与 "
                        f"({b[0]:.0f},{b[1]:.0f},{b[2]:.0f}x{b[3]:.0f}) 交叠 {ix:.0f}x{iy:.0f}px"
                    )

    for w in warns:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    if errors:
        print(f"\nFAIL {len(errors)} error(s), {len(warns)} warning(s)")
        return 1
    print(f"\nPASS 0 error(s), {len(warns)} warning(s)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
