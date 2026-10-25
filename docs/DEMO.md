# EcoProof local demo — October 24, 2026

The application is running locally with real OpenAQ Delhi observations and
Open-Meteo weather. One real batch is anchored on public Ethereum Sepolia, with
original-pass/edit-fail verification demonstrated. The detector remains a
prototype with measured limitations: its plume control now passes through an
uncertainty safeguard, while spike/drift/degradation detection remains weak.

## Open the application

- Dashboard: <http://127.0.0.1:5173>
- API documentation: <http://127.0.0.1:8000/docs>
- [Inspect a real saved record](http://127.0.0.1:5173/#verify?station=17&ts=2026-10-11T23%3A00%3A00.000000Z&batch=ecoproof%3Av1%3Avalid%3A20261011T230000Z%3Ae7aaf8938d201639002bfed699ed30b73674746c28d460ad4f1ce594aa67efc0)

The current session started API and Vite as hidden background processes. Their
launcher PIDs and URL are recorded in ignored `.cache/demo-runtime.json`, and
their logs are `.cache/demo-api*.log` and `.cache/demo-web*.log`. Closing the
browser does not stop them. For future starts, use separate terminals from the
repository root (after the main README setup):

```text
uv run --locked make api
uv run --locked make web
```

Use Ctrl+C in those terminals to stop services. Do not start duplicate servers
on the same ports. Stop API readers before database/anchoring writes.

## What actually ran

| Item | Measured result |
| --- | --- |
| Catalog | 94 Delhi-area locations, including historical locations |
| Air inputs | 7,596 PM2.5 records from 12 locations |
| Weather | 240 hourly rows, October 3–12 |
| Calibration | October 3 00:00 UTC to October 5 00:00 UTC |
| Classified output | October 5 00:00 UTC to October 12 00:00 UTC, end exclusive |
| Output | 1,546 hourly classifications at 11 locations |
| Labels | 1,514 VALID, 15 suspected-fault rows, 17 plume-evidence rows |
| Confidence | 257 output rows are low confidence; included within VALID |
| Prepared proofs | 165 hourly batches containing 1,257 confident VALID records |
| Evaluation | 18 independent injected cases on copies of real observations |
| Plume control | Passed: 0 false faults among 8 affected observations; 7 remain low confidence |
| Public anchoring | Registry deployed; one seven-record batch mined on Sepolia |
| Public verification | Original 22.0000 passes; edited 23.0000 fails; restored original passes |

Ten locations have observations across the output week. Sampling has gaps; the
other two input locations are sparse. Catalog locations are not a count of
active sensors. Provider timestamps describe measurement-interval ends; the
unbounded cached rebuild includes boundary records through October 13 00:00 UTC.

The first proposed one-day calibration supplied only 15–23 observed hours per
station. An earlier day was fetched to satisfy the unchanged 24-sample minimum.
Graph sigma 10 km, radius 20 km, wind alpha 0.5, z threshold 2.5, and evaluation
seed 42 are untuned settings. Cases and parameters were not changed after seeing
the failed evaluation. The subsequent supported flatline correction was rerun
on the same cases: stuck/zero F1 is now 0.509/0.505. The later transport-ambiguity
safeguard changed the remaining plume false fault to low confidence, leaving all
fault-type scores unchanged. See the [flatline review](DETECTOR_REVIEW.md) and
[plume review](PLUME_REVIEW.md), including the preserved failed reports.

## Walk through the real UI

1. Monitor opens a station with classified readings. Select R K Puram or another
   observed station using the search/list. Compare observed and expected values,
   select a nearby station, and inspect the wind and confidence reason. Gaps in
   the chart are missing observations, not zero values.
2. Use the recent-event filter to inspect suspected faults or plume evidence.
   Overview counts describe each station's latest label; the event list also
   contains earlier rows. These heuristic labels are not independently confirmed
   real sensor failures or atmospheric plumes.
3. Open the saved-record link above and click **Verify record**. The canonical
   JSON, hash and sibling path are real saved artifacts. The result is
   **Record verified**, with a Sepolia transaction link. In Record JSON change
   only `"value":22.0000` to `"value":23.0000`, then verify again: it fails.
   Click **Restore saved record** and verify again to restore the green result.
4. Open Evaluation. Its image and table come directly from `reports/eval.json`.
   Stuck/zero detection improved; other scores remain low. The plume control passes,
   with seven of eight affected observations still low confidence. An experiment
   with `status: complete` has finished running; it has not necessarily passed.

Actual screenshots: [Monitor](../reports/demo-monitor.png),
[Verify](../reports/demo-verify.png), [edited-record rejection](../reports/demo-tampered.png),
[Evaluation](../reports/demo-evaluation.png),
[mobile](../reports/demo-mobile.png). The browser result is
[demo-browser.json](../reports/demo-browser.json). It recorded loaded map tiles,
working charts, no horizontal mobile overflow and zero browser JavaScript errors.
All three public verification requests returned HTTP 200, with verdicts true,
false and true. The browser also checked the actual Sepolia transaction link.

## Reproduce the data run

These Windows commands use the installed project environment. Keep credentials
in ignored root `.env`, and stop the API while rebuilding the database.

```text
.\.venv\Scripts\python.exe -m ecoproof.ingest --source all --region delhi --latitude 28.6139 --longitude 77.2090 --radius-m 25000 --start-date 2026-10-04 --end-date 2026-10-12 --station-limit 12
.\.venv\Scripts\python.exe -m ecoproof.ingest --source all --region delhi --latitude 28.6139 --longitude 77.2090 --radius-m 25000 --start-date 2026-10-03 --end-date 2026-10-03 --station-limit 12
.\.venv\Scripts\python.exe -m ecoproof.detect --region delhi --rebuild-silver --baseline-start 2026-10-03T00:00:00Z --baseline-end 2026-10-05T00:00:00Z --start 2026-10-05T00:00:00Z --end 2026-10-12T00:00:00Z --sigma-km 10 --alpha 0.5
.\.venv\Scripts\python.exe -m ecoproof.detect.evaluate --region delhi --baseline-start 2026-10-03T00:00:00Z --baseline-end 2026-10-05T00:00:00Z --start 2026-10-05T00:00:00Z --end 2026-10-12T00:00:00Z --sigma-km 10 --alpha 0.5 --seed 42
```

The evaluation deliberately exits 1 when the plume control fails and retains its
measured report/chart. That exit must not be relabeled as a pass. Batches were
prepared with `prepare_batches` over the same output window; the equivalent CLI is:

```text
.\.venv\Scripts\python.exe -m ecoproof.provenance.anchor prepare --start 2026-10-05T00:00:00Z --end 2026-10-12T00:00:00Z
```

Development Vite reads the current report. For a production/preview snapshot,
run `npm.cmd run build` in `web/` after publishing the evaluation.

## Public verification evidence

The funded throwaway wallet deployed
[`0xb120d4671607E7C24F6C14C4f23B589F5f4484EB`](https://sepolia.etherscan.io/address/0xb120d4671607E7C24F6C14C4f23B589F5f4484EB)
on Ethereum Sepolia, chain ID 11155111. The
[anchor transaction](https://sepolia.etherscan.io/tx/0xbc325583e39e7778538a69878d9507281444a2e508ce13f048df455096ca5e49)
mined in block 11981966 at 2026-10-24 06:16:24 UTC. Its root, count, time bounds,
event and receipt were checked against the seven saved records.

The existing wallet key and RPC stay in ignored `.env`; `REGISTRY_ADDRESS` now
contains the mined address. Verification reads the chain and does not submit
another transaction. There is no need to fund or deploy again for this demo.
Only one of 165 prepared batches is anchored; other batches display **Saved only**.

[sepolia-demo.json](../reports/sepolia-demo.json) records public receipt fields
and actual CLI outputs. Original verification exited 0 with `verified: true`;
the edited record exited 1 with `verified: false`, as expected. See
[ANCHORING.md](ANCHORING.md) for repeatable commands and recovery behavior.

## Submission status

The [handoff guide](HANDOFF.md) contains the final checklist, fresh-checkout
instructions, an independent public-proof check and a timed video script.

The software tests and current development plume control pass. A recent upwind
anomaly now makes the previously missed arrival uncertain instead of calling it
an isolated fault. This does not establish confirmed plume recognition: seven
of eight affected observations are low confidence. The original failure and all
paired results remain available. Overall detection is still weak for spikes,
drift and degradation and needs broader validation before operational use.

The [GitHub repository](https://github.com/ks-exe/EcoProof_Climate-Data-Environmental-Monitoring)
is available. Still outstanding: the required narrated 3–5 minute video and final
submission. An MIT software license and [submission description draft](SUBMISSION.md)
are prepared locally. Screenshots
are actual execution evidence but do not replace those submission items.

For a video, distinguish the real input observations, heuristic labels, injected
evaluation faults, and the publicly anchored record. Use only measured
results from the report. Video publication and final submission remain owner
actions; broader detector validation remains future engineering work.
