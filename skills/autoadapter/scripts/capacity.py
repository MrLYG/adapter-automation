#!/usr/bin/env python3
"""Print the free Daytona capacity of the organization behind DAYTONA_API_KEY.

Usage:
    python skills/autoadapter/scripts/capacity.py            # table
    python skills/autoadapter/scripts/capacity.py --json     # machine-readable

Reads DAYTONA_API_KEY (and DAYTONA_API_URL if set) from the environment.
Never prints the key. Uses only the Python standard library.

For each sandbox class it prints quota, current usage and free amount for
CPU (cores), memory (GB), disk (GB) and GPU, plus the per-sandbox maximums.
The usage covers every user of the key, not only you.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("DAYTONA_API_URL", "https://app.daytona.io/api").rstrip("/")
RESOURCES = [("cpu", "Cpu"), ("memory_gb", "Memory"), ("disk_gb", "Disk"), ("gpu", "Gpu")]


def get(path):
    key = os.environ.get("DAYTONA_API_KEY")
    if not key:
        sys.exit("DAYTONA_API_KEY is not set in this shell.")
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        sys.exit(f"GET {path} failed: HTTP {e.code}")
    except urllib.error.URLError as e:
        sys.exit(f"GET {path} failed: {e.reason}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    org = (get("/api-keys/current") or {}).get("organizationId")
    if not org:
        sys.exit("The API key response has no organizationId.")
    usage = get(f"/organizations/{org}/usage") or {}

    rows = []
    for r in usage.get("regionUsage", []):
        row = {"region": r.get("regionId"), "class": r.get("sandboxClass")}
        for name, field in RESOURCES:
            total = r.get(f"total{field}Quota") or 0
            used = r.get(f"current{field}Usage") or 0
            row[name] = {"quota": total, "used": used, "free": max(total - used, 0)}
        row["max_per_sandbox"] = {
            "cpu": r.get("maxCpuPerSandbox"),
            "memory_gb": r.get("maxMemoryPerSandbox"),
            "disk_gb": r.get("maxDiskPerSandbox"),
        }
        row["gpu_types"] = r.get("allowedGpuTypes")
        rows.append(row)

    if args.json:
        print(json.dumps(rows, indent=1))
        return
    for row in rows:
        print(f"class={row['class']} region={row['region']}")
        for name, _ in RESOURCES:
            v = row[name]
            print(f"  {name:10} quota={v['quota']:<8} used={v['used']:<8} free={v['free']}")
        print(f"  max per sandbox: {row['max_per_sandbox']}")
        if row["gpu_types"]:
            print(f"  GPU types: {row['gpu_types']}")


if __name__ == "__main__":
    main()
