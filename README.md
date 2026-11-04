# Adapter automation

Reusable workflows and reviewer guidance for Harbor adapters. Adapter source,
acceptance requirements, author tools, and parity evidence remain in
[harbor-framework/adapters](https://github.com/harbor-framework/adapters).

## Adapter review

The reusable `.github/workflows/adapter-review.yml` performs structural validation
and read-only Claude review, then publishes results on the caller's PR. It uses
the caller's GitHub context, existing model secrets, and current Claude action
authentication. The model API key and endpoint stay configured for the caller;
this repository does not need copies of those credentials.

The caller owns event handling and authorization. The adapters caller retains
the existing `/review-adapter` comment and author-association checks. This
workflow does not add label, push, or automatic PR invocation.

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

`automation-ref` pins the checkout containing reviewer guidance to the same
revision as the workflow. Pass the two existing model secrets explicitly because
the caller and this repository are in different organizations. `GITHUB_TOKEN`
is supplied by GitHub for the caller; the Claude action retains its existing
GitHub App token exchange and `id-token: write` permission. No new model federation,
PAT, or application installation is introduced by this migration.

The caller's Actions policy must permit this public reusable workflow and its
existing dependencies. A reference to reusable YAML does not check out its
repository automatically; the workflow checks it out explicitly.

## Source ownership

| Source | Revision used during review |
| --- | --- |
| Workflow and `skills/review-adapter/SKILL.md` | The caller's full automation SHA |
| `scripts/validate_adapter.py`, `docs/adapters.mdx`, and shared parity diagnostics | The trusted caller revision, `github.sha` |
| Submitted adapter files | The PR head SHA resolved at the start of validation |

The validator is executed from `trusted-adapters/` against files in `reviewed-pr/`.
The PR's own validator and review instructions cannot replace the accepted ones.
The AI job requires successful structural validation and checks PR freshness
before reviewing and again before publishing. Reviews identify the adapter and
contract revisions, and the prompt records the automation revision.

Shared diagnostics normally come from `docs/parity-diagnostics.md` in the caller.
The loader also accepts the previous
`skills/review-adapter/references/parity-diagnostics.md` location so the automation
can land before the adapter-side documentation move.

## Migration and future workflows

Merge the automation change before switching the adapter caller. The consumer
must pin a commit retained in this repository; if the automation PR is squash
merged, update both consumer pins to the resulting commit before merging the
consumer PR. Preserve the current adapter workflow until that cutover.

The adapter contract, local validator, author skills, and contract tests stay
with the adapter repository. Workflow tests and reviewer policy live here.
Changes proposed in adapters PRs #59 (pagination/report guidance) and #69
(baseline-aware validation) remain separate from this migration and need to be
reconciled with the shared implementation when those changes land.

Additional workflows can be added alongside this one with `workflow_call`.
Future invocation methods can resolve a PR number in the caller and pass it to
an appropriate workflow. Claude's current comment-event handling must also be
checked when adding another invocation method. Upgrading the consumer pin is an
explicit rollout step.

## Development

Use Python 3.12+ and Node.js 22+:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

The tests execute the trusted-input loader, validator invocation, and report
publishing steps with local fixtures and a fake GitHub client. They cover changed
or closed PRs, comment ownership, newer structural reports, and empty model
reports without invoking a model or writing to GitHub. The test workflow runs
these checks on PRs and pushes to `main`.

After cutover, verify one authorized `/review-adapter` request in the adapter
repository. Local tests cannot verify the existing Claude App token exchange in
a live reusable-workflow run.
