#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布流水线：版本一致性 → 回归 → bump → 打包 → 打印市场表单文案。

用法：
    python scripts/release.py --check-only          # 只校验当前状态
    python scripts/release.py --version 2.9.0       # 正式发版（会改 SKILL.md 版本号）
    python scripts/release.py --version 2.9.0 --out D:/dist

退出码：0 全部通过；1 任一环节失败。
"""
from __future__ import annotations

import argparse
import datetime
import io
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "SKILL.md"
CHANGELOG = ROOT / "CHANGELOG.md"
MARKET = ROOT / "MARKET.md"
PACKAGER = Path(
    r"C:/Users/1/.workbuddy/plugins/cache/cb_teams_marketplace/skill-creator"
    r"/unknown/scripts/package_skill.py"
)
DESC_LIMIT = 200


def fail(msg: str) -> None:
    print(f"ERROR {msg}")
    sys.exit(1)


def parse_frontmatter(text: str) -> dict:
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        fail("SKILL.md 缺 frontmatter")
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta


def changelog_body(version: str) -> str:
    """取 CHANGELOG 中指定版本的段落正文。"""
    text = io.open(CHANGELOG, encoding="utf-8").read()
    pat = re.compile(rf"^## {re.escape(version)}\b.*?$(.*?)(?=^## |\Z)", re.M | re.S)
    m = pat.search(text)
    return m.group(1).strip() if m else ""


def market_field(label: str) -> str:
    """从 MARKET.md 抓 `- **label**：value` 或引用块描述。"""
    text = io.open(MARKET, encoding="utf-8").read()
    if label == "描述":
        # 取描述行之后的第一个引用块
        blocks = re.findall(r"^>\s*(.+?)$", text, re.M)
        for b in blocks:
            if len(b) > 40:
                return b.strip()
        fail("MARKET.md 里找不到描述引用块")
    m = re.search(rf"\*\*{label}\*\*：(.+)$", text, re.M)
    return m.group(1).strip().strip("`") if m else ""


def run(cmd: list[str], label: str) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    if r.returncode != 0:
        print(f"--- {label} 输出 ---")
        print(out[-2000:] if out else "(空)")
        if err:
            print(err[-800:])
        fail(f"{label} 失败（退出码 {r.returncode}）")
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", help="目标版本号，如 2.9.0")
    ap.add_argument("--check-only", action="store_true", help="只校验，不改文件")
    ap.add_argument("--out", default=str(Path.home() / "WorkBuddy"),
                    help="zip 输出目录（默认 ~/WorkBuddy，不要指向 skill 目录自身）")
    args = ap.parse_args()

    text = io.open(SKILL, encoding="utf-8").read()
    meta = parse_frontmatter(text)
    cur = meta.get("version", "?")
    print(f"当前版本 {cur}")

    # 1 市场文案
    if not MARKET.exists():
        fail("缺 MARKET.md（市场表单的唯一真源）")
    desc = market_field("描述")
    cjk = len(re.sub(r"\s", "", desc))
    if cjk > DESC_LIMIT:
        fail(f"MARKET.md 描述 {cjk} 字，超上限 {DESC_LIMIT}")
    print(f"描述长度 {cjk}/{DESC_LIMIT} 字")

    if args.check_only:
        body = changelog_body(cur)
        if not body:
            fail(f"CHANGELOG 缺 {cur} 段落")
        print(f"CHANGELOG {cur} 段落 {len(body)} 字")
        print("CHECK OK")
        return 0

    if not args.version:
        fail("需要 --version（或用 --check-only 只校验）")
    ver = args.version.strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", ver):
        fail(f"版本号格式应为 X.Y.Z，收到 {ver}")
    body = changelog_body(ver)
    if not body:
        fail(f"CHANGELOG 里没有 ## {ver} 段落——先写变更记录再发版")

    # 1.5 主文件体积守门（每轮注入成本）
    skill_chars = len(io.open(SKILL, encoding="utf-8").read())
    if skill_chars > 4000:
        fail(f"SKILL.md {skill_chars} 字，超 4000 上限——细节移到 references 再发版")
    print(f"主文件 {skill_chars} 字（上限 4000）")

    # 1.6 描述与 SKILL.md 不脱节（两处都讲三档才发）
    d = parse_frontmatter(io.open(SKILL, encoding="utf-8").read()).get("description", "")
    if len(d) > 1024:
        fail(f"frontmatter description {len(d)} 字，超平台上限 1024")
    print(f"description {len(d)}/1024 字")

    # 2 回归（跑在 bump 之前，用当前代码）
    print("跑回归…")
    r = run([sys.executable, "scripts/regress.py"], "回归")
    tail = r.stdout.strip().splitlines()[-2:]
    for line in tail:
        print(f"  {line}")

    # 3 bump 版本号与日期
    if cur != ver:
        text = re.sub(r"^version: .*$", f"version: {ver}", text, count=1, flags=re.M)
        text = re.sub(r"^updated: .*$",
                      f"updated: {datetime.date.today().isoformat()}",
                      text, count=1, flags=re.M)
        io.open(SKILL, "w", encoding="utf-8").write(text)
        print(f"版本 {cur} → {ver}")
    else:
        print("版本号未变")

    # 4 打包（临时目录不进包）
    tmp = ROOT / ".outbox"
    if tmp.exists():
        shutil.rmtree(tmp)
    out_dir = Path(args.out)
    if not PACKAGER.exists():
        fail(f"找不到打包脚本 {PACKAGER}")
    run([sys.executable, str(PACKAGER), str(ROOT), str(out_dir)], "打包")

    zpath = out_dir / f"{meta.get('name', 'skill')}.zip"
    if not zpath.exists():
        fail(f"打包后未见 {zpath}")
    names = zipfile.ZipFile(zpath).namelist()
    size_kb = round(zpath.stat().st_size / 1024, 1)

    # 5 打印表单
    print()
    print("=" * 62)
    print("市场发布表单（直接复制）")
    print("=" * 62)
    print(f"Slug：{meta.get('name')}")
    print(f"显示名称：{market_field('显示名称')}")
    print(f"版本号：{ver}")
    print(f"分类：{market_field('分类')}")
    print()
    print("描述：")
    print(desc)
    print()
    print("变更说明：")
    print(body)
    print()
    print(f"包：{zpath} ｜ {len(names)} 个文件 ｜ {size_kb} KB")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
