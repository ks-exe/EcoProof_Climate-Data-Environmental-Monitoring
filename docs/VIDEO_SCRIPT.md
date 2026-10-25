# EcoProof — Full demo video script and recording guide

Aim for **4 minutes 30 seconds to 4 minutes 50 seconds**. Make the record
verification — **original passes, edited value fails, restored value passes** —
the main demonstration.

Read the quoted paragraphs aloud. The screen instructions are for you, not part
of the narration. Replace `[your name]` before recording.

## Before recording

Open these tabs:

- [Dashboard / Monitor](http://127.0.0.1:5173)
- [Evaluation](http://127.0.0.1:5173/#evaluation)
- [The exact record to verify](http://127.0.0.1:5173/#verify?station=17&ts=2026-10-11T23%3A00%3A00.000000Z&batch=ecoproof%3Av1%3Avalid%3A20261011T230000Z%3Ae7aaf8938d201639002bfed699ed30b73674746c28d460ad4f1ce594aa67efc0)
- [Public Sepolia transaction](https://sepolia.etherscan.io/tx/0xbc325583e39e7778538a69878d9507281444a2e508ce13f048df455096ca5e49)
- [README architecture](../README.md#layout-and-intended-architecture), preferably in its Markdown preview.

The dashboard and API documentation returned HTTP 200 when checked for this
script on October 24, 2026. Check they are available again before recording;
local links require the application to be running. Startup instructions are in
[DEMO.md](DEMO.md#open-the-application).

Use a screen recorder at **1080p**, enable your microphone, and disable
notifications. Keep `.env`, private keys and credential pages out of the
recording.

## 1. 0:00–0:25 — Introduce the problem and project

**Record:** Start on the dashboard with the EcoProof name and map visible. You
can briefly show your name and team name as a caption.

**Say:**

> Hi, I’m [your name], and this is EcoProof.
>
> Environmental decisions depend on sensor data, but sensors can drift, get
> stuck, or report unusual spikes. Real pollution can also look like a sensor
> problem.
>
> EcoProof combines checks of data quality with blockchain verification, so
> users can inspect the evidence behind a reading and detect later changes.

## 2. 0:25–1:00 — Demonstrate the real observations

**Record:** Show the map, search for **R K Puram**, select it, and scroll to its
chart. Use **Compare a nearby station** to add a comparison line. Point briefly
to the observed value, expected value and wind information.

**Say:**

> This demonstration uses cached real observations from OpenAQ, with weather
> and wind context from Open-Meteo.
>
> The map contains 94 catalog locations. Our recorded data run collected
> approximately 7,600 PM2.5 readings from 12 Delhi locations.
>
> Selecting a station shows its observations alongside an expected value
> calculated from neighboring stations. We can also compare a nearby station
> and inspect the wind context. Missing observations remain gaps rather than
> being filled with invented readings.

## 3. 1:00–1:40 — Explain suspected faults and plume evidence

**Record:** Scroll to **Recent events**. In **Show**, select **Suspected faults**
and demonstrate this saved event:

**Air Check**, station `4712609`, **October 11, 2026, 06:00 UTC**.

Click **Inspect event readings →** briefly. Then return to Recent events,
change **Show** to **Plume evidence**, and expand **Neighbor evidence** for:

**Air Check**, **October 9, 2026, 19:00 UTC**.

**Say:**

> EcoProof combines geographic neighbors, wind direction and changes over time.
>
> This event is flagged as suspected persistent drift because its difference
> from the expected value stays elevated.
>
> In this other event, the saved evidence shows two downwind neighbors rising
> one hour later. That supports a possible pollution plume.
>
> These are heuristic assessments of real observations, not independently
> confirmed sensor failures or pollution events. When the evidence is
> insufficient or conflicting, the system preserves uncertainty.

## 4. 1:40–2:20 — Show measured evaluation

**Record:** Switch to Evaluation. Show the chart, the comparison with the
threshold method, and the plume-control confidence notice. Keep the weaker
results visible.

**Say:**

> Because these observations do not come with confirmed fault labels, we
> evaluate using known faults injected into separate copies of the data.
>
> The chart compares EcoProof with a simple pollution threshold. In this
> development experiment, F1 is approximately 0.51 for stuck readings and 0.50
> for zero readings. Spike, drift and degradation detection still need
> improvement.
>
> None of the eight affected plume-control observations were classified as
> faults, but seven remain uncertain. These results measure synthetic
> interventions, not established field accuracy.

## 5. 2:20–3:40 — Perform the blockchain verification

**Record this sequence continuously.** Open the exact record link above.
Briefly show its hash and Merkle path, then scroll to **Record JSON**.

**Say:**

> Now I’ll demonstrate the audit workflow.
>
> This R K Puram observation belongs to a seven-record batch anchored on
> Ethereum Sepolia. The record has a hash and a Merkle proof, which lets us
> check its inclusion in the batch.

**Click `Verify record`. Wait until the green result appears.**

> The original value is 22.0000. Clicking Verify reads the public registry and
> checks the proof against its stored commitment. The original record passes.

**In Record JSON, change only:**

```text
"value":22.0000
```

**to:**

```text
"value":23.0000
```

**Click `Verify record` again. Pause on the failure message.**

> I’ll change just the value to 23.0000. Verification now fails because the
> edited record no longer matches the commitment.

**Click `Restore saved record`, then `Verify record`. Pause on the green result.**

> Restoring the original makes verification pass again.

**Open `View transaction` or switch to the prepared explorer tab. Show its
successful transaction status.**

> This is the actual public testnet transaction.
>
> The blockchain verifies the committed record’s integrity. It does not
> establish that the sensor was correct.

## 6. 3:40–4:20 — Explain the architecture and practical use

**Record:** Show the README architecture. If convenient, briefly show the
recorded test summary from [PROGRESS.md](PROGRESS.md). Do not rerun the full
suite during recording.

**Say:**

> The pipeline preserves raw responses, validates them into Parquet and DuckDB,
> and applies the station graph and classifier. Eligible records are grouped
> into hourly Merkle batches, while FastAPI and React provide the dashboard.
>
> The latest complete software run passed 447 tests.
>
> A reviewer can also verify the included public proof without our database
> or private key. Potential users include monitoring teams and auditors.
> Adding another city would require checking station coverage, recalibrating
> and validating the detector. Operating costs at scale have not yet been
> measured.

## 7. 4:20–4:50 — Close with the track and next step

**Record:** Return to the dashboard. Display the project name, team name, and
your GitHub URL:
<https://github.com/ks-exe/EcoProof_Climate-Data-Environmental-Monitoring>.

**Say:**

> EcoProof is built for the Climate Data & Environmental Monitoring track.
>
> It brings together explainable checks of air-quality observations, visible
> uncertainty and independently verifiable records.
>
> Our next step is stronger validation against independently labeled faults,
> followed by a pilot with monitoring users.
>
> The repository includes setup instructions, tests, evaluation reports and
> the public proof. Thank you.

## Recording and upload checklist

Record the seven sections as separate clips if that makes narration easier,
then join them in order. Keep the original → edit → restore verification
sequence together so viewers can follow what changed.

- Confirm the text is readable and your voice is clear.
- Keep the finished video under five minutes; the required range is 3–5 minutes.
- Check that the uploaded link works without signing in.
- Describe the inputs as **real historical observations**, the evaluation faults
  as **synthetic**, and the blockchain as **Sepolia testnet**.

The narration's metrics and test count refer to the saved October 24 results.
If you later change the detector or dataset, check the current reports before
reusing those claims. See [HANDOFF.md](HANDOFF.md) for the final submission
checklist and [DEMO.md](DEMO.md) for the detailed demo evidence.
