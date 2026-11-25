# -*- coding: utf-8 -*-
"""lint_style.py — 去 AI 味检查器（表达层硬规则，不改事实与判断）。

用法:
    python scripts/lint_style.py 稿件.txt [--max-dash 1]
    python scripts/lint_style.py 稿件.md

检查项:
  1. 英文双引号（中文正文应用「」）
  2. 数字与中文之间的空格（应写 3个月 而非 3 个月）
  3. 破折号 —— 超过上限（默认 1 处）
  4. 句式黑名单：同篇出现 ≥2 次判 ERROR，1 次仅提示
  5. 抽象词充数（内在秩序 / 自我和解 / 底层逻辑 等）

退出码: 0 通过 / 1 有 ERROR
"""
import re
import sys
from pathlib import Path

CJK = r"\u4e00-\u9fff"

# ── 句式黑名单：(名称, 正则, 建议改法) ───────────────────────────
CLICHES = [
    ("不是…而是", r"不是[^。；\n]{0,30}而是", "直接给结论，删掉前半句的假对立"),
    ("与其说…不如说", r"与其说", "直接给结论"),
    ("真正的X从来不是", r"真正的[^。；\n]{0,20}从来不是", "改说 X 具体是什么"),
    ("关键不在于…而在于", r"关键不在于", "只留后半句"),
    ("这背后其实反映了", r"这背后(其实)?反映了", "换成具体机制或数字"),
    ("这意味着要重新审视", r"这意味着[^。\n]{0,12}重新审视", "换成「所以要做什幺」"),
    ("值得注意的是", r"值得(注意|关注)的(是|问题)", "删掉，直接说事"),
    ("一个容易被忽略的是", r"一个容易被忽略", "删掉，直接说事"),
    ("越来越觉得", r"越来越觉得", "删掉"),
    ("从被动接受到主动选择", r"从被动接受", "删掉"),
    ("以前总觉得…后来才明白", r"以前总觉得", "只在确有其事时用，并写清时间地点"),
]

# ── 抽象词充数 ────────────────────────────────────────────────
ABSTRACT = [
    "内在秩序", "自我和解", "精神内核", "深层需求", "底层逻辑", "生命底色",
    "赋能", "闭环", "抓手", "颗粒度",
]


# ── 繁简归一（只针对规则涉及的字，避免误伤专有名词） ───────────
NORM_MAP = str.maketrans({
    "這": "这", "後": "后", "實": "实", "著": "着", "視": "视", "於": "于",
    "與": "与", "覺": "觉", "從": "从", "動": "动", "個": "个", "關": "关",
    "鍵": "键", "來": "来", "選": "选", "擇": "择", "層": "层", "邏": "逻",
    "輯": "辑", "內": "内", "註": "注", "題": "题", "問": "问", "們": "们",
    "對": "对", "會": "会", "為": "为", "無": "无", "個": "个", "麼": "么",
})


def normalize(text: str) -> str:
    return text.translate(NORM_MAP)


def strip_noise(text: str) -> str:
    """去掉代码块、行内代码、URL、引用块——这些地方的标点不算违规。"""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"^\s*>.*$", "", text, flags=re.M)
    text = re.sub(r"^\s*\|.*$", "", text, flags=re.M)   # 表格行不做标点判断
    return text


def count_cjk_chars(text: str) -> int:
    return len(re.findall(f"[{CJK}]", text))


def check(path: Path, max_dash=1):
    raw = path.read_text(encoding="utf-8", errors="replace")
    body = normalize(strip_noise(raw))
    errors, warns = [], []

    # 1 英文双引号（仅中文语境）
    en = re.findall(r'"([^"\n]{1,80})"', body)
    en_cjk = [x for x in en if re.search(f"[{CJK}]", x)]
    if en_cjk:
        errors.append(f"英文双引号 {len(en_cjk)} 处（应改「」）：{en_cjk[:2]}")
    if "“" in body or "”" in body:
        errors.append("中文弯引号 “” 出现，正文统一用「」")

    # 2 数字与中文之间空格（4 位年份、版本号/小数属既有排版惯例，放行）
    gaps = []
    for m in re.finditer(rf"(?<![\d.])(\d+)[ \t]+[{CJK}]|[{CJK}][ \t]+\d", body):
        num = m.group(1)
        if num and len(num) == 4 and 1900 <= int(num) <= 2099:
            continue
        gaps.append(m.group(0))
    if gaps:
        errors.append(f"数字与中文间有空格 {len(gaps)} 处（写 3个月）：{gaps[:3]}")

    # 3 破折号
    dash = body.count("——")
    if dash > max_dash:
        errors.append(f"破折号 —— 出现 {dash} 处，上限 {max_dash}")

    # 4 句式黑名单
    for name, pat, fix in CLICHES:
        hits = re.findall(pat, body)
        if len(hits) >= 2:
            errors.append(f"句式「{name}」出现 {len(hits)} 次（≥2 超标）→ {fix}")
        elif len(hits) == 1:
            warns.append(f"句式「{name}」出现 1 次，接近超标 → {fix}")

    # 5 抽象词
    for w in ABSTRACT:
        n = body.count(w)
        if n:
            warns.append(f"抽象词「{w}」{n} 次 → 换成具体指代")

    return errors, warns, count_cjk_chars(body)


def main(argv):
    max_dash = 1
    args = []
    for i, a in enumerate(argv):
        if a == "--max-dash" and i + 1 < len(argv):
            max_dash = int(argv[i + 1])
        elif not a.startswith("--") and not (i and argv[i - 1] == "--max-dash"):
            args.append(a)
    if not args:
        print(__doc__)
        return 1

    total_err = 0
    for a in args:
        p = Path(a)
        if not p.is_file():
            print(f"MISS {a}")
            total_err += 1
            continue
        errors, warns, n = check(p, max_dash)
        for w in warns:
            print(f"WARN {w}")
        for e in errors:
            print(f"ERROR {e}")
        if errors:
            total_err += 1
            print(f"FAIL {len(errors)} error(s), {len(warns)} warning(s) | {n} 字")
        else:
            print(f"PASS 0 error(s), {len(warns)} warning(s) | {n} 字")
    return 1 if total_err else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
