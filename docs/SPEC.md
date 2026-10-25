# EcoProof — Implementation Spec (MVP)

Transcribed from the user-supplied `EcoProof_Implementation_Spec.pdf` (7 pages).
The workspace had no existing `docs/SPEC.md`; this document preserves the supplied specification,
with PDF layout converted to Markdown. This is the project source of truth.

**IMPLEMENTATION SPEC · 6-DAY MVP**

**Verifiable climate-sensor data: graph-based fault detection + on-chain Merkle anchoring**

Purpose of this document: a trimmed, buildable version of the full blueprint, written so it can be
given to a coding agent (Codex) task by task. Hackathon: IEEE ClimateChain Global Hackathon, track
Climate Data & Environmental Monitoring. Deadline: Oct 25, 2026, 7:00 pm GMT+5.

| Item | Decision |
| --- | --- |
| One-line pitch | Low-cost air sensors fail silently; EcoProof separates sensor faults from real pollution plumes using neighbor + wind logic, and only anchors validated data (as Merkle roots) on a blockchain. |
| Scope rule | Everything in the demo path must really run. Anything not finished by Day 5 is cut, not faked. |
| Cut from full blueprint | Dagster, Mapbox, CNN-GNN-LSTM-VAE training, quantum/BB84 layer, partitioned lakehouse tiers beyond Parquet files. |
| Kept | DuckDB + Parquet, haversine graph, wind-weighted expected value, z-score classifier, fault-injection evaluation, Merkle proofs, testnet smart contract, map dashboard, verify page. |
| Stretch | Text-to-SQL chat (read-only), recurring ingestion job. |

## 1. What the judges score, and how this MVP answers it

| Criterion | What we show |
| --- | --- |
| Climate Impact | Trustworthy emissions/air data for carbon markets, regulators and parametric insurance; fewer false pollution violations. |
| Innovation | Wind-aware graph residuals to separate faults from plumes, combined with validate-then-anchor blockchain design. |
| Technical Execution | Live pipeline on real OpenAQ + Open-Meteo data, measured detection metrics, deployed contract, working verify page. |
| Practical Usefulness | Auditor can verify any single record against an on-chain root without trusting the operator's database. |
| Presentation | 3–5 min video: problem, live fault-vs-plume case, verification, metrics, scale story. |

Required submission items: track statement, project description (problem, solution, users, scalability,
adoption), 3–5 min demo video, public GitHub repo with documentation, and a working prototype or proof of concept.

## 2. Technology stack

| Layer | Choice | Notes |
| --- | --- | --- |
| Language | Python 3.11+ | Pipeline, detector, API. Use uv or venv + requirements.txt. |
| Data APIs | OpenAQ v3, Open-Meteo | OpenAQ needs a free API key (check current docs). Open-Meteo needs none. Cache raw responses to disk. |
| Storage | DuckDB + Parquet | Bronze = raw JSON files; Silver/Gold = Parquet queried through DuckDB. |
| Backend | FastAPI + uvicorn | Serves stations, readings, classifications, batches, proofs. |
| Contract | Solidity + Foundry or Hardhat | Deploy to a public testnet (Sepolia or similar). Keep the contract tiny. |
| Chain client | web3.py | Backend submits roots; verify endpoint reads them. |
| Frontend | React + Vite + Leaflet | Leaflet/OSM needs no API token. Three views: Map, Verify, (stretch) Chat. |
| Tests | pytest | Merkle, haversine, classifier, SQL guard must have unit tests. |

## 3. Repository layout

```text
ecoproof/
├── AGENTS.md                  # instructions for Codex (section 10)
├── README.md                  # setup, demo steps, architecture, honest limitations
├── pyproject.toml / requirements.txt
├── .env.example               # OPENAQ_API_KEY, RPC_URL, PRIVATE_KEY (never commit real values)
├── data/
│   ├── bronze/                # raw API JSON, one file per pull (immutable)
│   ├── silver/ gold/          # Parquet
│   └── ecoproof.duckdb
├── src/ecoproof/
│   ├── config.py
│   ├── ingest/openaq.py  ingest/openmeteo.py
│   ├── transform/silver.py  transform/gold.py
│   ├── graph/geo.py           # haversine, adjacency, wind weights
│   ├── detect/classifier.py   # expected value, z-score, labels
│   ├── detect/inject.py       # synthetic fault injection
│   ├── detect/evaluate.py     # precision/recall/F1 vs threshold baseline
│   ├── provenance/merkle.py   # canonical JSON, tree, proofs
│   ├── provenance/anchor.py   # submit/read roots via web3.py
│   ├── api/main.py            # FastAPI app
│   └── sqlchat/guard.py       # stretch: read-only SQL validation
├── contracts/ BatchRegistry.sol, test/, script/deploy
├── web/                       # React + Vite + Leaflet
└── tests/
```

## 4. Data model (DuckDB / Parquet)

Timestamps are UTC. Pick one city or region with at least 8–10 reference-grade or low-cost stations
inside roughly a 20–25 km radius so the neighbor graph is meaningful.

```sql
-- silver.stations
station_id TEXT PRIMARY KEY, name TEXT, lat DOUBLE, lon DOUBLE, provider TEXT, cluster_id TEXT
-- silver.readings   (deduplicated, validated)
station_id TEXT, ts TIMESTAMP, parameter TEXT,        -- 'pm25' for the MVP
value DOUBLE CHECK (value >= 0 AND value <= 1500), unit TEXT,
PRIMARY KEY (station_id, ts, parameter)
-- silver.weather    (nearest grid point per station or one per region)
region_id TEXT, ts TIMESTAMP, wind_speed DOUBLE, wind_dir_deg DOUBLE, temp DOUBLE, pressure DOUBLE
-- gold.classified
station_id TEXT, ts TIMESTAMP, value DOUBLE, expected DOUBLE, residual DOUBLE, z DOUBLE,
label TEXT,                  -- VALID | SENSOR_FAULT_DRIFT | VERIFIED_PLUME_EVENT
neighbor_count INT, wind_speed DOUBLE, wind_dir_deg DOUBLE, record_hash TEXT, batch_id TEXT
-- gold.batches
batch_id TEXT PRIMARY KEY, window_start TIMESTAMP, window_end TIMESTAMP, record_count INT,
merkle_root TEXT, tx_hash TEXT, chain_id INT, anchored_at TIMESTAMP
```

Bronze files are named `{source}_{UTC-timestamp}.json` and never modified. Silver/Gold can always be
rebuilt from Bronze.

## 5. Detection logic (the core of the project)

Step 1: graph. Nodes are stations. Edge weight Wij = exp(−d²/2σ²) if d ≤ τ (default 20 km) and i ≠ j,
else 0. Distance is haversine in km.

Step 2: wind weighting. For each station pair and timestamp, compute the cosine between the
vector from i to j and the direction the wind blows toward. Convert meteorological wind direction (where
wind comes from) to a travel vector first: u = −speed·sin(dir), v = −speed·cos(dir). Then
Aij,t = Wij·(1 + α·max(0, cos θij)·f(speed)), with f a bounded function such as min(speed/5, 2).
Treat α as a tuned parameter, not a constant from the papers.

Step 3: expected value and score. x̂i,t = Σ Aij,t·xj,t / Σ Aij,t; residual e = x − x̂; z = |e| / σi,
where σi is the residual std for that station over a healthy baseline window (use a robust estimate such as
1.4826·MAD). Optionally smooth with a rolling mean of |e| over T = 5 steps for slow drift.

Step 4: classify.

| Label | Rule (initial; tune on data) |
| --- | --- |
| VALID | z < 2.5, or fewer than 2 usable neighbors (then mark low-confidence, do not claim a fault). |
| VERIFIED_PLUME_EVENT | z ≥ 2.5 and at least one downwind neighbor shows a rise (relative to its own recent baseline) within a lag window of about 1–3 hours consistent with distance / wind speed. |
| SENSOR_FAULT_DRIFT | z ≥ 2.5 and neighbors (downwind first) stay near baseline; or a persistent smoothed residual indicates slow drift; or the series is flat/stuck/zero. |

Honesty rule: a single isolated spike can also be a very local real source. Label it as suspected fault and
say so in the UI; do not claim certainty the data cannot support.

## 6. Evaluation (what makes the demo credible)

Real data has no fault labels, so inject known faults into a copy of clean real readings and measure how
many are caught.

| Injected fault | How |
| --- | --- |
| Stuck / zero | Replace a window with a constant or zero. |
| Spike | Add a large short-lived jump to one station while neighbors are untouched. |
| Gradual drift / degradation | Multiply readings by 0.6–0.8 or add a slowly growing offset over many hours. |
| Real plume (negative control) | Add a spike to a station and a lagged, smaller spike to downwind neighbors; this must NOT be called a fault. |

Report precision, recall and F1 per fault type, and compare against a naive threshold baseline (e.g. flag
if PM2.5 > 150). Save results to reports/eval.json and a chart for the README and video. State
clearly that faults are synthetic.

## 7. Provenance: Merkle batches and the smart contract

- Batching: hourly batch of Gold records labelled VALID (and optionally the classified labels too, with
  the label included in the record).
- Canonical record: JSON with sorted keys, no whitespace, floats formatted to fixed precision (e.g. 4
  decimals), UTC ISO timestamps, UTF-8. Leaf = SHA-256 of that string.
- Tree: sort leaves by (station_id, ts); parent = SHA-256(left ‖ right) over raw bytes; if a level is odd,
  duplicate the last node. Document this choice, since it affects proofs.
- Hardening (recommended): prefix leaves and internal nodes with different bytes (e.g. 0x00 /
  0x01) to prevent second-preimage confusion.
- Proof: list of (sibling_hash, side) pairs from leaf to root. Verification recomputes the root and
  compares with the on-chain value.
- Honest framing: the chain proves a record existed unchanged at anchoring time; it does not prove
  the sensor was right. That is why validation happens first.

```solidity
// contracts/BatchRegistry.sol  (minimal; add tests)
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
contract BatchRegistry {
    address public immutable owner;
    struct Batch { bytes32 root; uint64 windowStart; uint64 windowEnd; uint32 count; uint64 anchoredAt; }
    mapping(bytes32 => Batch) public batches;          // key = keccak256(batchId string)
    event BatchAnchored(bytes32 indexed batchKey, bytes32 root, uint32 count);
    constructor() { owner = msg.sender; }
    function anchor(bytes32 key, bytes32 root, uint64 ws, uint64 we, uint32 count) external {
        require(msg.sender == owner, "not owner");
        require(batches[key].anchoredAt == 0, "already anchored");   // batches are write-once
        batches[key] = Batch(root, ws, we, count, uint64(block.timestamp));
        emit BatchAnchored(key, root, count);
    }
}
```

Never commit private keys. Use a throwaway testnet wallet loaded from .env. Add a unit test that a second anchor for
the same key reverts.

## 8. API and frontend

| Endpoint | Returns |
| --- | --- |
| GET /stations | Stations with coordinates and latest label. |
| GET /readings?station=&from=&to= | Time series with expected value, z, label. |
| GET /events?label= | Recent fault / plume events with wind context and neighbor evidence. |
| GET /batches | Batches with root, tx hash, chain and anchor time. |
| GET /proof?station=&ts= | Record, canonical string, Merkle path, root. |
| POST /verify | Upload a record; recompute hash and path; compare with on-chain root; return pass/fail with reason. |
| POST /chat (stretch) | NL question → SQL (validated) → rows → short summary. |

Screens: (1) Map with station markers coloured by label, wind arrow, click-through to a station chart
showing value vs expected with neighbors. (2) Batches/Verify page: pick a record, see its Merkle path,
press Verify, and see a green check plus the transaction link; edit one digit of the record and see it fail.
(3) Metrics page showing the evaluation chart.

Text-to-SQL guardrails (stretch): parse with a SQL parser, allow a single SELECT only, allow-list
tables/columns, enforce a LIMIT, run on a read-only DuckDB connection with a timeout, and unit-test
that DROP, UPDATE, ATTACH, COPY and multi-statement inputs are rejected.

## 9. Six-day plan (today is Oct 19)

| Day | Goal | Done when |
| --- | --- | --- |
| Mon Oct 19 (rest of day) | Scaffold repo, config, tests. Ingest OpenAQ + Open-Meteo for the chosen city, store Bronze, build Silver. | DuckDB query returns clean readings for ≥ 8 stations over ≥ 7 days. |
| Tue Oct 20 | Graph, wind weighting, expected value, z-scores, classifier v1. | Classifier labels a full week; unit tests pass. |
| Wed Oct 21 | Fault injection, evaluation vs baseline, tune α/τ/thresholds. Merkle module + tests. | eval.json and chart exist; Merkle proofs verify; tampering fails. |
| Thu Oct 22 | Contract, tests, testnet deploy, anchor.py, batches table, FastAPI endpoints. | A real tx hash is stored and /verify passes against the chain. |
| Fri Oct 23 | Frontend: map, station chart, verify page, metrics page. | Whole demo path works end to end locally. |
| Sat Oct 24 | Polish, README, architecture diagram, record 3–5 min video, draft Devpost text. Text-to-SQL only if everything above is solid. | Repo public, video uploaded, submission drafted. |
| Sun Oct 25 (morning) | Buffer. Fix bugs, re-check links, submit well before 7:00 pm GMT+5. | Submitted with time to spare. |

If you fall behind: cut the frontend metrics page, then text-to-SQL, then the wind-lag plume check (keep
neighbor-consensus faults). Never cut the contract + verify flow or the evaluation.

## 10. Working with Codex

Codex reads project instructions from an AGENTS.md file in the repo root. Put the block below there, then
give it one task at a time from the prompt list. Small, testable tasks with explicit acceptance criteria
work far better than “build the whole app”. Check Codex's current docs for any changes to how it loads
instructions.

```markdown
# AGENTS.md — EcoProof
## Goal
Verifiable air-quality data platform for a hackathon (deadline Oct 25, 2026). Real data, real tests,
no faked results. See docs/SPEC.md for the full spec.
## Rules
- Python 3.11, type hints, small functions. Run `pytest -q` before saying a task is done.
- Never commit secrets. Read keys from env (.env.example documents them).
- Bronze files are immutable. Silver/Gold must be rebuildable from Bronze with one command.
- Hashing: canonical JSON (sorted keys, no spaces, floats to 4 decimals, UTC ISO timestamps).
- SQL from any LLM path must pass src/ecoproof/sqlchat/guard.py (single SELECT, allow-list, LIMIT).
- Do not invent metrics. Evaluation numbers come from reports/eval.json produced by code.
- If a library or API detail is uncertain, check its docs or ask; do not guess endpoints.
## Commands
- make ingest | make build | make detect | make eval | make anchor | make api | make web | make test
## Definition of done (per task)
Code + unit tests + a short note in README if behavior or setup changed.
```

### Suggested prompt sequence

| # | Prompt to Codex (shortened) | Acceptance check |
| --- | --- | --- |
| 1 | Scaffold the repo per section 3 with config, Makefile, pytest, and .env.example. | make test runs (even if empty). |
| 2 | Implement ingest/openaq.py and openmeteo.py with caching to data/bronze and retry/backoff. Mock HTTP in tests. | Tests pass; one real pull saved. |
| 3 | Implement transform to Silver (validation rules from section 4, dedupe, UTC) and DuckDB views. | Constraint violations rejected in tests. |
| 4 | Implement graph/geo.py: haversine, adjacency with tau and sigma, wind weights with correct direction convention. | Known-distance and wind-direction unit tests. |
| 5 | Implement detect/classifier.py per section 5 with robust sigma and low-confidence handling. | Synthetic cases classify as expected. |
| 6 | Implement detect/inject.py and evaluate.py; write reports/eval.json and a chart. | Includes plume negative control. |
| 7 | Implement provenance/merkle.py with proofs and tampering tests (odd leaf count, single leaf, reordering). | All edge-case tests pass. |
| 8 | Write BatchRegistry.sol, tests, deploy script, and anchor.py. | Tx hash on testnet; revert test for duplicate batch. |
| 9 | Build FastAPI endpoints from section 8 with response models and tests. | OpenAPI docs render; verify endpoint works. |
| 10 | Build the React + Leaflet app: map, station chart, verify page, metrics page. | Demo path works against the local API. |
| 11 | (Stretch) sqlchat with guardrails and adversarial tests. | Write/multi-statement SQL rejected. |

## 11. Demo video outline (3–5 minutes)

| Time | Content |
| --- | --- |
| 0:00–0:30 | Problem: carbon markets, regulators and insurers rely on sensors that drift and fail; blockchain alone just preserves bad data. |
| 0:30–1:30 | Map with real stations. Open one station: a spike with flat neighbors → SENSOR_FAULT_DRIFT. Then a case where downwind neighbors rise later → VERIFIED_PLUME_EVENT. Say which events are injected tests and which are real. |
| 1:30–2:15 | Evaluation chart: our detector vs a fixed threshold, precision and recall by fault type. |
| 2:15–3:30 | Batch anchored on testnet (show the explorer link). Verify a record: pass. Change one digit: fail. |
| 3:30–4:15 | Impact and scale: carbon-credit MRV, parametric insurance, city air-quality programmes; how a new city is added; cost of anchoring one root per hour. |
| 4:15–4:45 | (Stretch) one natural-language question answered by guarded SQL. Close with the track statement. |

## 12. Risks and how to handle them

| Risk | Mitigation |
| --- | --- |
| Sparse stations in the chosen area | Choose the region by counting stations first; fall back to a denser city rather than weaken the graph logic. |
| API limits or outages | Cache to Bronze, pull a few days up front, and demo from stored data if the live call fails. |
| Too few real fault events | Use injection for evaluation and label it as such in the video and README. |
| Overclaiming | Do not present paper results (e.g. fold-improvements, tamper-detection rates) as your own. Report only your measured numbers. |
| Chain or wallet problems on demo day | Deploy and anchor early (Thu), keep the tx links, and keep a recorded fallback. |
| Scope creep | Follow the cut order in section 9. Freeze features Fri night. |

Before submitting, confirm every paper in the bibliography exists and says what you cite, and that eligibility rules
(students only, excluded regions, team rules) apply to you.

## 13. Submission checklist

- Track stated: Climate Data & Environmental Monitoring, with a two-sentence alignment explanation.
- Description covers problem, solution, target users, scalability, and adoption.
- Demo video 3–5 minutes, public link.
- Public GitHub repo with README (setup, architecture, demo steps, evaluation results, limitations) and
  an MIT or similar licence.
- Working prototype: local instructions that run from a clean clone, plus testnet contract address and
  sample transaction links.
- No secrets in git history. Submitted before Oct 25, 2026, 7:00 pm GMT+5.
