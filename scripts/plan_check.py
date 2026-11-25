#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lean Answer 计划对账器 —— 把「我做完了」变成可验收的断言。

用法:
    python plan_check.py plan.json [--run] [--json]

plan.json 结构:
{
  "goal": "一句话目标",
  "tasks": [
    {"id": "T1", "do": "动作", "check": "完成判据（可执行或可观察）",
     "cmd": "python x.py f.svg",        # 可选，--run 时真跑
     "status": "DONE|FAILED|SKIPPED|UNVERIFIED",
     "evidence": "退出码/输出片段",     # DONE 必填
     "reason": "原因"}                  # FAILED/SKIPPED 必填
  ]
}

判定规则 (ERROR):
  1. 任务缺 check 字段 → 不可验收，属愿望不是任务
  2. status=DONE 但 evidence 为空/过短 → 声称完成但无证据
  3. status=FAILED/SKIPPED 但 reason 为空 → 失败无归因
  4. status 不在四态内
  5. --run 时 cmd 退出码非 0 → 强制改判 FAILED
退出码: 0 全部可宣称完成 / 1 存在 ERROR 或仍有 UNVERIFIED
"""

import json
import re
import subprocess
import sys

STATUSES = ("DONE", "FAILED", "SKIPPED", "UNVERIFIED")
MIN_EVIDENCE = 8


def run_cmd(cmd, timeout=120):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "").strip() or (p.stderr or "").strip()
        return p.returncode, out[:300]
    except subprocess.TimeoutExpired:
        return 124, f"超时 {timeout}s"
    except Exception as e:  # noqa: BLE001
        return 1, f"执行异常: {e}"


def main(path, do_run=False, as_json=False):
    plan = json.load(open(path, encoding="utf-8"))
    tasks = plan.get("tasks", [])
    errors = []

    for t in tasks:
        tid = t.get("id", "?")
        st = t.get("status", "UNVERIFIED").upper()
        t["status"] = st

        if do_run and t.get("cmd"):
            want = int(t.get("expect_rc", 0))
            rc, out = run_cmd(t["cmd"])
            t["evidence"] = f"exit={rc}（期望 {want}）| {out[:120] or '(无输出)'}"
            if rc != want:
                t["status"] = "FAILED"
                t["reason"] = t.get("reason") or f"命令退出码 {rc} ≠ 期望 {want}"
            else:
                t["status"] = "DONE"
        st = t["status"]

        if not t.get("check"):
            errors.append(f"{tid} 缺完成判据（check）——无法验收")
        if st not in STATUSES:
            errors.append(f"{tid} 状态非法: {st}")
        if st == "DONE" and len((t.get("evidence") or "").strip()) < MIN_EVIDENCE:
            errors.append(f"{tid} 声称 DONE 但无证据——须贴退出码或输出片段")
        if st == "DONE":
            ev = (t.get("evidence") or "")
            if re.search(r"已按要求|已完成|已修好|效果良好|应该可以|大概率", ev) and not re.search(r"\d", ev):
                errors.append(f"{tid} 证据是措辞不是证据：「{ev[:24]}」——须含数字/退出码/输出")
        if st in ("FAILED", "SKIPPED") and not (t.get("reason") or "").strip():
            errors.append(f"{tid} {st} 但无原因说明")

    cnt = {s: sum(1 for t in tasks if t["status"] == s) for s in STATUSES}
    total = len(tasks) or 1
    cov = cnt["DONE"] / total * 100

    if as_json:
        print(json.dumps({"counts": cnt, "coverage": round(cov, 1), "errors": errors},
                         ensure_ascii=False, indent=2))
    else:
        print(f"目标: {plan.get('goal', '(未填)')}")
        print(f"{'ID':<5}{'状态':<12}{'动作':<34}证据")
        print("-" * 78)
        for t in tasks:
            ev = (t.get("evidence") or t.get("reason") or "")[:26]
            print(f"{t.get('id','?'):<5}{t['status']:<12}{t.get('do','')[:32]:<34}{ev}")
        print("-" * 78)
        print(f"DONE {cnt['DONE']}/{total}  完成率 {cov:.0f}%  "
              f"FAILED {cnt['FAILED']}  SKIPPED {cnt['SKIPPED']}  UNVERIFIED {cnt['UNVERIFIED']}")
        for e in errors:
            print("ERROR", e)
        if errors or cnt["UNVERIFIED"]:
            print("\n结论: 不可宣称完成 —— 对外只能说「已做 X 项、未验证 Y 项」")
        else:
            print("\n结论: 全部任务带证据通过，可宣称完成")

    return 0 if (not errors and not cnt["UNVERIFIED"]) else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1], "--run" in sys.argv, "--json" in sys.argv))
