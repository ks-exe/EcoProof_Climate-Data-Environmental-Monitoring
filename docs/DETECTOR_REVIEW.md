# Detector reliability review — October 23, 2026

This review addressed a specific classifier defect: supported flat/zero runs were
vetoed by changing neighbors, even though variation in neighbors is
part of the evidence for a stuck sensor. It does not replace the detector, add
features, or change the project specification.

## Protocol fixed before the independent experiment

- Development evidence: the existing October 5–11 evaluation, calibrated on
  October 3–4. Its original report, chart, and classifier source are preserved in
  `reports/history/2026-10-23-initial/`.
- Independent temporal block: September 25–October 1, with September 23–24
  calibration and October 2 follow-up. These observations have not been used to
  design this correction. This is an earlier, separate period, not a prospective
  field trial or an independently labeled fault dataset.
- Use the same Delhi region, 25 km catalog radius, and first 12 eligible catalog
  locations. Preserve gaps and report coverage. Do not select stations by scores.
- Freeze the existing numerical detector defaults: sigma 10 km, alpha 0.5,
  tau 20 km, z threshold 2.5, scale floor 1, minimum baseline count 24, and five
  consecutive hours for flatness. No parameter search.
- Independent evaluation: five cases per type, seed 2026. Use unchanged
  intervention definitions and score every output row, including background and
  low-confidence rows. Run both the archived and corrected classifiers on the
  same inputs and interventions. Keep all results, including failed controls.
- Fix the rule using synthetic regression cases before scoring the independent
  period. Do not revise it after inspecting those scores within this review.

## Intended correction and limits

Keep missing-weather, sparse-baseline, and fewer-than-two-neighbor safeguards.
Require a complete five-hour run and two independently supporting neighbors.
For a nonzero flatline, the sensor must have varied during calibration and both
neighbors must vary during the run. For a zero run after a nonzero baseline,
both neighbors must remain above the noise floor. A regional zero reading or a
whole steady neighborhood does not establish an individual sensor failure.

When these conditions hold, emit `SENSOR_FAULT_DRIFT` with the existing
`suspected_stuck_or_zero` reason. Such evidence does not require neighboring
pollution to remain at its recent baseline or future samples to be available.
Other fault and plume rules remain unchanged. Exact repeated values are evidence,
not proof of malfunction; quantization and local environmental conditions can
also produce repeated values.

A passed software test is not evidence of accurate real-world detection. The
executed results and commands follow.

The corrected classifier was frozen before scoring the independent period:
SHA-256 `450ed3dcc326c89d4d9b6406c374d3ab433fc8ffa7dd2c47d6ea978b8e809af1`.
The original classifier SHA-256 is
`ff345864804e7e1ef977e1645c56a0f9ada0c4b2b3d6c9a1f0b9da508d76eca3`.

## Reproduce the comparison

From the repository root, after the normal dependency setup and the documented
October demo ingestion, cache the separate period:

```text
uv run --locked python -m ecoproof.ingest --source all --region delhi --latitude 28.6139 --longitude 77.2090 --radius-m 25000 --start-date 2026-09-23 --end-date 2026-10-02 --station-limit 12
```

The executed comparison uses an isolated Silver database so the running app can
keep its current snapshot. To prepare it in PowerShell:

```powershell
New-Item -ItemType Directory -Force .cache/detector-review-data/bronze
Copy-Item -Path data/bronze/*.json -Destination .cache/detector-review-data/bronze
```

Build it with this Python snippet (saved to a local file and run with the project
Python environment):

```python
from pathlib import Path
from ecoproof.config import Settings
from ecoproof.transform.silver import build_silver
build_silver(Settings(data_dir=Path('.cache/detector-review-data').resolve()), region_id='delhi')
```

Run the paired evaluations and chart:

```text
uv run --locked python scripts/review_detector.py --data-dir data --period development --revision after
uv run --locked python scripts/review_detector.py --data-dir .cache/detector-review-data --period independent --revision before
uv run --locked python scripts/review_detector.py --data-dir .cache/detector-review-data --period independent --revision after
uv run --locked python scripts/plot_detector_review.py
```

The development command uses the original app Silver snapshot. Its original
report is the development "before" measurement. The plotting script rejects
comparisons whose input fingerprints, configurations, coverage, or intervention
locations/values differ. A fresh API pull may contain provider revisions; in that
case, rerun both revisions on identical inputs and retain the original results.
`bronze-manifest.json` records the exact local input snapshots used in this review.

An evaluation exits 1 when the plume control fails, after saving all measured
results. Run the commands separately so this does not prevent the remaining
comparisons from executing. The archived Python modules are used only by the
offline experiment script; the application always uses `src/ecoproof/`.
Both revisions are now pinned: the flatline-corrected source is retained at
`reports/history/2026-10-24-pre-plume/classifier.py`, so subsequent fixes cannot
silently alter this comparison when its commands are repeated.

## Measured results

Both periods used identical inputs and intervention plans for their before/after
comparison; the plotting script's pairing checks passed. F1 below is over every
observed row in each intervention copy, not just the affected window.

| Fault | Development before | Development after | Separate period before | Separate period after |
| --- | ---: | ---: | ---: | ---: |
| Stuck | 0.096386 | 0.509434 | 0.000000 | 0.714286 |
| Zero | 0.139535 | 0.504673 | 0.000000 | 0.666667 |
| Spike | 0.000000 | 0.000000 | 0.080000 | 0.080000 |
| Drift | 0.025000 | 0.025000 | 0.000000 | 0.000000 |
| Degradation | 0.024390 | 0.024390 | 0.000000 | 0.000000 |

![Measured before/after comparison](../reports/detector-review/comparison.png)

The development report contains 18 independent copies (three per type), each
with 1,546 scored rows. Stuck/zero true positives rose to 27 of 36 affected
observations each. Unchanged-background fault flags remained 15; the other
fault metrics did not change. That revision's plume control failed: 1 false fault among
8 affected observations. This report is preserved; the dashboard now serves the
later [plume-ambiguity correction](PLUME_REVIEW.md).

The separate period contains 30 copies (five per type), each with 1,528 scored
rows at ten stations represented on all seven dates. Stuck true positives rose
from 0/60 to 45/60, and zero from 0/60 to 40/60. Unchanged-background flags remained
four; the other fault metrics did not change. Both revisions passed its plume
control (0/14 affected observations called faults), with all five sources labeled
`VERIFIED_PLUME_EVENT` and seven affected observations low confidence. That pass
does not resolve the earlier failed control. Neither period has independent
ground-truth labels for background sensor health.

Separate-period input fingerprint:
`c49be8e23b921b109058ca1cf76bac29ad81a33472b40be50bc95ba8dd504149`.
No detector rules or numerical settings were changed after seeing those results.
The independent commands both exited 0. The development command exited 1 for
its failed control. Plot generation exited 0 and the figure was inspected.

Machine-readable [comparison counts and metrics](../reports/detector-review/comparison.json)
link the evidence to the chart. Full reports retain confidence counts, threshold
baseline scores, interventions and failures:

- [Original development report](../reports/history/2026-10-23-initial/eval.json)
- [Corrected development report](../reports/detector-review/development-after/eval.json)
- [Separate period, original classifier](../reports/detector-review/independent-before/eval.json)
- [Separate period, corrected classifier](../reports/detector-review/independent-after/eval.json)

The gain is specific to sustained flat/zero faults in these experiments.
Spike/drift/degradation detection remains inadequate. More labeled data, other
regions and longer monitoring periods would be needed before an operational
accuracy claim. Public blockchain verification was completed on October 24;
see [the actual transaction and verification evidence](ANCHORING.md).
The later [plume ambiguity review](PLUME_REVIEW.md) is a separate correction and
experiment; the flatline comparison results above remain preserved.
