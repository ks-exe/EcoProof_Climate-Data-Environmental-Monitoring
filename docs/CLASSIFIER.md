# Task 5 classifier contract

This implements section 5 as a retrospective hourly heuristic. Mathematical and
synthetic cases are tested; these are not performance measurements on real air
data. [Task 6 evaluation](EVALUATION.md) runs interventions on separate copies
of real Delhi observations. The [reliability review](DETECTOR_REVIEW.md) records
the first correction and its separate-period comparison. Measured detection
limitations remain. The [plume ambiguity review](PLUME_REVIEW.md) documents the
second correction; [public Sepolia verification](ANCHORING.md) has been demonstrated.

## Inputs and baseline

`ecoproof.detect.classifier.classify` accepts station ID to `(lat, lon)` mappings,
readings keyed by `(station_id, timestamp)`, and regional weather keyed by timestamp
with `(speed_m_s, direction_from_deg)` values. Missing map entries mean missing
observations. Supplied invalid values are errors. Datetimes must be timezone-aware
and on UTC hour boundaries; offsets normalize to UTC. Output is sorted by station
ID and timestamp and includes only observed target readings.

The caller supplies `[baseline_start, baseline_end)` and `[start, end)`, with
`baseline_start < baseline_end <= start < end`. Baseline residuals use the same
graph, weights, and available neighbors as detection. Only baseline hours with
weather and at least two usable neighbors count. No detection or follow-up hour
is admitted to scale fitting. Selecting the window does not prove it is healthy.

`make detect` reads the selected region from a consistent Silver database snapshot.
Silver timestamps mean UTC. Raw interval-ending samples are assigned to `(H-1h, H]`
and averaged to a value at H; a sample exactly at H remains there. There is no
interpolation or carry-forward. This is an unweighted sample mean: unequal sample
durations and long measurement intervals are not corrected. Weather at H is used
exactly; no nearest-time substitute is invented. Silver retains the raw samples.

## Scores and initial parameters

The expected value is the weighted mean of available neighbors with positive
graph weights, excluding self-edges. Weights renormalize after missing readings
are removed. A zero concentration is a usable reading.

Residual is `value - expected`; z is `abs(residual) / sigma`. Baseline sigma is
`max(scale_floor, 1.4826 * median(abs(residual - median(residual))))`. An insufficient
baseline produces unknown sigma/z, not an invented baseline. The positive floor
handles zero MAD without infinity. It does not subtract the median residual from
the score or calibrate away persistent station bias.

| Setting | Initial value / requirement |
| --- | --- |
| Gaussian sigma in km, wind alpha | Required caller arguments; no tuned defaults |
| Graph cutoff | 20 km, inclusive |
| z threshold | 2.5, anomaly at equality |
| Residual/neighbor scale floor | 1 µg/m³, configurable |
| Minimum usable baseline residuals | 24, configurable; never below 3 |
| Recent neighbor baseline | Previous 6 hourly slots, at least 3 observed values |
| Persistence / flat window | 5 consecutive hourly slots |
| Flat tolerance | 0 µg/m³ (exact flatline), configurable in `DetectorConfig` |
| Plume delay candidates | 1, 2, 3 hours |
| Travel-time tolerance | 1 hour around distance/speed, configurable |

Defaults other than the spec's stated values are implementation choices, not
learned thresholds. The recent neighbor reference is its median and robust scale
from hours strictly before the source time. Missing slots are not compressed
together for persistence: all five consecutive hours must be present.

## Classification and evidence

1. Missing weather, fewer than two usable neighbors, or insufficient baseline
   returns `VALID` with `low_confidence=True` and a specific reason. Missing scores
   remain null. Fewer than two neighbors never causes a fault claim.
2. A supported flat/zero run emits a suspected fault independently of changing
   nearby pollution (see rule 8). Otherwise, below-threshold z without persistent disagreement
   returns `VALID` without a low-confidence flag.
3. For an anomaly, a positive target rise above its own recent reference and a
   positive residual can support a plume. A neighbor must be downwind at the
   source time, inside the graph, initially below its rise threshold, and rise
   by at least `z_threshold * its_recent_scale` at an eligible later hour. Wind
   must be nonzero. Eligible hours satisfy
   `abs(lag_hours - distance_km / (speed_m_s * 3.6)) <= lag_tolerance_hours`.
   Evidence saves neighbor, timestamp, lag, travel time, alignment, rise, and reference.
4. With z at/above threshold, at least one match produces `VERIFIED_PLUME_EVENT`.
   This name is the spec's label, not independent verification of a pollution event.
   The model uses the source-time regional wind and straight-line travel estimate;
   it does not simulate dispersion or subsequent wind changes.
5. A receiving observation linked to that supported source must not be called an
   isolated fault merely because no further downwind station exists. If it would
   otherwise be a fault, it remains `VALID`, low-confidence, with reason
   `arrival_of_supported_plume` and source station/time links. Up to three prior
   detection hours provide context across output-window boundaries; baseline
   hours are never relabeled as source context.
   An otherwise isolated positive spike can also be uncertain when a recent
   upwind anomaly is consistent with transport but fails the strict plume test.
   This narrower fallback requires a source-time receiver observation, a positive
   step of at least `z_threshold * receiver.baseline_sigma`, and an anomalous
   source that rose above its own reference. Source-time wind, graph distance and
   one-to-three-hour travel bounds still apply. Suspected-fault sources and chains
   of newly reconsidered arrivals cannot clear faults. The receiver becomes
   low-confidence `VALID` with `possible_upwind_transport` and source links;
   neither observation gains a confirmed plume label. This fallback does not
   override flat/zero or persistent-drift reasons.
6. Without a match, missing recent references or missing eligible later readings
   produce low-confidence `VALID`. So does observed neighbor disagreement. A fault
   is suspected only when the usable neighbors remain within their recent bounds
   at the current time and at eligible follow-up times. Crosswind/upwind future
   observations are not treated as downwind transport evidence.
7. Persistent drift requires a five-hour mean absolute residual z at/above the
   threshold and five same-sign residuals at least the scale floor in magnitude.
   A resolved one-hour spike must not create trailing fault labels through the
   rolling average alone.
8. A flatline requires a previously varying station (nonzero baseline value MAD),
   five consecutive flat readings, and two neighbors each with sufficient range
   and at least two changes during that complete window. Five zero readings
   after a nonzero baseline require two complete neighbors that stay above the
   noise floor. The weather, baseline and current-neighbor safeguards still
   apply. This temporal evidence does not require future observations or stable
   nearby pollution. A whole steady neighborhood or regional zero run is not
   declared an individual stuck sensor. The reason is `suspected_stuck_or_zero`.

The conservative `VALID` fallbacks above resolve cases the spec's initial rule
table leaves unspecified. Reasons preserve the distinction. These choices need
evaluation; low confidence is not proof of sensor health. An isolated real source
can resemble a fault, and smooth/noisy failure modes may escape these heuristics.

## Storage, rebuilds, and schema proposal

`make detect ARGS="..."` reads current Silver. Adding `--rebuild-silver` first
rebuilds Silver from immutable local Bronze, satisfying the one-command rebuild
rule without network access. Both forms require explicit windows, sigma, and alpha.
Rebuilding Silver may complete even if the subsequent detection fails; the
previous Gold view still remains intact in that case.

Each completed Gold build has its own directory. The two Parquet-backed views
switch in one DuckDB transaction after the files/report are complete. A failed
view switch rolls back both. Earlier Gold builds and any existing `gold.batches`
are retained. No output rows means an error; no empty replacement is published.

`gold.classified` keeps every column from section 4; timestamps retain the UTC
meaning. Task 8 computes `record_hash` from the canonical data/confidence payload.
The view resolves `batch_id` only for an identical saved record hash, preferring
mined batches without duplicating rows. See [batch storage](ANCHORING.md).
No placeholder hashes, transactions, or metrics are generated.

The companion `gold.classification_evidence` is keyed by `(station_id, ts)` and
stores `low_confidence`, `reason`, `baseline_sigma`, `smoothed_z`,
`plume_evidence_json`, and `plume_sources_json`. The JSON timestamps use UTC `Z`.
Source links can describe a supported plume or possible upwind transport; the
record's reason and confidence distinguish them.
Join this view whenever consuming a label. Do not silently include low-confidence
`VALID` records in the validated-data anchoring path.

**Proposed spec clarification for review:** add `low_confidence BOOLEAN NOT NULL`
and `reason TEXT NOT NULL` to `gold.classified`, and explicitly state that
incomplete/conflicting plume evidence can return low-confidence `VALID`. Section 5
requires confidence handling but section 4 currently provides no columns for it.
For now the companion view carries those fields, preserving the stated schema.
`docs/SPEC.md` has not been changed.

Build reports record configuration, baseline sample counts/scales, observed label
and confidence counts, reasons, and station/date coverage. These counts describe
the run; they are not precision, recall, or F1. Full seven-day classification needs
baseline data before those seven days and follow-up afterward, with real coverage
checked separately. A test fixture or seven distinct dates alone does not prove
the real-data milestone.
