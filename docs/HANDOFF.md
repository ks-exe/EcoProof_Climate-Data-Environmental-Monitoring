# Submission handoff — October 24, 2026

The core EcoProof prototype has a real-data dashboard, measured injection
evaluation and one public Sepolia batch. The remaining submission actions belong
to the project owner: record/upload the video, check
eligibility and submit before **October 25, 2026, 19:00 GMT+5 (Pakistan time)**.

## Checklist against spec section 13

| Required item | Ready material / remaining action |
| --- | --- |
| Track and alignment | Two-sentence statement in [SUBMISSION.md](SUBMISSION.md#track-statement) |
| Problem, solution, users, scalability, adoption | [Submission description](SUBMISSION.md); adoption is proposed, not claimed |
| Public 3–5 minute video | Owner must record and publish; use the script below |
| Public GitHub repository | [EcoProof repository](https://github.com/ks-exe/EcoProof_Climate-Data-Environmental-Monitoring); README, lockfiles, architecture and MIT license are included |
| Working prototype and local setup | [README](../README.md#setup), [real demo](DEMO.md), fresh-checkout notes below |
| Testnet contract and example transaction | [Deployed registry](https://sepolia.etherscan.io/address/0xb120d4671607E7C24F6C14C4f23B589F5f4484EB), [anchor transaction](https://sepolia.etherscan.io/tx/0xbc325583e39e7778538a69878d9507281444a2e508ce13f048df455096ca5e49) |
| Secrets excluded | `.env`, databases and deployment journals are ignored; inspect staged files before publishing |
| Eligibility and final submission | Owner must check the official rules, team details, public links and receipt |

The [public repository](https://github.com/ks-exe/EcoProof_Climate-Data-Environmental-Monitoring)
was supplied on October 25. A video URL is still pending. A localhost dashboard URL
works on the computer running EcoProof; it is not a public hosting link.

## Verification performed for this handoff

A fresh export of the nonignored source files was installed with `uv sync
--locked` and clean npm installs on October 24. At the time of that check there
was no initial commit or remote, so it tested a source export rather than a
public Git clone.
The export contained no `.env` or database. The installed package was confirmed
to import that export's source rather than the original workspace.

The full exported-source suite passed **447 tests**, including the public-proof
checks and browser/EVM acceptance, after correcting a missing first-run test
directory parent. All 14 frontend unit tests, contract compilation and the
production frontend build passed. [PROGRESS.md](PROGRESS.md) preserves the exact
commands, output, earlier failure and three final warnings.

The independent public proof returned true / false / true for the original,
in-memory edit and restored record, with exit codes 0 / 1 / 0. Only the RPC was
provided to those processes. Fresh API documentation and frontend startup
returned HTTP 200; the empty-data route correctly returned HTTP 503. The saved
evaluation JSON and chart were served unchanged. See [actual check output](../reports/handoff-check.json).

This check did not repeat ingestion of the full real dataset in the export.
The populated original dashboard was checked separately in Chrome, including
its public verification flow. Full data rebuild commands and their earlier
measured results remain in [DEMO.md](DEMO.md).

## Fresh-checkout instructions

A checkout contains code, tests, evaluation artifacts and the public sample proof.
It deliberately has no local `.env`, observations database or transaction journals.
Starting the servers before ingesting/building data shows an unavailable-data
state; it does not reproduce the populated demonstration automatically.

Install Python 3.11 through uv, Node 22.13+ and Chrome (or the documented browser
alternative). From the repository root, install the locked dependencies:

```text
uv sync --locked
npm --prefix contracts ci
npm --prefix contracts run compile
npm --prefix web ci
npm --prefix web run build
```

Use `npm.cmd` in PowerShell if `npm.ps1` is blocked. Copy `.env.example` to `.env`
only when `.env` does not already exist. Set the credentials for the chosen action:

| Action | Required local configuration |
| --- | --- |
| Tests and viewing saved evaluation | No service credentials; browser/EVM tools above are required for the full tests |
| Independently verify the included public proof | `RPC_URL` for Ethereum Sepolia; no private key or database |
| Fetch real observations and populate Monitor | `OPENAQ_API_KEY`, then the ingestion, classification and batch preparation commands in [DEMO.md](DEMO.md#reproduce-the-data-run) |
| API verification of locally prepared records | `RPC_URL` and `REGISTRY_ADDRESS=0xb120d4671607E7C24F6C14C4f23B589F5f4484EB`; the record must match an anchored batch |
| Deploy or anchor a new batch | A funded testnet signing key; this is unnecessary for checking the existing public proof |

Provider responses can change. A new pull may produce different records, metrics
or roots; the published counts describe the saved October run. Preparing a new
batch does not anchor it, and rebuilding cannot recreate local transaction
history. Keep the original database and journals on the demo computer.

After preparing data, start these in two terminals at the repository root:

```text
uv run --locked make api
uv run --locked make web
```

Open <http://127.0.0.1:5173> and <http://127.0.0.1:8000/docs>. Stop those terminals
with Ctrl+C before rebuilding the database. Do not start duplicate servers.

## Verify the public sample without the operator's database

After Python setup and contract compilation, set only a working Sepolia
`RPC_URL` in the checkout's `.env`. Run:

```text
uv run --locked python scripts/verify_public_demo.py
uv run --locked python scripts/verify_public_demo.py --tamper
```

The first command must return `verified: true` and exit 0. The second adds one
to the sample's value in memory, must return `verified: false`, and exits 1.
Exit 2 means the check could not run, such as missing RPC or invalid input; it
is not a successful tampering test. `--record edited-record.json` accepts an
optional replacement twelve-field payload. No command here signs or sends a
transaction, edits the saved proof, or opens the local database.

The checker pins the published Sepolia registry and batch identity, reads the
current root and count from that contract, and verifies the saved sibling path.
It checks metadata and canonical payload consistency too. It relies on the
configured RPC's chain response. A passing proof establishes the canonical
record's inclusion in the commitment, not sensor accuracy. The explorer
transaction is supporting evidence, not a substitute for reading the root.

## Suggested 4 minute 30 second video

The complete word-for-word narration and screen recording instructions are in
[VIDEO_SCRIPT.md](VIDEO_SCRIPT.md).

Keep the demo running locally and open Monitor, Evaluation, Verify and the
anchor transaction in tabs before recording. Use [DEMO.md](DEMO.md) for the
saved-record link and actual screenshots if a service becomes unavailable;
label any recording/screenshot fallback as previously captured evidence.

| Time | Show | Suggested narration |
| --- | --- | --- |
| 0:00–0:30 | Monitor / project name | “Environmental decisions depend on sensor data, but a spike could be a failed sensor or real pollution. EcoProof combines a quality assessment with a record that an auditor can check for later changes.” |
| 0:30–1:25 | Real Delhi map, observed/expected chart, nearby station and event filters | “These are real OpenAQ observations with Open-Meteo wind context. The map includes 94 catalog locations; this run has readings from 12. Neighbor and wind evidence produce suspected-fault or plume-evidence labels, with uncertainty shown explicitly. These real events have no independent fault labels.” |
| 1:25–2:10 | Evaluation chart and confidence notice | “Evaluation injects faults into separate copies of the observations. Stuck and zero F1 are about 0.509 and 0.505 in this development run; spikes, drift and degradation remain weak. The plume control has zero false faults among eight affected observations, but seven remain uncertain. These are measured synthetic tests, not field accuracy.” |
| 2:10–3:25 | Verify, explorer transaction, original → edit → restore | “One seven-record batch is anchored on public Sepolia. This record is 22.0000: Verify passes. Changing it to 23.0000 fails; restoring it passes again. The chain protects the committed record from undetected changes; it cannot prove that a sensor was right.” |
| 3:25–4:05 | README architecture / saved proof | “Raw responses are cached, processed into DuckDB and Parquet, then classified and batched. One root represents an hour of eligible observations. A reviewer can check the included proof with a Sepolia RPC, without my database or private key. No operating-cost or throughput claim has been measured.” |
| 4:05–4:30 | Project / track / repository | “The track is Climate Data & Environmental Monitoring. Potential users are monitoring teams and auditors. The next engineering step is independent fault labeling and better validation, followed by a user pilot. The repository includes setup, tests, reports and honest limitations.” |

Concrete saved examples available through the event filters: station `4712609`
at `2026-10-11 06:00 UTC` has suspected persistent drift; the same station at
`2026-10-09 19:00 UTC` has downwind-lag evidence at two neighbors one hour later.
Show the recorded reasons, rather than describing either event as confirmed
ground truth. Public verification uses station `17`, `2026-10-11 23:00 UTC`.

## Owner's final actions

1. Review the [public source repository](https://github.com/ks-exe/EcoProof_Climate-Data-Environmental-Monitoring)
   and its README, LICENSE, code, tests, lockfiles, docs and public reports.
   Keep local `.env`, `.cache`, dependencies and data journals out of future commits.
2. Record/upload a narrated 3–5 minute video. Open the video and repository URLs
   in a signed-out browser to confirm they are publicly accessible.
3. Add those real URLs and the public transaction link to the submission form.
   Adapt [SUBMISSION.md](SUBMISSION.md) to its fields without increasing the
   measured claims. Confirm team eligibility against the official rules.
4. Submit before the deadline and retain the platform's confirmation. A local
   draft or a saved form is not proof of a completed submission.

AWS hosting and SQL chat are outside this submission handoff. The detector's
remaining accuracy limitations should stay visible in both the video and repo.
