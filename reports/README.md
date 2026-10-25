# Generated evaluation artifacts

Run `make eval ARGS="..."` as documented in the project README.

The current development experiment has zero false faults on eight injected
plume observations after the October 24 ambiguity safeguard. Seven affected
observations remain uncertain; other fault scores remain weak. See
[`docs/DEMO.md`](../docs/DEMO.md) for the run and its limitations.

`demo-monitor.png`, `demo-verify.png`, `demo-tampered.png`, `demo-evaluation.png`, `demo-mobile.png`
and `demo-browser.json` record actual browser output against the real workspace.
The October 24 verification screenshots show a real Sepolia success and rejection
after editing the value. The browser report includes original, edited and restored
API verdicts and the actual transaction link. `sepolia-demo.json` contains public
deployment/anchor receipt fields, registry readback and CLI verification output.
`sepolia-proof.json` preserves the actual API proof response, including the
original canonical payload and sibling path, for independent inspection.
`scripts/verify_public_demo.py` checks that sample directly against the published
Sepolia registry without the operator's local database; see `docs/HANDOFF.md`.
`handoff-check.json` records that check from a fresh source export, including
original/edit/restore verdicts, empty-data startup and the saved evaluation assets.

- `eval.json`: latest completed experiment, or an explicit blocked status if no
  experiment has completed yet. Read `status` and `input_kind` before using metrics.
- `eval-*.png`: immutable charts; the report's `chart` field names its matching PNG.
- `eval.attempt.json`: a blocked later attempt that preserves an earlier complete report.
- `history/2026-10-23-initial/`: original measured report, chart and classifier;
  retained as the development baseline for the supported-flatline correction.
- `detector-review/`: paired before/after reports, input snapshot manifest and
  comparison artifacts. See [`docs/DETECTOR_REVIEW.md`](../docs/DETECTOR_REVIEW.md)
  for the fixed protocol and reproducible commands.
- `history/2026-10-24-pre-plume/`: the classifier, report and chart immediately
  before the ambiguity safeguard, including the unresolved 1/8 plume failure.
- `plume-review/`: the new paired reports, immutable input manifest, current Gold
  comparison and figure. See [`docs/PLUME_REVIEW.md`](../docs/PLUME_REVIEW.md).

Blocked reports have no metrics and their charts say **EVALUATION NOT RUN**.
Synthetic test fixtures write only to pytest scratch directories. Do not copy
their metrics here and present them as results on real observations.
