#!/usr/bin/env python3
"""Check what Claude wrote in the prepare job and build the comparison folders (build_pairs.py).

Reads work/choice.json, work/pairs.csv (all paired problems), work/parity_ids.txt
(the human parity set, when Claude found a list) and work/datasets/ (from fetch.sh).
Keeps only the human parity set:
  full                                 all pairs
  adapter_file|registry|hf_runs|readme the pairs whose original_id is in parity_ids.txt
  sample                               parity_size pairs drawn with random seed 0
Writes compare/auto/<task>, compare/human/<task>, compare/pairs.csv and compare/meta.json.
Always exits 0 and writes status=ok|no_human_adapter|failed to $GITHUB_OUTPUT,
so the report job can explain a failure.
"""
import argparse
import csv
import json
import os
import random
import re
import shutil
import sys
from pathlib import Path

STATUSES = {"ok", "no_human_adapter", "failed"}
PARITY_SOURCES = {"full", "adapter_file", "registry", "hf_runs", "readme", "sample"}
SAMPLE_SEED = 0
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
TEXT_FIELDS = [
    "reason", "benchmark", "original_repo", "auto_adapter", "auto_dataset", "human_adapter",
    "human_adapter_reason", "human_dataset", "parity_source", "parity_note", "pairing_rule", "notes",
]


def load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def clean_choice(raw):
    """Keep only known fields with simple types."""
    choice = {"status": raw.get("status") if raw.get("status") in STATUSES else "failed"}
    for key in TEXT_FIELDS:
        value = raw.get(key)
        choice[key] = str(value)[:2000] if value is not None else ""
    for key in ("auto_dataset_pr", "parity_size"):
        value = raw.get(key)
        choice[key] = value if isinstance(value, int) and not isinstance(value, bool) else None
    if raw.get("status") not in STATUSES:
        choice["reason"] = f"choice.json has an unknown status: {raw.get('status')!r}"
    return choice


def select_parity(pairs, choice, work):
    """Return (the pairs in the human parity set, notes for meta.json)."""
    source = choice.get("parity_source")
    if source not in PARITY_SOURCES:
        raise ValueError(f"parity_source must be one of {sorted(PARITY_SOURCES)}, not {source!r}")
    if source == "full":
        return pairs, {}
    if source == "sample":
        size = choice.get("parity_size")
        if not size or size <= 0:
            raise ValueError("parity_source is sample but parity_size is not a positive integer")
        ordered = sorted(pairs, key=lambda row: row["original_id"])
        if size >= len(ordered):
            return ordered, {"parity_sample_note": f"parity_size {size} >= {len(ordered)} pairs; all used"}
        chosen = random.Random(SAMPLE_SEED).sample(ordered, size)
        return sorted(chosen, key=lambda row: row["original_id"]), {"parity_sample_seed": SAMPLE_SEED}
    path = Path(work) / "parity_ids.txt"
    if not path.is_file():
        raise ValueError(f"parity_source is {source} but work/parity_ids.txt is missing")
    listed = list(dict.fromkeys(line.strip() for line in path.read_text().splitlines() if line.strip()))
    if not listed:
        raise ValueError("work/parity_ids.txt is empty")
    wanted = set(listed)
    kept = [row for row in pairs if row["original_id"] in wanted]
    paired = {row["original_id"] for row in pairs}
    not_paired = [i for i in listed if i not in paired]
    if not kept:
        raise ValueError(f"no paired problem is in parity_ids.txt (e.g. {listed[:3]})")
    return kept, {"parity_listed": len(listed), "parity_not_paired": len(not_paired),
                  "parity_not_paired_examples": not_paired[:10]}


def read_pairs(path):
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or [n.strip() for n in reader.fieldnames] != [
            "original_id", "auto_task", "human_task"
        ]:
            raise ValueError("pairs.csv header must be original_id,auto_task,human_task")
        rows = [{k.strip(): (v or "").strip() for k, v in row.items()} for row in reader]
    if not rows:
        raise ValueError("pairs.csv has no rows")
    for column in ("original_id", "auto_task", "human_task"):
        values = [row[column] for row in rows]
        if any(not v for v in values):
            raise ValueError(f"pairs.csv has an empty {column}")
        if len(set(values)) != len(values):
            raise ValueError(f"pairs.csv repeats a value in {column}")
    for row in rows:
        for column in ("auto_task", "human_task"):
            if not NAME.match(row[column]):
                raise ValueError(f"bad task folder name in pairs.csv: {row[column]!r}")
    return rows


def task_folders(root):
    return sorted(p.name for p in Path(root).iterdir() if (p / "task.toml").is_file())


def build(work, out):
    work, out = Path(work), Path(out)
    meta = {"status": "failed", "reason": ""}
    raw = load_json(work / "choice.json")
    if not isinstance(raw, dict):
        meta["reason"] = "Claude did not write a valid work/choice.json"
        return meta
    meta.update(clean_choice(raw))
    if meta["status"] != "ok":
        meta["reason"] = meta["reason"] or f"Claude stopped with status {meta['status']}"
        return meta

    sides = {}
    for side in ("auto", "human"):
        info = load_json(work / "datasets" / f"{side}.json")
        if not isinstance(info, dict) or not NAME.match(str(info.get("folder", ""))):
            meta.update(status="failed", reason=f"the {side} dataset was not fetched")
            return meta
        root = work / "datasets" / side / info["folder"]
        if not root.is_dir():
            meta.update(status="failed", reason=f"work/datasets/{side}/{info['folder']} is missing")
            return meta
        sides[side] = (info, root)

    try:
        pairs = read_pairs(work / "pairs.csv")
    except (OSError, ValueError) as e:
        meta.update(status="failed", reason=f"pairs.csv: {e}")
        return meta

    for side, (info, root) in sides.items():
        available = set(task_folders(root))
        missing = [row[f"{side}_task"] for row in pairs if row[f"{side}_task"] not in available]
        if missing:
            meta.update(status="failed",
                        reason=f"{len(missing)} {side} tasks in pairs.csv do not exist, e.g. {missing[:3]}")
            return meta
        meta[f"{side}_dataset_commit"] = info.get("commit")
        meta[f"{side}_task_count"] = len(available)

    meta["paired_all_count"] = len(pairs)
    try:
        pairs, notes = select_parity(pairs, meta, work)
    except ValueError as e:
        meta.update(status="failed", reason=f"parity set: {e}")
        return meta
    meta.update(notes)

    for side, (info, root) in sides.items():
        dest = out / side
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        for row in pairs:
            name = row[f"{side}_task"]
            shutil.copytree(root / name, dest / name, symlinks=True)

    with open(out / "pairs.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["original_id", "auto_task", "human_task"])
        writer.writeheader()
        writer.writerows(pairs)
    if (work / "parity_ids.txt").is_file():
        shutil.copy(work / "parity_ids.txt", out / "parity_ids.txt")
    meta["paired_count"] = len(pairs)
    meta["status"] = "ok"
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", default="work")
    ap.add_argument("--out", default="compare")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = build(args.work, out)
    inputs = load_json(Path(args.work) / "inputs.json")
    if isinstance(inputs, dict):
        meta["pr_number"] = inputs.get("pr_number")
        meta["pr_sha"] = inputs.get("pr_sha")
    adapters_commit = Path(args.work) / "adapters.commit"
    if adapters_commit.is_file():
        meta["adapters_commit"] = adapters_commit.read_text().strip()
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    print(f"status={meta['status']}" + (f" ({meta['reason']})" if meta.get("reason") else ""))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"status={meta['status']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
