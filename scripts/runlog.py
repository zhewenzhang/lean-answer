#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""周期任务台账 —— 防「机械重复同一错误」。

用法:
    python runlog.py <log.jsonl>                                     # 只判定
    python runlog.py <log.jsonl> --append --status OK --sig "src=2;items=8" --note "..."

判定规则:
  1. 末轮 FAILED 且与上轮同 status + 同 sig → ESCALATE（连续同因失败，禁止原样重跑）
  2. 末轮 OK 但 sig 为空或 items=0      → ERROR 空结果不等于成功
  3. 连续 ≥3 轮 OK 且 sig 完全相同        → WARN 疑似空转
  4. 仅 1 轮 FAILED                      → HINT 可换方法重试一次
退出码: 0 可继续执行 / 1 须升级或本轮不达标
"""

import json
import os
import sys
from datetime import datetime


def load(path):
    if not os.path.exists(path):
        return []
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main(path, argv):
    rows = load(path)

    if "--append" in argv:
        rec = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "task": _val(argv, "--task") or "未命名",
            "status": (_val(argv, "--status") or "OK").upper(),
            "sig": _val(argv, "--sig") or "",
            "note": _val(argv, "--note") or "",
        }
        if rec["status"] not in ("OK", "FAILED", "SKIPPED"):
            print(f"ERROR 状态非法: {rec['status']}")
            return 1
        rows.append(rec)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    if not rows:
        print("台账为空：先 --append 记录一轮")
        return 1

    print(f"任务: {rows[-1].get('task', '?')}   共 {len(rows)} 轮")
    print(f"{'时间':<18}{'状态':<9}{'签名':<24}备注")
    print("-" * 78)
    for r in rows[-8:]:
        print(f"{r.get('ts',''):<18}{r.get('status',''):<9}{r.get('sig','')[:22]:<24}{r.get('note','')[:20]}")

    last, prev = rows[-1], (rows[-2] if len(rows) > 1 else None)
    problems, hints = [], []

    sig = (last.get("sig") or "").strip()
    if last["status"] == "OK" and (not sig or "items=0" in sig.replace(" ", "")):
        problems.append("末轮 OK 但签名为空或 items=0 —— 空结果不等于成功，须确认是「确实没有」还是「读不到来源」")

    if last["status"] == "FAILED":
        if prev and prev.get("status") == "FAILED" and prev.get("sig") == last.get("sig"):
            problems.append(
                f"ESCALATE 连续 2 轮同一原因失败（sig={sig or '空'}）——禁止原样重跑第 3 轮，须改方案或暂停并报障"
            )
        elif prev:
            hints.append("本轮失败、上轮不同因：诊断根因 + 换方法重试一次")

    tail_ok = [r for r in rows[-3:] if r.get("status") == "OK"]
    if len(tail_ok) == 3 and len({r.get("sig") for r in tail_ok}) == 1:
        hints.append("连续 3 轮签名完全相同——疑似空转，检查数据源是否真的在更新")

    for h in hints:
        print("HINT ", h)
    for p in problems:
        print("ERROR", p)
    if problems:
        print(f"\n结论: 须升级处理，不可照原样继续（共 {len(problems)} 项）")
        return 1
    print("\n结论: 本轮可接受，继续按计划执行")
    return 0


def _val(argv, key):
    return argv[argv.index(key) + 1] if key in argv else ""


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1], sys.argv[2:]))
