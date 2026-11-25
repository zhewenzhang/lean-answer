#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""去 AI 味改写器 v2：句级处理 + 改动表 + 改后全文。

v1 的教训：逐词替换会造出语义反转与断句（「不是A而是B」→「是B，A不重要」是错的）。
所以改为句级：先切句，按需重写整句，只重写结构明确、映射唯一的句式，其余交人工。

用法：
    python scripts/deai.py 稿件.md            # 改动表 + 改后全文
    python scripts/deai.py 稿件.md --apply    # 另存 稿件.deai.md
    python scripts/deai.py 稿件.md --diff     # 只列改动
退出码：0 无硬违规残留；1 仍有残留（需人工）。
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LS = _load("lint_style")

PROTECT = re.compile(r"```.*?```|`[^`\n]+`|https?://\S+|^\|.*$|^>.*$", re.M | re.S)
SENT = re.compile(r"[^。！？\n]*[。！？]?")

# ── 标点：全局安全替换 ────────────────────────────────────────
PUNCT = [
    (re.compile(r'"([^"\n]{1,60})"'), r"「\1」", "英文双引号→「」"),
    (re.compile(r"\u201c([^\u201d\n]{1,60})\u201d"), r"「\1」", "中文弯引号→「」"),
    (re.compile(r"([\u4e00-\u9fff])[ \t\u3000]{1,4}(?=\d)"), r"\1", "中文→数字去空格"),
    (re.compile(r"(\d)[ \t\u3000]{1,4}(?=[\u4e00-\u9fff])"), r"\1", "数字→中文去空格"),
]

# ── 句式：只在句内匹配，长句完整匹配在前，短模式在后 ──────────
SENT_RULES = [
    (re.compile(r"真正的[^，。；]{2,16}[，,]?\s*从来不是[^，。；]{2,20}[，,]?\s*而是"),
     "", "真正的X从来不是Y而是Z → 删掉整段，直接说Z"),
    (re.compile(r"不是(?:一个|一种|个)?([^，。,]{2,24})[，,]\s*而是(?:一个|一种|个)?([^，。,]{2,30})"),
     r"是\2，\1不是关键", "不是A而是B → 是B，A不是关键"),
    (re.compile(r"与其说[^，。,]{2,24}[，,]\s*不如说"), "", "与其说A不如说B → 只说B"),
    (re.compile(r"关键不在于[^，。；]{2,24}[，,]?\s*而在于"), "关键在", "关键不在于A而在于B → 关键在B"),
    (re.compile(r"这背后(?:其实)?反映了?"), "原因是", "这背后反映了 → 原因是"),
    (re.compile(r"这意味着[，,]?\s*我们需要?重新审视"), "所以要改的是", "这意味着需要重新审视 → 所以要改的是"),
    (re.compile(r"值得(?:注意|关注)的是[，,]?\s*"), "", "值得注意的是 → 删"),
    (re.compile(r"一个容易被忽略的(?:问题|一点)是[，,]?\s*"), "", "容易被忽略的是 → 删"),
    (re.compile(r"以前总觉得([^，。；]{2,30})[，,]\s*后来才明白"), r"以前以为\1，后来发现",
     "以前总觉得…后来才明白 → 以前以为…后来发现"),
    (re.compile(r"(?:大家)?越来越觉得[，,]?\s*(?=[一-鿿])"), "", "越来越觉得 → 删，直接说判断"),
]

ABSTRACT = ["内在秩序", "自我和解", "精神内核", "深层需求", "底层逻辑",
            "赋能", "闭环", "抓手", "颗粒度", "生命底色", "真正的"]
DASH = re.compile(r"——")


def protect(text: str) -> tuple[str, list[str]]:
    vault: list[str] = []

    def stash(m: re.Match) -> str:
        vault.append(m.group(0))
        return f"\x00{len(vault) - 1}\x00"

    return PROTECT.sub(stash, text), vault


def restore(text: str, vault: list[str]) -> str:
    return re.sub(r"\x00(\d+)\x00", lambda m: vault[int(m.group(1))], text)


def fix_sentence(s: str, changes: list, notes: list) -> str:
    if not s.strip() or "\x00" in s:
        return s
    orig = s
    for pat, rep, why in SENT_RULES:
        if not pat.search(s):
            continue
        cand = pat.sub(rep, s, count=1)
        if rep == "" and re.match(r"^\s*[，,。、；]|^\s*是", cand):
            notes.append(f"删词会造成断句，需人工：{orig.strip()[:32]}")
            continue
        if cand.strip() and cand != s:
            changes.append((orig.strip(), cand.strip(), why))
            s = cand
    return s


def rewrite(text: str) -> tuple[str, list[tuple[str, str, str]], list[str]]:
    body, vault = protect(text)
    changes: list[tuple[str, str, str]] = []
    notes: list[str] = []

    for pat, rep, why in PUNCT:
        def sub(m: re.Match, rep=rep, why=why) -> str:
            raw, new = m.group(0), m.expand(rep)
            if re.sub(r"\s", "", raw) != re.sub(r"\s", "", new):
                changes.append((raw.strip() or "（空格）", new.strip() or "（删）", why))
            return new
        body = pat.sub(sub, body)

    out_lines = []
    for line in body.split("\n"):
        if "\x00" in line or line.startswith("#"):
            out_lines.append(line)
            continue
        parts = SENT.findall(line)
        out_lines.append("".join(fix_sentence(p, changes, notes) for p in parts))
    body = "\n".join(out_lines)

    for w in ABSTRACT:
        for m in re.finditer(re.escape(w), body):
            ctx = body[max(0, m.start() - 8): m.end() + 10].replace("\n", " ")
            notes.append(f"「{w}」偏空泛或书面，换具体指代：…{ctx}…")
    n = len(DASH.findall(body))
    if n > 1:
        notes.append(f"破折号 {n} 处，上限 1 处，人工删减")

    return restore(body, vault), changes, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--diff", action="store_true")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"ERROR 找不到 {src}")
        return 1
    raw = io.open(src, encoding="utf-8").read()
    out, changes, notes = rewrite(raw)

    if args.diff:
        for old, new, why in changes:
            print(f"- {old}\n+ {new}\n  （{why}）")
        return 0

    print("| # | 原文 | 改为 | 理由 |")
    print("|---|---|---|---|")
    for i, (old, new, why) in enumerate(changes, 1):
        o = old.replace("|", "\\|")[:46]
        n = (new or "（删）").replace("|", "\\|")[:46]
        print(f"| {i} | {o} | {n} | {why} |")
    if not changes:
        print("| — | 无可自动替换项 | — | — |")

    if notes:
        print("\n**需人工处理**")
        for x in notes:
            print(f"- {x}")

    print(f"\n自动改 {len(changes)} 处，待人工 {len(notes)} 条；{len(raw)} 字 → {len(out)} 字")
    print("\n---- 改后全文 ----")
    print(out)

    if args.apply:
        dst = src.with_suffix(".deai" + src.suffix)
        io.open(dst, "w", encoding="utf-8").write(out)

    tmp = src.with_name("_deai_lint_tmp" + src.suffix)
    io.open(tmp, "w", encoding="utf-8").write(out)
    try:
        errors, warns, _ = LS.check(tmp)
    finally:
        tmp.unlink(missing_ok=True)

    if errors:
        print("\n改后仍有硬违规，需人工二次处理：")
        for e in errors:
            print(f"  ERROR {e}")
        return 1
    if warns:
        print("\n提示项（不阻断）：")
        for w in warns:
            print(f"  WARN {w}")
    print("\n改后无硬违规。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
