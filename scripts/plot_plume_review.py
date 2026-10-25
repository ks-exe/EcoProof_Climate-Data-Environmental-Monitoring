"""Validate paired experiments and plot their measured fault and plume results."""

from collections import Counter
import json
import os

from ecoproof.config import PROJECT_ROOT


def interventions(report: dict) -> list:
    return [(case['parameters'], [
        {key: item[key] for key in ('station_id', 'ts', 'original', 'injected', 'role')}
        for item in case['interventions']
    ]) for case in report['cases']]


def summarize(report: dict) -> dict:
    controls = [case['plume_control'] for case in report['cases'] if case['kind'] == 'plume']
    return {
        'fault_metrics': {kind: row['methods']['ecoproof'] for kind, row in report['metrics'].items() if kind != 'plume'},
        'unchanged_control': report['unchanged_control']['ecoproof'],
        'plume_false_faults': sum(row['ecoproof_faults_on_plume'] for row in controls),
        'plume_affected_observations': sum(row['affected_observations'] for row in controls),
        'plume_low_confidence': sum(row['low_confidence_on_plume'] for row in controls),
        'plume_source_labels': dict(Counter(label for row in controls for label in row['source_labels'])),
        'plume_negative_control_passed': report['plume_negative_control_passed'],
        'detector_source_sha256': report['detector_source_sha256'],
    }


def main() -> None:
    os.environ.setdefault('MPLCONFIGDIR', str(PROJECT_ROOT / '.cache/matplotlib'))
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    root = PROJECT_ROOT / 'reports/plume-review'
    kinds = ('stuck', 'zero', 'spike', 'drift', 'degradation')
    figure = Figure(figsize=(11, 11), layout='constrained')
    FigureCanvasAgg(figure)
    summary = {}
    for axis, period in zip(figure.subplots(3, 1), ('development', 'regression', 'validation')):
        reports = {revision: json.loads((root / f'{period}-{revision}/eval.json').read_text(encoding='utf-8'))
                   for revision in ('before', 'after')}
        before, after = reports['before'], reports['after']
        for key in ('input_fingerprint_sha256', 'detector_config', 'evaluation_config', 'station_coverage'):
            if before[key] != after[key]:
                raise ValueError(f'Unpaired {period} reports: {key}')
        if interventions(before) != interventions(after):
            raise ValueError(f'Unpaired {period} interventions')
        rows = {revision: summarize(report) for revision, report in reports.items()}
        summary[period] = {'start_utc': after['start_utc'], 'end_exclusive_utc': after['end_exclusive_utc'],
                           'input_fingerprint_sha256': after['input_fingerprint_sha256'],
                           'cases_per_type': after['evaluation_config']['cases_per_type'],
                           'seed': after['evaluation_config']['seed'],
                           'paired_inputs_and_interventions': True, **rows}
        for revision, offset, color in (('before', -.2, '#94a3b8'), ('after', .2, '#0f766e')):
            bars = axis.bar([index + offset for index in range(len(kinds))],
                            [rows[revision]['fault_metrics'][kind]['f1'] for kind in kinds],
                            .38, label=revision.title(), color=color)
            axis.bar_label(bars, fmt='%.3f', fontsize=9, padding=3)
        axis.set(xticks=range(len(kinds)), xticklabels=[kind.title() for kind in kinds],
                 ylim=(0, 1), ylabel='F1 (0–1)')
        axis.set_title(f"{period.title()}: {after['start_utc'][:10]} to {after['end_exclusive_utc'][:10]} (end exclusive)")
        axis.legend(loc='upper right')
        axis.grid(axis='y', alpha=.2)
        axis.set_axisbelow(True)
        faults = ' → '.join(f"{rows[revision]['plume_false_faults']}/{rows[revision]['plume_affected_observations']}" for revision in rows)
        low = ' → '.join(str(rows[revision]['plume_low_confidence']) for revision in rows)
        axis.set_xlabel(f'Plume observations called faults: {faults}; low confidence: {low}')
    figure.suptitle('EcoProof: measured effect of the plume ambiguity safeguard\nSynthetic interventions in copies of real Delhi observations', fontsize=14)
    figure.savefig(root / 'comparison.png', dpi=160)
    (root / 'comparison.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
