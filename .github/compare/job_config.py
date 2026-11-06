#!/usr/bin/env python3
"""Print the Harbor JobConfig (JSON) for one run of the comparison.

  job_config.py --side auto|human --run run1..runN --pr <number>

Settings come from the workflow env: AGENT, AGENT_MODEL, AGENT_MAX_TOKENS,
N_CONCURRENT, MAX_RETRIES and OPENAI_BASE_URL. The agent reads OPENAI_API_KEY
itself; no key is written into the config.
"""
import argparse
import json
import os
import re
import sys


def build(side, run, pr, env):
    if side not in ("auto", "human"):
        raise ValueError(f"bad side: {side}")
    if not re.fullmatch(r"run[0-9]+", run):
        raise ValueError(f"bad run: {run}")
    agent = {
        "name": env["AGENT"],
        "model_name": env["AGENT_MODEL"],
        "kwargs": {
            "api_base": env["OPENAI_BASE_URL"],
            "llm_call_kwargs": {"max_tokens": int(env["AGENT_MAX_TOKENS"])},
        },
    }
    return {
        "job_name": f"{side}-{run}",
        "jobs_dir": "jobs",
        "n_concurrent_trials": int(env["N_CONCURRENT"]),
        "retry": {"max_retries": int(env["MAX_RETRIES"])},
        "environment": {
            "type": "daytona",
            "kwargs": {"labels": {
                "compare_owner": "compare-auto-with-human",
                "compare_job": f"pr{pr}-{side}-{run}",
            }},
        },
        "agents": [agent],
        "datasets": [{"path": f"compare/{side}"}],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--side", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--pr", required=True, type=int)
    args = ap.parse_args()
    json.dump(build(args.side, args.run, args.pr, os.environ), sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
