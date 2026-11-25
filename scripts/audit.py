#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit：出可交付的合规报告（Markdown / HTML），供团队或甲方存档。

跑完整校验后，把每条违规落到「位置 + 原文 + 问题 + 改法」，而不是只给 FAIL。
用法：
    python scripts/audit.py 稿件.md                 # Markdown 报告
    python scripts/audit.py 稿件.md --html out.html # 另出 HTML
    python scripts/audit.py 目录/ --recursive       # 批量，汇总得分
退出码：0 无 ERROR；1 有 ERROR。
"""
from __future__ import annotations

import argparse
import datetime
import html
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


LR = _load("lint_reply")
LS = _load("lint_style")

FIX_HINT = {
    "开场元话语": "删掉开场，第一句直接给结论",
    "收尾服务性邀约": "删掉邀约，只留一个具体下一步",
    "平行方案": "收敛为一个建议；确有取舍才列两项并说明差异",
    "流水账": "删过程叙述，只报结果与增量",
    "重点条目": "砍到 3 条以内，其余排下一轮",
    "篇幅": "压缩到上限内，或把细节移到表格/附图",
    "英文双引号": "中文正文改用「」",
    "弯引号": "中文正文改用「」",
    "空格": "数字与中文之间不留空格",
    "破折号": "全文最多 1 处，且不用它引出解释",
    "句式": "按提示改成直述，如「不是A而是B」→「B」",
    "抽象词": "换成具体指代或数字",
    "疑问句": "把判断给出来，不要反抛给用户",
}


def hint(msg: str) -> str:
    for k, v in FIX_HINT.items():
        if k in msg:
            return v
    return "按提示改写该处"


def locate(text: str, msg: str) -> str:
    """尽量给出原文位置：从提示里的引号内容反查。"""
    for m in re.findall(r"[「\"']([^「」\"']{2,24})[」\"']", msg):
        if m in text:
            i = text.index(m)
            line = text[:i].count("\n") + 1
            return f"第{line}行：{m[:20]}"
    for m in re.findall(r"[：:]\s*\[?['\"]?([^\]'\"]{2,24})", msg):
        if m in text:
            i = text.index(m)
            line = text[:i].count("\n") + 1
            return f"第{line}行：{m[:20]}"
    return "—"


def audit_one(path: Path) -> dict:
    raw = io.open(path, encoding="utf-8").read()
    re_err, re_wan = LR.lint(path)
    st_err, st_wan, chars = LS.check(path)
    return {
        "file": path.name,
        "chars": chars,
        "raw": raw,
        "errors": [("结构", m) for m in re_err] + [("表达", m) for m in st_err],
        "warns": [("结构", m) for m in re_wan] + [("表达", m) for m in st_wan],
    }


def score(r: dict) -> int:
    return max(0, 100 - 12 * len(r["errors"]) - 3 * len(r["warns"]))


def fingerprint(files: list[Path]) -> str:
    """执行环境指纹：谁、在哪、用什么版本、审了哪些字节。"""
    import hashlib, getpass, platform
    h = hashlib.sha256()
    for f in sorted(files):
        h.update(f.read_bytes())
    ver = re.search(r"^version:[ \t]*([^ \n]+)", io.open(HERE.parent / "SKILL.md", encoding="utf-8").read(), re.M)
    return (f"执行者 {getpass.getuser()}@{platform.node()} ｜ "
            f"Python {platform.python_version()} ｜ skill v{ver.group(1) if ver else '?'} ｜ "
            f"样本SHA256 {h.hexdigest()[:12]} ｜ 共 {len(files)} 文件")


def to_markdown(reports: list[dict], files: list[Path]) -> str:
    today = datetime.date.today().isoformat()
    total_e = sum(len(r["errors"]) for r in reports)
    total_w = sum(len(r["warns"]) for r in reports)
    avg = round(sum(score(r) for r in reports) / len(reports)) if reports else 0

    out = []
    out.append("# 输出合规报告\n")
    out.append(f"日期：{today}　文件数：{len(reports)}　"
               f"ERROR：{total_e}　WARN：{total_w}　综合得分：{avg}/100\n")
    out.append(f"\n> 执行指纹：{fingerprint(files)}\n")
    out.append("评分口径：每个 ERROR 扣 12 分，每个 WARN 扣 3 分，最低 0 分。"
               "90 分以上可直接对外，70-89 需修订，70 以下重写。\n")

    for r in reports:
        out.append(f"\n## {r['file']}（{score(r)}分，{r['chars']}字）\n")
        if not r["errors"] and not r["warns"]:
            out.append("无违规。\n")
            continue
        if r["errors"]:
            out.append("\n### 必须修（ERROR）\n")
            out.append("| # | 类型 | 位置 | 问题 | 改法 |")
            out.append("|---|---|---|---|---|")
            for i, (kind, msg) in enumerate(r["errors"], 1):
                out.append(f"| {i} | {kind} | {locate(r['raw'], msg)} | "
                           f"{msg[:60]} | {hint(msg)} |")
        if r["warns"]:
            out.append("\n### 建议修（WARN）\n")
            out.append("| # | 类型 | 问题 | 改法 |")
            out.append("|---|---|---|---|")
            for i, (kind, msg) in enumerate(r["warns"], 1):
                out.append(f"| {i} | {kind} | {msg[:60]} | {hint(msg)} |")
    return "\n".join(out) + "\n"


def to_html(md: str, reports: list[dict]) -> str:
    today = datetime.date.today().isoformat()
    total_e = sum(len(r["errors"]) for r in reports)
    avg = round(sum(score(r) for r in reports) / len(reports)) if reports else 0
    rows = []
    for r in reports:
        for kind, msg in r["errors"]:
            rows.append(f"<tr class='err'><td>{html.escape(r['file'])}</td>"
                        f"<td>{kind}</td><td>{html.escape(locate(r['raw'], msg))}</td>"
                        f"<td>{html.escape(msg[:90])}</td><td>{html.escape(hint(msg))}</td></tr>")
        for kind, msg in r["warns"]:
            rows.append(f"<tr class='warn'><td>{html.escape(r['file'])}</td>"
                        f"<td>{kind}</td><td>—</td>"
                        f"<td>{html.escape(msg[:90])}</td><td>{html.escape(hint(msg))}</td></tr>")
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>输出合规报告 {today}</title><style>
body{{font-family:-apple-system,"Segoe UI",sans-serif;max-width:980px;margin:40px auto;padding:0 20px;color:#1c2430;background:#fff}}
h1{{font-size:22px;margin-bottom:6px}} .meta{{color:#6b7a90;font-size:13px;margin-bottom:20px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:#1f3864;color:#fff;text-align:left;padding:8px;font-weight:600}}
td{{padding:7px 8px;border-bottom:1px solid #e3e8ef;vertical-align:top}}
tr.err td:first-child{{border-left:3px solid #c0392b}}
tr.warn td:first-child{{border-left:3px solid #d4a017}}
.sum{{display:flex;gap:24px;margin:16px 0 24px;font-size:14px}}
.sum b{{font-size:20px;display:block}}
</style></head><body>
<h1>输出合规报告</h1>
<div class="meta">日期 {today}　文件 {len(reports)} 份　评分口径：ERROR 扣12分，WARN 扣3分</div>
<div class="sum"><div><b>{avg}</b>综合得分</div><div><b>{total_e}</b>必须修</div>
<div><b>{sum(len(r['warns']) for r in reports)}</b>建议修</div></div>
<table><tr><th>文件</th><th>类型</th><th>位置</th><th>问题</th><th>改法</th></tr>
{''.join(rows) or '<tr><td colspan="5">无违规</td></tr>'}
</table></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--html", help="另出 HTML 报告到该路径")
    ap.add_argument("--out", help="Markdown 报告写入该路径（默认打印）")
    ap.add_argument("--recursive", action="store_true", help="目录递归")
    args = ap.parse_args()

    src = Path(args.src)
    if src.is_dir():
        pats = ("*.md", "*.txt")
        files = [p for pat in pats for p in sorted(src.rglob(pat))] if args.recursive \
            else [p for pat in pats for p in sorted(src.glob(pat))]
    elif src.exists():
        files = [src]
    else:
        print(f"ERROR 找不到 {src}")
        return 1
    if not files:
        print("没有可审计的文件")
        return 1

    reports = [audit_one(f) for f in files]
    md = to_markdown(reports, files)
    print(md)
    if args.out:
        io.open(args.out, "w", encoding="utf-8").write(md)
        print(f"Markdown 已写出 {args.out}")
    if args.html:
        io.open(args.html, "w", encoding="utf-8").write(to_html(md, reports))
        print(f"HTML 已写出 {args.html}")

    return 1 if any(r["errors"] for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
