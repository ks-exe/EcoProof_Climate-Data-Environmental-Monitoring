# Submission description draft

This draft describes the actual October 24 state, including public Sepolia
anchoring and original-pass/edit-fail verification. The core prototype and plume
controls run; detector accuracy limitations remain documented below. Public
video URL must be added after publication. The project repository is
[ks-exe/EcoProof](https://github.com/ks-exe/EcoProof_Climate-Data-Environmental-Monitoring).

## Track statement

**Climate Data & Environmental Monitoring.** EcoProof explores how environmental
observations can carry both a quality assessment and an auditable provenance
record. The prototype uses PM2.5 observations; these are air-quality measurements,
not direct measurements of carbon emissions or carbon-credit validity.

## Problem and users

Environmental decisions depend on sensor data, but sensors can drift, become
stuck or report isolated spikes. A pollution event can also resemble a faulty
reading. Putting data on a blockchain does not resolve that ambiguity.

EcoProof is intended for monitoring teams and auditors who need to inspect the
evidence behind a reading and check whether a saved record was later changed.
City monitoring programs and environmental data providers are potential users;
no deployment, customer adoption or verified operational impact is claimed.

## Prototype and approach

The Python pipeline caches original OpenAQ and Open-Meteo responses, validates
them into Parquet/DuckDB, and builds a geographic station graph. Wind-weighted
neighbor observations provide an expected value. A robust residual scale and
temporal checks produce heuristic valid, suspected-fault or plume-evidence
labels. Missing evidence is explicitly marked low confidence.

Confident VALID observations are placed into immutable hourly Merkle snapshots.
A small Solidity registry and web3 client implement public testnet submission
and readback. FastAPI and React/Leaflet provide station charts, evidence,
canonical record/proof inspection, verification and evaluation results.

The registry is deployed on Ethereum Sepolia and one seven-record batch has a
[public anchor transaction](https://sepolia.etherscan.io/tx/0xbc325583e39e7778538a69878d9507281444a2e508ce13f048df455096ca5e49).
Its receipt, event, root, time bounds and count match the saved snapshot.
The actual CLI and browser verify the original value 22.0000 and reject 23.0000;
restoring the saved record passes again in the browser. Other prepared batches
remain unanchored. [Public evidence](../reports/sepolia-demo.json) and
[API/browser results](../reports/demo-browser.json) are saved with the project.

## What was demonstrated

The October 23 run ingested 7,596 PM2.5 observations from 12 Delhi locations and
240 weather hours. Ten stations have observations across the scored week, with
gaps preserved. It produced 1,546 hourly classifications and prepared 1,257
confident VALID records in 165 batches. The live dashboard and actual evaluation
chart were tested in desktop and mobile Chrome, with zero browser JavaScript
errors in that run.

An 18-case injection experiment used independent copies of the real observations.
A supported flatline correction raised stuck-fault F1 from 0.096 to 0.509 and
zero-fault F1 from 0.140 to 0.505 on identical development cases. The original
reports are archived; other fault scores remain weak. A later ambiguity safeguard
changed the remaining plume false fault to low confidence on identical cases:
the current report has zero false faults among eight affected observations, seven
of which remain uncertain. The earlier failed control is preserved. Current
scores are published in `reports/eval.json`; the paired protocols and results are
in `docs/DETECTOR_REVIEW.md` and `docs/PLUME_REVIEW.md`.
On the separate week, with rules frozen before scoring five cases per type,
stuck/zero F1 increased from 0/0 to 0.714/0.667. Unchanged-data fault flags stayed
at four, while spike/drift/degradation remained weak. Both versions passed that
week's plume control. The later plume correction also leaves that week's scores
and zero-of-fourteen false-fault result unchanged.
On a newly scored October 15–21 period, both versions also passed the plume
control (0/15), with unchanged fault-type scores and six affected rows uncertain.
The correction was frozen before that period was scored.
These synthetic interventions do not establish field accuracy.
Software checks passed: 447 Python tests in a fresh source export, including
the public-proof checks and existing browser acceptance wrapper. All 14 frontend
unit checks and the production build also passed in that export.
Software passes and a plume-control pass do not establish
adequate field accuracy for the weak fault types.

## Scale and adoption

A new region would require selecting sufficiently dense stations, checking
coverage, calibrating on a separate baseline and measuring performance before
use. Hourly root commitments would keep blockchain storage proportional to
batches, while observations and proofs remain off chain. No throughput, operating
cost, carbon reduction or accuracy improvement has been measured at scale.

The next steps are to improve and validate the heuristic using separate data,
and test the audit workflow with monitoring users.
Any future hosting or scheduled ingestion should preserve the documented
credential boundaries, immutable source data and reproducible evaluation.

## Submission assets

- Setup, commands and architecture: root README.
- Actual demo guide: `docs/DEMO.md`.
- Owner checklist, fresh-checkout notes and timed video script: `docs/HANDOFF.md`.
- Independent public-proof checker: `scripts/verify_public_demo.py`; actual
  original/edit/restore output without a database: `reports/handoff-check.json`.
- Actual screenshots and browser results: `reports/demo-*`.
- Public receipt/readback and original proof: `reports/sepolia-demo.json` and `reports/sepolia-proof.json`.
- Measured experiment and figure: `reports/eval.json` and its referenced PNG.
- Software license: root `LICENSE` (MIT). Data sources retain their own terms
  and attribution; the software license does not relicense third-party data.
- Public repository: [EcoProof on GitHub](https://github.com/ks-exe/EcoProof_Climate-Data-Environmental-Monitoring).
- Narrated 3–5 minute video URL: not yet recorded/published.
- Public Sepolia transaction: [seven-record batch](https://sepolia.etherscan.io/tx/0xbc325583e39e7778538a69878d9507281444a2e508ce13f048df455096ca5e49).

Do not submit placeholders as functioning links or claim completion of pending
items. The narrated video and final hackathon submission remain owner actions.
