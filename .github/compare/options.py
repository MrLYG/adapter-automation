#!/usr/bin/env python3
"""Read the settings that a maintainer wrote after the comparison command.

  options.py        (reads COMMENT_BODY and the workflow env, prints name=value lines)

Example comment:
  /compare-auto-with-human timeout-multiplier=20 model=deepseek-v4.1-flash concurrency=20

Only the first line of the comment is read. A setting that is not in the comment keeps
the value of the workflow env (TIMEOUT_MULTIPLIER, AGENT_MODEL, N_CONCURRENT). The
output lines go to GITHUB_OUTPUT of the check job.
"""
import os
import re
import sys

COMMAND = "/compare-auto-with-human"
# setting in the comment -> (output name, workflow env default, pattern of a correct value)
SETTINGS = {
    "timeout-multiplier": ("timeout_multiplier", "TIMEOUT_MULTIPLIER", r"[0-9]+(\.[0-9]+)?"),
    "model": ("agent_model", "AGENT_MODEL", r"[A-Za-z0-9][A-Za-z0-9._/-]*"),
    "concurrency": ("n_concurrent", "N_CONCURRENT", r"[0-9]+"),
}


def parse(body, env):
    """Return {output name: value} for the comment text and the workflow env."""
    lines = body.strip().splitlines()
    words = lines[0].split() if lines else []
    if not words or words[0] != COMMAND:
        raise ValueError(f"the comment must start with {COMMAND}")
    given = {}
    for word in words[1:]:
        key, sep, value = word.partition("=")
        if not sep or key not in SETTINGS:
            raise ValueError(f"unknown setting: {word} (known: {', '.join(SETTINGS)})")
        if key in given:
            raise ValueError(f"setting given two times: {key}")
        if not re.fullmatch(SETTINGS[key][2], value) or (key != "model" and float(value) <= 0):
            raise ValueError(f"bad value for {key}: {value}")
        given[key] = value
    return {name: given.get(key, env[default]) for key, (name, default, _) in SETTINGS.items()}


def main():
    try:
        values = parse(os.environ.get("COMMENT_BODY", ""), os.environ)
    except ValueError as error:
        sys.exit(f"Cannot read the settings: {error}")
    for name, value in values.items():
        print(f"{name}={value}")


if __name__ == "__main__":
    main()
