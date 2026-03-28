#!/usr/bin/env python3
"""
审计 X SearchTimeline 原始响应的解析覆盖率。

注意：
- 原始响应目录会累积同一 task_id 的多次运行/恢复历史文件。
- 因此“按 task 目录汇总的总推文数”不能直接等价于最终任务结果数。
- 本脚本关注的是“单个原始响应文件里可见的主结果推文，是否被 parser 全量解析”。

用法：
  python scripts/audit_x_raw_search_parser.py
  python scripts/audit_x_raw_search_parser.py --task-id 07cdf0eb-8c5f-44d4-822e-84ce843dbe1e
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from crawler.parser import parse_search_response


def _iter_search_files(base_dir: Path, task_id: str | None) -> list[Path]:
    if task_id:
        return sorted((base_dir / task_id).glob("page_*.json"))

    files: list[Path] = []
    for task_dir in sorted(base_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        files.extend(sorted(task_dir.glob("page_*.json")))
    return files


def _iter_instruction_entries(instruction: dict) -> list[dict]:
    entries: list[dict] = []
    raw_entries = instruction.get("entries", [])
    if isinstance(raw_entries, list):
        entries.extend(entry for entry in raw_entries if isinstance(entry, dict))
    raw_entry = instruction.get("entry")
    if isinstance(raw_entry, dict):
        entries.append(raw_entry)
    return entries


def _extract_reference_tweet_ids(payload: dict) -> tuple[list[str], Counter, Counter, Counter]:
    timeline = (
        payload.get("data", {})
        .get("search_by_raw_query", {})
        .get("search_timeline", {})
        .get("timeline", {})
    )
    instructions = timeline.get("instructions", [])

    instruction_types: Counter = Counter()
    entry_types: Counter = Counter()
    module_item_types: Counter = Counter()
    tweet_ids: list[str] = []

    for instruction in instructions:
        instruction_types[instruction.get("type") or "<missing>"] += 1
        for entry in _iter_instruction_entries(instruction):
            content = entry.get("content", {})
            entry_type = content.get("__typename") or "<missing>"
            entry_types[entry_type] += 1

            if entry_type == "TimelineTimelineItem":
                item_content = content.get("itemContent", {})
                if item_content.get("__typename") == "TimelineTweet":
                    tweet_id = _extract_tweet_id(item_content)
                    if tweet_id:
                        tweet_ids.append(tweet_id)
            elif entry_type == "TimelineTimelineModule":
                for item in content.get("items", []):
                    if not isinstance(item, dict):
                        continue
                    item_node = item.get("item", {}) if isinstance(item.get("item"), dict) else {}
                    item_content = item_node.get("itemContent") or item.get("itemContent") or {}
                    item_type = item_content.get("__typename") or "<missing>"
                    module_item_types[item_type] += 1
                    if item_type == "TimelineTweet":
                        tweet_id = _extract_tweet_id(item_content)
                        if tweet_id:
                            tweet_ids.append(tweet_id)

    return tweet_ids, instruction_types, entry_types, module_item_types


def _extract_tweet_id(item_content: dict) -> str:
    result = item_content.get("tweet_results", {}).get("result", {})
    if result.get("__typename") == "TweetWithVisibilityResults":
        result = result.get("tweet", {})
    legacy = result.get("legacy", {})
    return legacy.get("id_str") or result.get("rest_id", "")


def main() -> int:
    parser = argparse.ArgumentParser(description="审计 X SearchTimeline 原始响应解析覆盖率")
    parser.add_argument(
        "--raw-dir",
        default=str(ROOT / "backend" / "raw_responses"),
        help="原始响应根目录",
    )
    parser.add_argument("--task-id", help="仅审计指定 task_id")
    args = parser.parse_args()

    base_dir = Path(args.raw_dir)
    files = _iter_search_files(base_dir, args.task_id)
    if not files:
        print("未找到可审计的 SearchTimeline 原始响应文件。")
        return 1

    total_reference = 0
    total_parsed = 0
    mismatches: list[tuple[str, int, int]] = []
    instruction_types: Counter = Counter()
    entry_types: Counter = Counter()
    module_item_types: Counter = Counter()

    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        reference_ids, ins_counter, entry_counter, module_counter = _extract_reference_tweet_ids(payload)
        parsed_tweets, _, _ = parse_search_response(payload)
        parsed_ids = [tweet.get("id", "") for tweet in parsed_tweets if tweet.get("id")]

        instruction_types.update(ins_counter)
        entry_types.update(entry_counter)
        module_item_types.update(module_counter)
        total_reference += len(reference_ids)
        total_parsed += len(parsed_ids)

        if reference_ids != parsed_ids:
            mismatches.append((str(path), len(reference_ids), len(parsed_ids)))

    print(f"审计文件数: {len(files)}")
    print(f"原始可见推文数: {total_reference}")
    print(f"解析输出推文数: {total_parsed}")
    print(f"不一致文件数: {len(mismatches)}")
    print(f"instruction 类型分布: {dict(instruction_types)}")
    print(f"entry 内容类型分布: {dict(entry_types)}")
    if module_item_types:
        print(f"module item 类型分布: {dict(module_item_types)}")

    if mismatches:
        print("\n存在不一致文件：")
        for path, ref_count, parsed_count in mismatches[:20]:
            print(f"- {path}: raw={ref_count}, parsed={parsed_count}")
        return 2

    print("\n结论：当前审计范围内，SearchTimeline 原始响应里的主结果推文均已被解析。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
