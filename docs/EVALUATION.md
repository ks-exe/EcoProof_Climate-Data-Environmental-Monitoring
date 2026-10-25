# Task 6 evaluation contract

The reported experiment requires presumed-clean real Silver observations. Fault
and plume labels come from explicit synthetic interventions, not a real fault
catalog. Software tests use clearly marked synthetic fixtures in pytest scratch
directories; their metrics are not published to the project's `reports/`.

## Inputs and eligibility

`make eval ARGS="..."` requires region, baseline/output window bounds, graph sigma,
and wind alpha. Times are UTC-aware hours and end bounds are exclusive. The
baseline ends before or at the output start. The output window must span at least
seven days, with at least eight stations represented on seven UTC dates. Coverage
is reported per station; seven dates alone do not imply uninterrupted sampling.

The existing Silver snapshot reader supplies the same hourly means and regional
weather as the classifier, including three later hours for retrospective plume
checks. Evaluation does not write Bronze, Silver, or Gold. Rebuild Silver with
the required baseline/week/follow-up before running evaluation.

Candidate source times must have enough baseline residual samples, the previous
six hours of source history, weather throughout the intervention and follow-up,
and at least two neighbors observed throughout that context. These restrictions
make the controlled comparison interpretable and limit its applicability to
well-supported station windows. They are not evidence of healthy sensors.

Station/time candidates are sorted, then shuffled with a local seeded RNG. The
default seed is 42; the default is three cases per type. Each type takes the first
constructible cases in that order. Selection never uses predictions, scores, or
success/failure of injected cases. Rejections for missing data, no observable
effect, bounds, or lack of plume transport are recorded. If any required case type
cannot be constructed, the report is blocked, not a partially successful benchmark.

## Independent intervention copies

Every case starts from the original input mapping. Calibration rows are untouched
and the fitted baseline is checked against the unchanged control. Interventions
must fit inside the output window. Missing samples are not filled, and values
outside the Silver 0–1500 µg/m³ constraint are rejected instead of clipped.

| Type | Default intervention |
| --- | --- |
| Stuck | Hold the last pre-window observation for 12 hours |
| Zero | Set 12 hourly observations to zero |
| Spike | Add 100 µg/m³ for one hour at one station |
| Drift | Add a linearly growing offset, reaching +30 µg/m³ over 12 hours |
| Degradation | Multiply 12 observations by 0.7; configurable factor must be 0.6–0.8 |
| Plume negative control | Add +100 µg/m³ at the source and delayed +50 rises to up to two downwind neighbors |

The fault truth mask includes the entire intervention window even when one stuck
sample happens to equal its original value. A wholly unchanged intervention is
rejected as unobservable. Reports save the original and injected values and how
many actually changed.

Plume recipients are positive-alignment neighbors within tau. Source wind must
be nonzero. The chosen lag is the closest integer among 1, 2, and 3 hours within
the classifier's travel-time tolerance of `distance_km / (speed_m_s * 3.6)`.
Ties prefer the earlier lag. Recipients are ranked by alignment, distance, then
station ID; they must have an observation at the chosen lag. Their rise is
strictly smaller than the source rise. This is a simulated plume pattern, not a
claim that a real plume was observed.

These amplitudes/durations are provisional experiment settings, not tuned model
results or a representative distribution of real failures. `EvaluationConfig`
records them all. CLI flags expose seed, case count, duration, threshold, and the
detector's main parameters. No optimization or tuning on scored cases is performed.

## Metrics and the comparison

The fault detector predicts positive only for `SENSOR_FAULT_DRIFT`. The comparison
predicts positive exactly when PM2.5 is **greater than** 150, configurable with
`--threshold`. Both methods are scored on the identical set of observed output
rows for each independent copy.

Injected fault-window rows are positive; all other rows are assumed negative for
this experiment. All plume source/arrival rows are negative for fault detection.
Real observations may already contain faults, so apparent false positives on
unchanged data are not independently verified real false alarms. An unchanged
control reports those baseline flags explicitly.

- Precision = TP / (TP + FP).
- Recall = TP / (TP + FN).
- F1 = 2TP / (2TP + FP + FN), reported only when actual fault positives exist.
- False-positive rate = FP / (FP + TN).

A zero denominator gives JSON `null`, not an invented perfect score. If fault
positives exist and none are detected, recall/F1 are zero and precision is null.
Plume/unchanged controls have no fault positives, so recall/F1 are not applicable.

Low-confidence rows remain in the denominator: an injected fault left `VALID`
counts as a false negative. Low-confidence totals, counts on injected faults, and
the confident fraction are reported separately. No selective score over only
confident predictions is substituted for the full result.

Per-type metrics sum the confusion counts across that type's independent copies
before calculating ratios. Each copy reuses background data; these are not
independent field samples or a population estimate. No confidence intervals,
real-world prevalence estimates, or performance-improvement claims are invented.

The plume control separately reports false fault calls on affected observations,
source labels, and low-confidence counts. `plume_negative_control_passed` means
zero EcoProof fault calls on those affected rows. A low-confidence non-fault is
not evidence that the detector positively recognized a plume; source labels and
confidence must be read alongside the pass/fail field. Failed controls stay in
the report and are not discarded or retried to find better outcomes. A completed
experiment with a failed plume control is saved, but the CLI exits nonzero so
that it cannot be mistaken for a passed acceptance check.

## Artifacts and missing-data behavior

`reports/eval.json` contains the input kind, parameters, baseline/window bounds,
coverage, eligibility/rejection counts, unchanged control, per-case interventions
and metrics, per-type aggregates, and the plume result. The reproducibility
fingerprint hashes sorted compact JSON with UTC times and four-decimal numeric
strings; it is not a Merkle record hash or an on-chain claim.

A headless Matplotlib chart is generated from the staged JSON content and saved
under a unique PNG filename. JSON is published last and names that completed
chart. Earlier charts remain available. Failed chart generation preserves the
previous report and removes only the new staging artifacts.

When required input data is absent or insufficient, the command exits nonzero and
writes `status: blocked`, a reason, `metrics: null`, no cases, and no plume verdict.
The corresponding chart explicitly says **EVALUATION NOT RUN**, with no metric
bars. If a complete report already exists, blocked attempts go to
`eval.attempt.json` so they do not replace that completed experiment.

Matplotlib uses an Agg canvas and a workspace `.cache/matplotlib` directory when
`MPLCONFIGDIR` is not already set. The temporary environment setting is restored
after rendering. No new `.env` variable or credential is required for plotting.

The October 23 experiment used real Delhi Silver observations and 18 synthetic
intervention cases. It completed with a failed plume control (one false fault on
eight affected observations across three plume trials). The CLI correctly exited
1; its original metrics and failure are retained in
`reports/history/2026-10-23-initial/eval.json`. The source of that
arrival was left low confidence, so the supported-source protection did not
apply. This is a limitation of the heuristic on the measured data. No cases were
discarded and no parameters were changed to manufacture a passing result.

The subsequent [detector reliability review](DETECTOR_REVIEW.md) fixes the
supported flat/zero decision path. Its preserved rerun contains results on
the same development cases: stuck F1 0.509434 and zero F1 0.504673, with the plume
control still failed. The original report and source are archived. The review
also specifies a separate temporal block for paired evaluation, with model
rules fixed before scoring it. The separate results do not replace a known
failed control with a more favorable case selection.

The October 24 [plume ambiguity review](PLUME_REVIEW.md) reuses the same
development interventions after a narrow uncertainty-handling correction.
`reports/eval.json` now holds that measured report: 0/8 plume false faults, with
7/8 affected observations low confidence. All fault-type scores are unchanged.
The report before this correction is archived under
`reports/history/2026-10-24-pre-plume/`. Previously inspected and new temporal
periods are reported separately; passing this control is not a field-accuracy
claim or evidence that every plume was positively recognized.
