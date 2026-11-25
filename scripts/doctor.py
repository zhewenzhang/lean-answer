#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doctor：装完先跑这一条，看哪一环没通、怎么修。

12 项自检分四组：文件完整性、脚本可执行、规则可回归、宿主接入。
输出直接可读：每项 PASS / FAIL / SKIP，FAIL 附修复命令。退出码 0 全通，1 有 FAIL。

用法：
    python scripts/doctor.py            # 全量自检
    python scripts/doctor.py --brief    # 只输出汇总与失败项
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

results: list[tuple[str, str, str, str]] = []  # (组, 项, 状态, 说明)


def add(group: str, name: str, ok: bool | None, detail: str = "") -> None:
    state = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
    results.append((group, name, state, detail))


def run(script: str, *args: str) -> tuple[int, str]:
    p = subprocess.run([PY, str(ROOT / "scripts" / script), *args],
                       cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 1 文件完整性 ────────────────────────────────────────────
def check_files() -> None:
    need = ["SKILL.md", "README.md", "LICENSE", "CHANGELOG.md", "MARKET.md",
            "references/anti-ai-style.md", "references/gotchas.md",
            "scripts/gate.py", "scripts/lint_reply.py", "scripts/lint_style.py",
            "scripts/deai.py", "scripts/validate_svg.py", "scripts/regress.py",
            "scripts/release.py"]
    missing = [p for p in need if not (ROOT / p).exists()]
    add("文件", f"核心文件 {len(need)} 个", not missing,
        "缺 " + ", ".join(missing) if missing else "齐全")

    skill = io.open(ROOT / "SKILL.md", encoding="utf-8").read()
    m = re.search(r"^version:\s*(\S+)", skill, re.M)
    add("文件", "frontmatter 版本号", bool(m), m.group(1) if m else "缺 version 字段")

    size = len(skill)
    add("文件", f"主文件体积 {size} 字", size < 4000,
        "超过 4000 字会拖慢每轮注入，把细节移到 references" if size >= 4000 else "在舒适区间")


def check_docs_linked() -> None:
    """主文件没引用的 references，用户永远读不到。"""
    skill = io.open(ROOT / "SKILL.md", encoding="utf-8").read()
    refs = sorted(p.name for p in (ROOT / "references").glob("*.md"))
    orphans = [r for r in refs if r not in skill]
    add("文件", f"references 互引 {len(refs) - len(orphans)}/{len(refs)}",
        not orphans, "未在主文件出现：" + "、".join(orphans) if orphans else "全部可达")


# ── 2 脚本可执行 ────────────────────────────────────────────
# 每个脚本的冒烟用例：用一个已知达标样本喂进去，只看「能跑起来且结论正确」
SMOKE = {
    "gate.py": ("tests/reply/report_pass.txt", 0),
    "lint_reply.py": ("tests/reply/report_pass.txt", 0),
    "lint_style.py": ("tests/style/ai_tone_pass.md", 0),
    "deai.py": ("tests/deai/clean_pass.md", 0),
    "validate_svg.py": ("tests/svg/good_pass.svg", 0),
    "plan_check.py": ("tests/plan/all_evidenced_pass.json", 0),
    "runlog.py": ("tests/runlog/healthy_pass.jsonl", 0),
    "regress.py": (None, 0),
}


def check_scripts() -> None:
    for s, (sample, want) in SMOKE.items():
        if sample and not (ROOT / sample).exists():
            add("脚本", s, None, f"缺冒烟样本 {sample}")
            continue
        args = () if not sample else (str(ROOT / sample),)
        try:
            rc, out = run(s, *args)
            ok = rc == want
            tail = [l for l in out.strip().splitlines() if l.strip()]
            add("脚本", s, ok, (tail[-1][:60] if tail else "") or f"exit={rc}")
        except Exception as e:  # noqa: BLE001
            add("脚本", s, False, str(e)[:70])


# ── 3 规则可回归 ────────────────────────────────────────────
def check_regression() -> str:
    rc, out = run("regress.py")
    tail = [l for l in out.strip().splitlines() if "项判定" in l]
    line = tail[-1] if tail else out.strip()[-70:]
    add("回归", "样本判定", rc == 0, line)

    n = len(list((ROOT / "tests").rglob("*"))) if (ROOT / "tests").exists() else 0
    add("回归", f"样本总数 {n}", n >= 30, "少于 30 个样本，规则改动无从验证" if n < 30 else "足够")

    # 闸门串联：达标的要放行，违规的要拦下
    good = ROOT / "tests" / "reply" / "report_pass.txt"
    bad = ROOT / "tests" / "reply" / "opening_meta_fail.txt"
    if good.exists() and bad.exists():
        rc1, _ = run("gate.py", str(good), "--quiet")
        rc2, _ = run("gate.py", str(bad), "--quiet")
        add("回归", "闸门放行/拦截", rc1 == 0 and rc2 == 1,
            f"达标稿 exit={rc1}（应 0）、违规稿 exit={rc2}（应 1）")
    else:
        add("回归", "闸门放行/拦截", None, "缺基本样本")
    return line


# ── 4 宿主接入 ──────────────────────────────────────────────
def check_host() -> None:
    # 4.1 用户级 skills 目录
    home = Path.home()
    installed = home / ".workbuddy" / "skills" / "lean-answer"
    add("接入", "用户级安装路径", installed.exists(),
        str(installed) if installed.exists() else f"未安装到 {installed}")

    # 4.2 是否被全局规则强制引用（记忆文件）
    mem_hits = []
    for cand in home.glob(".workbuddy/*/MEMORY.md"):
        try:
            if "lean-answer" in io.open(cand, encoding="utf-8").read():
                mem_hits.append(cand.name)
        except OSError:
            continue
    add("接入", "全局记忆引用", bool(mem_hits),
        f"命中 {len(mem_hits)} 处" if mem_hits else "未在任何 MEMORY.md 引用，新对话可能不触发")

    # 4.3 描述里是否含触发词
    skill = io.open(ROOT / "SKILL.md", encoding="utf-8").read()
    trig = ["说重点", "TL;DR", "concise", "去 AI 味", "别废话"]
    hit = [t for t in trig if t in skill[:1600]]
    add("接入", f"触发词 {len(hit)}/{len(trig)}", len(hit) >= 4,
        "缺 " + "、".join(t for t in trig if t not in hit) if len(hit) < 4 else "覆盖常见说法")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", action="store_true", help="只输出汇总与失败项")
    args = ap.parse_args()

    check_files()
    check_docs_linked()
    check_scripts()
    check_regression()
    check_host()

    fails = [r for r in results if r[2] == "FAIL"]
    skips = [r for r in results if r[2] == "SKIP"]
    passes = [r for r in results if r[2] == "PASS"]

    if not args.brief:
        cur = None
        for g, name, state, detail in results:
            if g != cur:
                print(f"\n[{g}]")
                cur = g
            mark = {"PASS": "OK  ", "FAIL": "FAIL", "SKIP": "SKIP"}[state]
            print(f"  {mark} {name:<28} {detail}")

    print()
    print("-" * 58)
    print(f"体检结果：{len(passes)} 通过 / {len(fails)} 失败 / {len(skips)} 跳过（共 {len(results)} 项）")
    if fails:
        print("\n需要修：")
        for g, name, _, detail in fails:
            print(f"  - [{g}] {name}：{detail}")
        print("\n常见原因与修法：")
        print("  回归失败 → python scripts/regress.py -v 看具体样本，修脚本不改预期")
        print("  脚本不可跑 → 检查 Python 版本（需 3.9+）与文件是否完整")
        print("  未安装 → 解压 zip 到 ~/.workbuddy/skills/ 后再跑本命令")
        return 1
    print("\n全部通过，可以正常使用。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
