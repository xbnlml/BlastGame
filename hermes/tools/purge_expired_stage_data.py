#!/usr/bin/env python3
"""按 bot logic cutoff 清理 stage-data 派生缓存中的过期记录。

只处理 stage-data/<level>/*.json，按 created_at/createdAt 逐条删除早于 cutoff
的记录；没有可解析时间的记录保留并报告。原始 telemetry/optimizer 批次不触碰。
默认 dry-run，必须显式 --apply 才写入。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

HERMES = Path(__file__).resolve().parents[1]
STAGE_ROOT = HERMES / "stage-data"
BACKUP_ROOT = HERMES / "backups"
DEFAULT_CUTOFF = "2026-08-13T14:36:00+08:00"


def parse_levels(spec: str) -> list[int]:
    out: set[int] = set()
    for raw in str(spec).split(","):
        part = raw.strip()
        if not part:
            continue
        if "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
            out.update(range(a, b + 1))
        else:
            out.add(int(part))
    return sorted(out)


def parse_time(value: Any) -> dt.datetime | None:
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).strip()
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone(dt.timedelta(hours=8)))
    return parsed.astimezone(dt.timezone.utc)


def classify(record: dict[str, Any], cutoff: dt.datetime) -> str:
    raw = record.get("created_at", record.get("createdAt"))
    parsed = parse_time(raw)
    if parsed is None:
        return "unknown"
    return "expired" if parsed < cutoff else "fresh"


def filter_node(node: Any, cutoff: dt.datetime, stats: dict[str, int]) -> Any:
    if isinstance(node, list):
        kept = []
        for item in node:
            if isinstance(item, dict) and ("created_at" in item or "createdAt" in item):
                kind = classify(item, cutoff)
                stats[kind] += 1
                if kind == "expired":
                    continue
                kept.append(item)
            else:
                kept.append(filter_node(item, cutoff, stats))
        return kept
    if isinstance(node, dict):
        return {key: filter_node(value, cutoff, stats) for key, value in node.items()}
    return node


def iter_level_files(levels: list[int]):
    for level in levels:
        directory = STAGE_ROOT / str(level)
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            yield level, path


def inspect(levels: list[int], cutoff: dt.datetime):
    rows = []
    totals = {"files": 0, "changed_files": 0, "expired": 0, "fresh": 0, "unknown": 0}
    for level, path in iter_level_files(levels):
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"读取失败 {path}: {exc}") from exc
        stats = {"expired": 0, "fresh": 0, "unknown": 0}
        filtered = filter_node(data, cutoff, stats)
        totals["files"] += 1
        totals["expired"] += stats["expired"]
        totals["fresh"] += stats["fresh"]
        totals["unknown"] += stats["unknown"]
        changed = stats["expired"] > 0
        if changed:
            totals["changed_files"] += 1
        rows.append((level, path, data, filtered, stats, changed))
    return rows, totals


def backup_file(path: Path, root: Path) -> Path:
    relative = path.relative_to(HERMES)
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    if not target.exists() or target.stat().st_size != path.stat().st_size:
        raise RuntimeError(f"备份验证失败: {target}")
    return target


def write_json_atomic(path: Path, data: Any) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def main() -> int:
    parser = argparse.ArgumentParser(description="清理 stage-data cutoff 前的派生记录")
    parser.add_argument("--levels", required=True, help="关卡列表/区间")
    parser.add_argument("--cutoff", default=DEFAULT_CUTOFF, help="ISO 时间，默认 2026-08-13T14:36+08:00")
    parser.add_argument("--apply", action="store_true", help="实际写入；默认 dry-run")
    args = parser.parse_args()

    cutoff = parse_time(args.cutoff)
    if cutoff is None:
        parser.error(f"非法 cutoff: {args.cutoff}")
    levels = parse_levels(args.levels)
    rows, totals = inspect(levels, cutoff)
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"{mode}: cutoff={args.cutoff}")
    print(
        f"文件={totals['files']}，将修改={totals['changed_files']}，"
        f"过期记录={totals['expired']}，保留新记录={totals['fresh']}，"
        f"未知时间保留={totals['unknown']}"
    )
    for level, path, _data, _filtered, stats, changed in rows:
        if changed:
            print(f"  L{level} {path.name}: 删除{stats['expired']} / 保留{stats['fresh']} / 未知{stats['unknown']}")

    if not args.apply:
        return 0

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = BACKUP_ROOT / f"purge_expired_stage_data_{stamp}"
    changed = 0
    for _level, path, _data, filtered, _stats, should_change in rows:
        if not should_change:
            continue
        backup_file(path, backup_root)
        write_json_atomic(path, filtered)
        with path.open(encoding="utf-8") as handle:
            json.load(handle)
        changed += 1
    print(f"已修改 {changed} 个文件，备份: {backup_root}")

    after_rows, after = inspect(levels, cutoff)
    if after["expired"] != 0:
        raise RuntimeError(f"回读验证失败：仍有 {after['expired']} 条过期记录")
    if after["fresh"] != totals["fresh"] or after["unknown"] != totals["unknown"]:
        raise RuntimeError(
            f"回读验证失败：新记录 {totals['fresh']}->{after['fresh']}，"
            f"未知记录 {totals['unknown']}->{after['unknown']}"
        )
    print(f"✅ stage-data 验证通过：过期=0，新记录={after['fresh']}，未知保留={after['unknown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
