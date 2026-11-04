# Adapter automation

This repository contains shared workflows and the full adapter review guide.
Adapter code, requirements, author tools, and experiment results live in
[harbor-framework/adapters](https://github.com/harbor-framework/adapters).

## Adapter review

`.github/workflows/adapter-review.yml` checks adapter structure, asks Claude to
review the code, and posts the results on the adapter PR. It uses the existing
API key, endpoint, and GitHub authentication from the adapters repository.
Claude reads the submitted files and returns a report; it cannot run adapter
code or change files.

To request a review, comment `/review-adapter` on the adapter PR. The workflow in
`adapters` checks who posted the comment before calling this workflow. The
existing trigger and permission checks stay in place.

Call it with a full commit SHA in both places:

```yaml
jobs:
  review:
    # Keep the caller's existing event and authorization condition here.
    permissions:
      contents: read
      pull-requests: write
      issues: read
      id-token: write
    uses: harbor-index/adapter-automation/.github/workflows/adapter-review.yml@<automation-sha>
    with:
      pr-number: ${{ github.event.issue.number }}
      automation-ref: <automation-sha>
    secrets:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      ANTHROPIC_BASE_URL: ${{ secrets.ANTHROPIC_BASE_URL }}
```

Use the same full commit SHA for the workflow reference and `automation-ref`.
This makes the workflow and review guide come from the same version.
Pass the existing model secrets by name because the repositories are in different
organizations. GitHub supplies `GITHUB_TOKEN` for the adapters repository. The
Claude action continues to use its existing GitHub App token exchange, which
requires `id-token: write`.

The adapters repository's Actions settings must allow this public workflow and
the actions it uses. The workflow checks out this repository to read the guide;
GitHub does not do that automatically for reusable workflows.

## Files used during a review

| Files | Version |
| --- | --- |
| Workflow and `skills/review-adapter/SKILL.md` | The automation commit selected in `adapters` |
| `scripts/validate_adapter.py`, `docs/adapters.mdx`, and shared parity diagnostics | The trusted adapters revision, `github.sha` |
| Submitted adapter files | The PR head SHA resolved at the start of validation |

The workflow runs the validator from `trusted-adapters/` against the submitted
files in `reviewed-pr/`. This prevents a PR from changing its own validation rules.
Claude review starts after structural validation passes. Before reviewing and
posting the report, the workflow checks that the PR is still open and unchanged.
The report identifies the reviewed commit and specification version; the prompt
also records the automation commit.

Shared diagnostics come from `docs/parity-diagnostics.md` in `adapters`. The
workflow also accepts the old `skills/review-adapter/references/parity-diagnostics.md`
path, so this workflow can be merged before the adapter documentation moves.

Authors can still start a self-review from `skills/review-adapter/SKILL.md` in
their adapters checkout. That entry loads the full guide from the automation
commit selected by CI. The guide is maintained here, so authors need access to
GitHub to read it.

## Updating the workflow

Merge workflow changes here before updating `adapters`. Then set both references
in the adapters workflow to the resulting commit SHA. If a PR is squash-merged,
use the new commit created by that merge. Keep the current adapters workflow in
place until the replacement is ready.

New workflows can be added here with `workflow_call`. To support another trigger,
update the adapters workflow to handle that event and pass the PR number. Check
that the Claude action supports the new event too.

## Development

Use Python 3.12+ and Node.js 22+:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

The tests run the guidance loader, validator command, and report-publishing steps
against local files and a fake GitHub client. They check what happens when a PR
changes or closes, a newer report already exists, or the model returns an empty
report. They also check that structural validation updates only its own comments.
The tests run on PRs and pushes to `main`; they do not call a model or post to
GitHub.

After switching the adapters workflow, try one authorized `/review-adapter`
request. A live run is needed to check that the existing Claude App token exchange
works through the reusable workflow.
