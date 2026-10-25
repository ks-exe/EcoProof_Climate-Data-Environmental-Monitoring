"""Check paired experiment inputs, then plot the actual before/after F1 values."""

import json
import os

from ecoproof.config import PROJECT_ROOT


def main() -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".cache/matplotlib"))
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    root = PROJECT_ROOT / "reports/detector-review"
    kinds = ("stuck", "zero", "spike", "drift", "degradation")
    summary = {}
    figure = Figure(figsize=(11, 8), layout="constrained")
    FigureCanvasAgg(figure)
    axes = figure.subplots(2, 1)
    for axis, period in zip(axes, ("development", "independent")):
        before_path = root / f"{period}-before/eval.json"
        if period == "development" and not before_path.exists():
            before_path = PROJECT_ROOT / "reports/history/2026-10-23-initial/eval.json"
        before = json.loads(before_path.read_text(encoding="utf-8"))
        after = json.loads((root / f"{period}-after/eval.json").read_text(encoding="utf-8"))
        for key in ("input_fingerprint_sha256", "detector_config", "evaluation_config", "station_coverage"):
            if before[key] != after[key]:
                raise ValueError(f"Unpaired {period} reports: {key} differs")
        def interventions(report: dict) -> list:
            return [(case["parameters"], [
                {key: item[key] for key in ("station_id", "ts", "original", "injected", "role")}
                for item in case["interventions"]
            ]) for case in report["cases"]]
        if interventions(before) != interventions(after):
            raise ValueError(f"Unpaired {period} interventions")
        results = {}
        for label, report, offset, color in (("before", before, -.2, "#94a3b8"), ("after", after, .2, "#0f766e")):
            scores = [report["metrics"][kind]["methods"]["ecoproof"]["f1"] for kind in kinds]
            bars = axis.bar([x + offset for x in range(len(kinds))], scores, .38, label=label.title(), color=color)
            axis.bar_label(bars, fmt="%.3f", fontsize=9, padding=3)
            plume = [case["plume_control"] for case in report["cases"] if case["kind"] == "plume"]
            results[label] = {
                "fault_metrics": {kind: report["metrics"][kind]["methods"]["ecoproof"] for kind in kinds},
                "unchanged_control": report["unchanged_control"]["ecoproof"],
                "plume_false_faults": sum(case["ecoproof_faults_on_plume"] for case in plume),
                "plume_affected_observations": sum(case["affected_observations"] for case in plume),
                "plume_negative_control_passed": report["plume_negative_control_passed"],
            }
        summary[period] = {
            "start_utc": after["start_utc"], "end_exclusive_utc": after["end_exclusive_utc"],
            "cases_per_type": after["evaluation_config"]["cases_per_type"],
            "seed": after["evaluation_config"]["seed"], "paired_inputs_and_interventions": True,
            **results,
        }
        axis.set(xticks=range(len(kinds)), xticklabels=[kind.title() for kind in kinds], ylim=(0, 1), ylabel="F1 (0–1)")
        axis.set_title(f"{period.title()} period: {after['start_utc'][:10]} to {after['end_exclusive_utc'][:10]} (end exclusive)")
        axis.legend(loc="upper right")
        axis.grid(axis="y", alpha=.2)
        axis.set_axisbelow(True)
        verdict = " → ".join(f"{results[label]['plume_false_faults']}/{results[label]['plume_affected_observations']}" for label in ("before", "after"))
        axis.set_xlabel(f"Plume observations incorrectly called faults, before → after: {verdict}")
    figure.suptitle("EcoProof: measured effect of the flatline correction\nSynthetic faults in copies of real Delhi observations", fontsize=14)
    figure.savefig(root / "comparison.png", dpi=160)
    (root / "comparison.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
