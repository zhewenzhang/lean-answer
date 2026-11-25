#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lean Answer 回复文本校验器。

用法:
    python lint_reply.py <reply.txt> [--max-chars 500] [--strict]

检查项 (ERROR 拦截):
  1. 开场元话语（"好的，我来帮你分析" / "关于您的问题" 等）
  2. 收尾服务性邀约（"还需要什么随时告诉我" 等）
  3. 平行方案堆砌（方案A/B/C、选项一二三 ≥3 个）
  4. 篇幅超限（默认 500 字，正式交付物请用 --max-chars 放宽）
  5. 重点条目 > 3（数「重點/要点」区块下的 bullet）
WARN:
  6. 长回复无图无表（>220 字仍纯文字）
  7. 结尾是疑问句（把判断成本转给用户）
  8. 长回复无图无表 / 结尾疑问句

注：表达层（AI 味、标点、句式）由 lint_style.py 负责，两者分工不重叠。
退出码: 0 通过 / 1 有 ERROR
"""

import io
import re
import sys

OPENING = [
    r"好的[，,]\s*我", r"我來幫", r"我来帮", r"關於您的問題", r"关于您的问题",
    r"首先[，,]\s*讓?我们", r"首先[，,]\s*让?我们", r"以下是為您", r"以下是为您",
    r"我為您梳理", r"我为您梳理", r"讓我來", r"让我来", r"我來分析", r"我来分析",
]
CLOSING = [
    r"還需要", r"还需要", r"有什麼需要", r"有什么需要", r"如需", r"如有需要",
    r"隨時告訴我", r"随时告诉我", r"請隨時", r"请随时", r"歡迎隨時", r"欢迎随时",
    r"希望對您有幫助", r"希望对您有帮助", r"僅供參考.{0,4}$", r"仅供参考.{0,4}$",
]
PARALLEL = r"(方案\s*[A-Z一二三四五六]|選項\s*[A-Z一二三四五六]|选项\s*[A-Z一二三四五六]|Option\s*[A-F])"
SEQ = r"(我先|先扫描|先扫描|然后|接着|随后|之后我|于是我|再然后|首先我|第一步我|我又)"
SELF_ACT = r"^我\s*(扫描|检查|连接|查看|统计|整理|读取|抓取|调用了|试了)"

CJK = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")

def lint(path, max_chars=500):
    """纯校验：返回 (errors, warns)，不打印。供 audit / doctor 复用。"""

    """CLI 入口；返回 (errors, warns)。供 audit/doctor 复用。"""
    text = io.open(path, encoding="utf-8").read()
    errors, warns = [], []
    body = "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))
    n = len(re.sub(r"\s", "", text))

    head = body[:120]
    for p in OPENING:
        if re.search(p, head):
            errors.append(f"开场元话语: 命中 /{p}/")
            break

    tail = body[-160:]
    for p in CLOSING:
        if re.search(p, tail):
            errors.append(f"收尾服务性邀约: 命中 /{p}/")
            break

    opts = set(re.findall(PARALLEL, body))
    if len(opts) >= 3:
        errors.append(f"平行方案堆砌: {sorted(opts)}")

    seq = re.findall(SEQ, body)
    if len(seq) >= 3:
        errors.append(f"过程流水账: 时序连接词 {len(seq)} 处 {seq[:5]}（应只报结果与增量）")
    if re.search(SELF_ACT, body.strip()):
        errors.append("以自身动作开场（我扫描了…），应从结论或结果起句")

    if n > max_chars:
        errors.append(f"篇幅 {n} 字 > 上限 {max_chars}")

    kb = re.search(r"(?:^|\n)[#*\s]*(?:重點|重点|关键要点|核心结论)[^\n]*\n", body)
    if kb:
        seg = body[kb.end():]
        seg = re.split(r"\n\s*(?:\*\*|#{1,3}\s|needs input)", seg)[0]
        bullets = [l for l in seg.splitlines() if re.match(r"\s*(?:[-*•]|\d+[.、)])\s*\S", l)]
        if len(bullets) > 3:
            errors.append(f"重点条目 {len(bullets)} 条 > 3")

    has_visual = ("|" in body and body.count("|") >= 4) or "```" in body or "<svg" in body
    if not has_visual and n > 220:
        warns.append(f"长回复无图无表（{n} 字纯文字）")

    # 聚焦检查：一轮只推进一个目标
    topics = re.findall(r"^\s*\*\*([^*\n]{2,24})\*\*\s*$", body, re.M)
    topics += re.findall(r"^\s*#{2,3}\s+\S", body, re.M)
    if len(topics) >= 4:
        errors.append(f"一轮内主题过多（{len(topics)} 段：{topics[:5]}）——第 2 个主题应拆到下一轮")
    steps = re.findall(r"(?:\*\*)?下一步(?:\*\*)?\s*[：:]", body)
    if len(steps) >= 2:
        errors.append(f"出现 {len(steps)} 个「下一步」——每轮只留 1 个，其余排到后续轮次")
    # 引号/代码内的词属「讨论该词」，不算夹带
    body_nq = re.sub(r"「[^」]{0,24}」|`[^`]{0,40}`|\u201c[^\u201d]{0,24}\u201d", "", body)
    filler = re.findall(r"另外|顺便|附带|顺带|也可以考虑", body_nq)
    if len(filler) >= 2:
        warns.append(f"夹带延伸主题 {len(filler)} 处 {filler[:4]}——非本轮目标的内容应拆轮")
    if body.strip().endswith(("？", "?")):
        warns.append("结尾是疑问句，把判断转给了用户")
    paras = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    if len(paras) > 9:
        warns.append(f"段落 {len(paras)} 个，偏散")

    return errors, warns


def main(path, max_chars=500, strict=False):
    """CLI 入口：打印结论并返回退出码。"""
    errors, warns = lint(path, max_chars)
    n = len(re.sub(r"\s", "", io.open(path, encoding="utf-8").read()))
    for w in warns:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    if errors:
        print(f"\nFAIL {len(errors)} error(s), {len(warns)} warning(s) | {n} 字")
        return 1
    print(f"\nPASS 0 error(s), {len(warns)} warning(s) | {n} 字")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    mc = 500
    if "--max-chars" in sys.argv:
        mc = int(sys.argv[sys.argv.index("--max-chars") + 1])
    sys.exit(main(sys.argv[1], mc))
