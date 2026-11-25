#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lean Answer 回归测试套件 —— 一条命令判定「改版有没有搞坏东西」。

用法:
    python scripts/regress.py           # 跑全部
    python scripts/regress.py -v        # 附每例输出

样本命名约定: <说明>_pass.* / <说明>_fail.*
  tests/svg/*.svg|*.html  → 交给 validate_svg.py
  tests/reply/*.txt       → 交给 lint_reply.py
  tests/style/*.md        → 交给 lint_style.py
预期退出码: _pass→0，_fail→1。不符即 FAIL（误报或漏检都算）。

退出码: 0 全过 / 1 有样本不符预期
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def expected_code(path: Path) -> int:
    stem = path.stem
    if stem.endswith("_pass"):
        return 0
    if stem.endswith("_fail"):
        return 1
    raise ValueError(f"样本命名须以 _pass/_fail 结尾: {path.name}")


def collect():
    items = []
    for p in sorted((ROOT / "tests" / "svg").iterdir()):
        if p.suffix in (".svg", ".html"):
            items.append((p, "validate_svg.py"))
    for p in sorted((ROOT / "tests" / "reply").iterdir()):
        if p.suffix == ".txt":
            items.append((p, "lint_reply.py"))
    plan_dir = ROOT / "tests" / "plan"
    if plan_dir.is_dir():
        for p in sorted(plan_dir.iterdir()):
            if p.suffix == ".json":
                items.append((p, "plan_check.py"))
    style_dir = ROOT / "tests" / "style"
    if style_dir.is_dir():
        for p in sorted(style_dir.iterdir()):
            if p.suffix not in (".md", ".txt"):
                continue
            items.append((p, "lint_style.py"))
    deai_dir = ROOT / "tests" / "deai"
    if deai_dir.is_dir():
        for p in sorted(deai_dir.iterdir()):
            if p.suffix in (".md", ".txt"):
                items.append((p, "deai.py"))

    for extra in ("readme",):
        d = ROOT / "tests" / extra
        if d.is_dir():
            for p in sorted(d.iterdir()):
                if p.suffix in (".md", ".txt"):
                    items.append((p, "lint_style.py"))

    audit_dir = ROOT / "tests" / "audit"
    if audit_dir.is_dir():
        for p in sorted(audit_dir.iterdir()):
            if p.suffix in (".md", ".txt"):
                items.append((p, "audit.py"))

    log_dir = ROOT / "tests" / "runlog"
    if log_dir.is_dir():
        for p in sorted(log_dir.iterdir()):
            if p.suffix == ".jsonl":
                items.append((p, "runlog.py"))
    return items


GATE_CASES = [
    (["tests/reply/decide_pass.txt", "tests/svg/good_pass.svg",
      "tests/plan/all_evidenced_pass.json"], 0, "全过应放行"),
    (["tests/reply/decide_pass.txt", "tests/reply/multi_topic_fail.txt"], 1, "含违规应拦下"),
    (["tests/runlog/healthy_pass.jsonl"], 0, "台账健康应放行"),
]


def gate_smoke():
    """元测试：闸门本身的分发与退出码是否正确。"""
    bad = []
    for args, want, why in GATE_CASES:
        r = subprocess.run([sys.executable, str(SCRIPTS / "gate.py")]
                           + [str(ROOT / a) for a in args],
                           capture_output=True, text=True)
        ok = r.returncode == want
        print(f"{'OK  ' if ok else 'MISMATCH'} gate/{args[-1].split('/')[-1]:<32} "
              f"期望 exit={want} 实得 {r.returncode}  ({why})")
        if not ok:
            bad.append("gate:" + args[-1].split("/")[-1])
    return bad


def main(verbose=False):
    items = collect()
    if not items:
        print("未找到测试样本")
        return 1
    bad = gate_smoke()
    for path, script in items:
        want = expected_code(path)
        r = subprocess.run([sys.executable, str(SCRIPTS / script), str(path)],
                           capture_output=True, text=True)
        ok = r.returncode == want
        tag = "OK  " if ok else "MISMATCH"
        print(f"{tag} {path.parent.name}/{path.name:<32} 期望 exit={want} 实得 {r.returncode}")
        if verbose or not ok:
            for line in (r.stdout or r.stderr).strip().splitlines()[-3:]:
                print("      " + line)
        if not ok:
            bad.append(path.name)

    total = len(items) + len(GATE_CASES)
    print("-" * 66)
    print(f"{total - len(bad)}/{total} 项判定符合预期（样本 {len(items)} + 闸门 {len(GATE_CASES)}）")
    if bad:
        print("不符: " + ", ".join(bad))
        return 1
    print("REGRESSION PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main("-v" in sys.argv))
