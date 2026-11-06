#!/usr/bin/env bash
# The only command Claude can run in the prepare job.
#
#   fetch.sh human <folder>             dataset folder on harbor-datasets main
#   fetch.sh auto <pr-number> <folder>  dataset folder at the head of that harbor-datasets pull request
#   fetch.sh parity-runs <folder>       trial folders under adapters/<folder>/ on the Hugging Face
#                                       repo harborframework/parity-experiments
#
# Dataset output: work/datasets/<side>/<folder>/ plus work/datasets/<side>.json
# (folder, commit, pull request, number of task folders).
# Parity-run output: work/parity-runs/<folder>.tsv with "<run folder><TAB><task name>" per trial.
set -euo pipefail

REPO=https://github.com/harbor-framework/harbor-datasets
HF_TREE=https://huggingface.co/api/datasets/harborframework/parity-experiments/tree/main/adapters

die() { echo "fetch.sh: $*" >&2; exit 2; }

if [ "${1:-}" = parity-runs ]; then
  [ $# -eq 2 ] || die "usage: fetch.sh parity-runs <folder>"
  [[ $2 =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "bad folder name: $2"
  mkdir -p work/parity-runs
  python3 - "$HF_TREE/$2?recursive=true" "work/parity-runs/$2.tsv" <<'PY'
import json, re, sys, urllib.error, urllib.request
url, out = sys.argv[1], sys.argv[2]
trials, pages = [], 0
while url and pages < 200:
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            items = json.loads(r.read())
            link = r.headers.get("Link") or ""
    except urllib.error.HTTPError as e:
        sys.exit(f"fetch.sh: Hugging Face returned HTTP {e.code} (no such folder?)")
    pages += 1
    for item in items:
        name = item["path"].rsplit("/", 1)[-1]
        if item["type"] == "directory" and re.fullmatch(r".+__[A-Za-z0-9]{5,}", name):
            trials.append((item["path"].rsplit("/", 1)[0], name.rsplit("__", 1)[0]))
    match = re.search(r'<([^>]+)>;\s*rel="next"', link)
    url = match.group(1) if match else None
with open(out, "w") as f:
    f.writelines(f"{run}\t{task}\n" for run, task in sorted(trials))
note = " (stopped after 200 pages)" if url else ""
print(f"Listed {len(trials)} trial folders, {len({t for _, t in trials})} task names{note} into {out}")
PY
  exit 0
fi

side=${1:-}
case "$side" in
  human)
    [ $# -eq 2 ] || die "usage: fetch.sh human <folder>"
    pr=""; ref=refs/heads/main; folder=$2 ;;
  auto)
    [ $# -eq 3 ] || die "usage: fetch.sh auto <pr-number> <folder>"
    [[ $2 =~ ^[0-9]+$ ]] || die "pull request number must be digits: $2"
    pr=$2; ref=refs/pull/$2/head; folder=$3 ;;
  *) die "first argument must be human, auto or parity-runs" ;;
esac
[[ $folder =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "bad folder name: $folder"

clone=work/.clone-$side
dest=work/datasets/$side
rm -rf "${clone:?}" "${dest:?}/${folder:?}"
mkdir -p "$dest"

git clone -q --depth 1 --filter=blob:none --no-checkout "$REPO" "$clone"
git -C "$clone" fetch -q --depth 1 --filter=blob:none origin "$ref"
git -C "$clone" sparse-checkout set --no-cone "/datasets/$folder/"
git -C "$clone" checkout -q FETCH_HEAD
[ -d "$clone/datasets/$folder" ] || die "datasets/$folder not found at $ref"

commit=$(git -C "$clone" rev-parse FETCH_HEAD)
mv "$clone/datasets/$folder" "$dest/$folder"
rm -rf "$clone"

tasks=$(find "$dest/$folder" -mindepth 2 -maxdepth 2 -name task.toml | wc -l | tr -d ' ')
printf '{"side": "%s", "folder": "%s", "commit": "%s", "pull_request": %s, "task_folders": %s}\n' \
  "$side" "$folder" "$commit" "${pr:-null}" "$tasks" > "work/datasets/$side.json"
echo "Fetched datasets/$folder ($tasks task folders) at ${commit:0:12} into $dest/$folder"
