#!/usr/bin/env python3
"""Compute the comparison numbers from the Harbor jobs.

Reads compare/pairs.csv and every trial result.json under --jobs
(<anything>/<side>-<run>/<trial>/result.json). Writes to --out:
  stats.json   per-run scores, kept runs, mean ± SEM, ranges, overlap, rule verdict
  pertask.csv  per pair: passes and failures on each side

Scores are percentages: 100 * (sum of rewards over the paired tasks) / (number of pairs).
A paired task with no trial or no reward counts as 0 and as a failed trial.
Per side, the highest and the lowest agent runs are dropped; mean ± SEM uses the rest.
"""
import argparse
import csv
import json
import math
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

JOB = re.compile(r"(auto|human)-(run[0-9]+)")
SIDES = ("auto", "human")


def read_pairs(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def reward_of(result):
    rewards = (result.get("verifier_result") or {}).get("rewards") or {}
    value = rewards.get("reward")
    if value is None and len(rewards) == 1:
        value = next(iter(rewards.values()))
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def task_folder(result):
    """The task folder name. task_name can differ (it may be '<org>/<name>' from task.toml)."""
    for source in (result.get("task_id"), (result.get("config") or {}).get("task")):
        if isinstance(source, dict) and source.get("path"):
            return Path(str(source["path"]).rstrip("/")).name
    return str(result["task_name"]).rsplit("/", 1)[-1]


def load_trials(jobs_root):
    """Return {(side, run): {task folder: {"reward", "exception", "finished_at"}}}."""
    trials = {}
    for path in Path(jobs_root).rglob("result.json"):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or "trial_name" not in data or "task_name" not in data:
            continue
        match = JOB.fullmatch(path.parent.parent.name)
        if not match:
            continue
        exc = data.get("exception_info") or {}
        entry = {
            "reward": reward_of(data),
            "exception": exc.get("exception_type") if isinstance(exc, dict) else None,
            "finished_at": data.get("finished_at") or "",
        }
        by_task = trials.setdefault(match.groups(), {})
        folder = task_folder(data)
        old = by_task.get(folder)
        if old is None or entry["finished_at"] >= old["finished_at"]:
            by_task[folder] = entry
    return trials


def summarize_run(tasks, by_task, n_pairs):
    if by_task is None:
        return {"present": False}
    total, missing, no_reward, exceptions = 0.0, 0, 0, Counter()
    for task in tasks:
        trial = by_task.get(task)
        if trial is None:
            missing += 1
            continue
        if trial["exception"]:
            exceptions[trial["exception"]] += 1
        if trial["reward"] is None:
            no_reward += 1
        else:
            total += trial["reward"]
    return {
        "present": True,
        "score": round(100.0 * total / n_pairs, 4),
        "missing": missing,
        "no_reward": no_reward,
        "failed_fraction": round((missing + no_reward) / n_pairs, 4),
        "exceptions": dict(exceptions),
    }


def mean_sem(values):
    if not values:
        return None, None
    mean = statistics.fmean(values)
    sem = statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else 0.0
    return mean, sem


def compute(pairs, trials, runs, error_limit):
    n = len(pairs)
    run_names = [f"run{i}" for i in range(1, runs + 1)]
    stats = {"available": True, "n_pairs": n, "runs_expected": runs, "error_limit": error_limit,
             "sides": {}, "problems": []}
    for side in SIDES:
        tasks = [row[f"{side}_task"] for row in pairs]
        side_stats = {"runs": {}}
        for run in run_names:
            info = summarize_run(tasks, trials.get((side, run)), n)
            side_stats["runs"][run] = info
            if not info["present"]:
                stats["problems"].append(f"{side} {run}: no results")
            elif info["failed_fraction"] > error_limit:
                stats["problems"].append(
                    f"{side} {run}: {info['missing'] + info['no_reward']} of {n} trials failed")
        scores = [side_stats["runs"][r]["score"] for r in run_names if side_stats["runs"][r]["present"]]
        kept = sorted(scores)[1:-1] if len(scores) == runs and runs >= 3 else sorted(scores)
        mean, sem = mean_sem(kept)
        side_stats.update(scores=scores, kept=kept, mean=mean, sem=sem,
                          range=[min(kept), max(kept)] if kept else None)
        stats["sides"][side] = side_stats

    a, h = stats["sides"]["auto"]["range"], stats["sides"]["human"]["range"]
    stats["overlap"] = bool(a and h and max(a[0], h[0]) <= min(a[1], h[1])) if a and h else None
    if stats["problems"]:
        stats["rule_verdict"] = "failed"
    else:
        stats["rule_verdict"] = "match" if stats["overlap"] else "no match"
    return stats


def per_task_rows(pairs, trials, runs):
    run_names = [f"run{i}" for i in range(1, runs + 1)]
    rows = []
    for pair in pairs:
        row = dict(pair)
        for side in SIDES:
            task = pair[f"{side}_task"]
            rewards, errors = [], Counter()
            for run in run_names:
                trial = trials.get((side, run), {}).get(task)
                if trial is None:
                    errors["no_trial"] += 1
                    continue
                if trial["exception"]:
                    errors[trial["exception"]] += 1
                if trial["reward"] is not None:
                    rewards.append(trial["reward"])
            row[f"{side}_reward_sum"] = round(sum(rewards), 4)
            row[f"{side}_graded_runs"] = len(rewards)
            row[f"{side}_errors"] = ";".join(f"{k}x{v}" for k, v in sorted(errors.items()))
        row["gap"] = round(row["auto_reward_sum"] - row["human_reward_sum"], 4)
        rows.append(row)
    rows.sort(key=lambda r: -abs(r["gap"]))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compare", default="compare")
    ap.add_argument("--jobs", default="jobs")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--error-limit", type=float, default=0.10)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pairs_path = Path(args.compare) / "pairs.csv"
    if not pairs_path.is_file():
        stats = {"available": False, "reason": "no compare/pairs.csv (the prepare job did not finish)"}
        rows = []
    else:
        pairs = read_pairs(pairs_path)
        trials = load_trials(args.jobs) if Path(args.jobs).is_dir() else {}
        stats = compute(pairs, trials, args.runs, args.error_limit)
        rows = per_task_rows(pairs, trials, args.runs)

    (out / "stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    with open(out / "pertask.csv", "w", newline="") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    if stats.get("available"):
        for side in SIDES:
            s = stats["sides"][side]
            shown = f"{s['mean']:.2f} ± {s['sem']:.2f}" if s["mean"] is not None else "n/a"
            print(f"{side}: runs {s['scores']} -> {shown}")
        print(f"overlap={stats['overlap']} rule_verdict={stats['rule_verdict']} problems={stats['problems']}")
    else:
        print(stats["reason"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
