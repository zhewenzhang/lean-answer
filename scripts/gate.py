# -*- coding: utf-8 -*-
"""gate.py — 单一校验闸门：自动识别文件类型并送到对应校验器。

用法：
    python scripts/gate.py 回复.txt 图.svg 计划.json 台账.jsonl
    python scripts/gate.py tests/            # 目录递归
    python scripts/gate.py --quiet 某文件     # 只输出失败项

退出码：0 = 全过；1 = 有 ERROR。
设计意图：把「要记得跑四个脚本」降为一件事。脚本越多，越容易被绕过。
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

DISPATCH = {
    ".svg": ["validate_svg.py"],
    ".html": ["validate_svg.py"],
    ".txt": ["lint_reply.py", "lint_style.py"],   # 精简 + 去 AI 味，两道都过
    ".md": ["lint_reply.py", "lint_style.py"],
    ".jsonl": ["runlog.py"],
    ".json": ["plan_check.py"],   # 计划对账；台账请用 .jsonl
}


def classify(p: Path):
    """返回 (脚本列表, 说明) 或 (None, 原因)。"""
    ext = p.suffix.lower()
    if ext not in DISPATCH:
        return None, "跳过：未知类型"
    return DISPATCH[ext], ""


def run_one(script: str, p: Path):
    cmd = [sys.executable, str(HERE / script), str(p)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
    except Exception as e:                       # noqa: BLE001
        return "ERROR", f"执行失败：{e}"
    out = (r.stdout or "") + (r.stderr or "")
    tail = ""
    for line in reversed(out.strip().splitlines()):
        if line.strip():
            tail = line.strip()
            break
    return ("PASS" if r.returncode == 0 else "FAIL"), tail


def collect(targets):
    files = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            files.extend(sorted(x for x in p.rglob("*") if x.is_file()))
        elif p.is_file():
            files.append(p)
        else:
            print(f"[MISS] {t} 不存在")
    return files


def main(argv):
    quiet = "--quiet" in argv
    targets = [a for a in argv if not a.startswith("--")]
    if not targets:
        print(__doc__)
        return 0

    files = collect(targets)
    if not files:
        print("没有可校验的文件")
        return 1

    rows, n_fail, n_skip = [], 0, 0
    for f in files:
        scripts, why = classify(f)
        if not scripts:
            n_skip += 1
            if not quiet:
                print(f"  - {f.name:<34} {why}")
            continue
        for script in scripts:
            status, tail = run_one(script, f)
            if status == "FAIL":
                n_fail += 1
            rows.append((f.name, script, status, tail))
            if not quiet or status == "FAIL":
                print(f"  {status:<4} {f.name:<34} [{script}] {tail[:90]}")

    passed = sum(1 for r in rows if r[2] == "PASS")
    print(f"\n闸门：{passed}/{len(rows)} 通过，{n_fail} 失败，{n_skip} 跳过")
    if n_fail:
        print("结论：FAIL — 存在 ERROR，不得直接发出/交付，先修。")
        return 1
    print("结论：PASS — 可以发出。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
