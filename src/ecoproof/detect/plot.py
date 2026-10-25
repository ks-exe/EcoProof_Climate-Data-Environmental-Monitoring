"""Standalone evaluation figures rendered from the saved JSON report contents."""

import os
from pathlib import Path
import textwrap
from typing import Any

from ecoproof.config import PROJECT_ROOT
from ecoproof.detect.inject import FAULT_KINDS


def render_evaluation(report: dict[str, Any], destination: Path) -> None:
    """Use a headless Matplotlib canvas; a blocked report contains no plotted metrics."""
    previous = os.environ.get('MPLCONFIGDIR')
    if previous is None:
        cache = PROJECT_ROOT / '.cache' / 'matplotlib'
        cache.mkdir(parents=True, exist_ok=True)
        os.environ['MPLCONFIGDIR'] = str(cache)
    try:
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure

        if report['status'] != 'complete':
            figure = Figure(figsize=(11, 4), facecolor='#f8fafc')
            FigureCanvasAgg(figure)
            figure.text(.07, .77, 'EVALUATION NOT RUN', fontsize=24, weight='bold', color='#9a3412')
            figure.text(.07, .56, textwrap.fill(report['reason'], width=94), fontsize=12, va='top', linespacing=1.5)
            figure.text(.07, .20, 'No precision, recall, F1, or plume-control result is available.', fontsize=12)
            figure.text(.07, .10, 'Provide real air observations, then rerun make eval.', fontsize=11, color='#475569')
        else:
            figure = Figure(figsize=(13, 6), facecolor='white')
            FigureCanvasAgg(figure)
            synthetic = report['input_kind'] == 'synthetic_fixture'
            title = 'SYNTHETIC FIXTURE — software test only' if synthetic else 'Synthetic fault injection on Silver observations'
            figure.suptitle(title, fontsize=17, weight='bold', y=.96)
            axes = figure.subplots(1, 3)
            for axis, metric in zip(axes, ('precision', 'recall', 'f1')):
                for offset, method, color, label in ((-.19, 'ecoproof', '#047857', 'EcoProof'),
                                                    (.19, 'threshold', '#64748b', f"PM2.5 > {report['evaluation_config']['threshold']:g}")):
                    values = [report['metrics'][kind]['methods'][method][metric] for kind in FAULT_KINDS]
                    positions = [index + offset for index in range(len(FAULT_KINDS))]
                    axis.bar(positions, [0 if value is None else value for value in values], width=.36, color=color, label=label)
                    for position, value in zip(positions, values):
                        if value is None:
                            axis.text(position, .04, 'n/a', ha='center', va='bottom', rotation=90, fontsize=8)
                axis.set_xticks(range(len(FAULT_KINDS)), [kind.title() for kind in FAULT_KINDS], rotation=35, ha='right')
                axis.set_ylim(0, 1.08)
                axis.set_title(metric.upper() if metric == 'f1' else metric.title())
                axis.spines[['top', 'right']].set_visible(False)
                axis.grid(axis='y', alpha=.2)
                axis.set_axisbelow(True)
            axes[0].legend(fontsize=8, loc='upper right')
            controls = [case['plume_control'] for case in report['cases'] if case['kind'] == 'plume']
            total = sum(case['affected_observations'] for case in controls)
            ours = sum(case['ecoproof_faults_on_plume'] for case in controls)
            naive = sum(case['threshold_faults_on_plume'] for case in controls)
            low = sum(case['low_confidence_on_plume'] for case in controls)
            figure.text(.06, .12, f'Plume negative control: false fault calls on affected observations — EcoProof {ours}/{total}; threshold {naive}/{total}.', fontsize=11)
            figure.text(.06, .075, f'EcoProof low confidence on plume observations: {low}/{total}. Undefined ratios are n/a.', fontsize=10, color='#475569')
            figure.text(.06, .03, 'Independent injected copies; full observed-window scoring. Unchanged background is presumed healthy, not ground-truth labeled.', fontsize=9, color='#475569')
            figure.subplots_adjust(left=.06, right=.98, top=.85, bottom=.33, wspace=.30)
        figure.savefig(destination, format='png', dpi=160)
        figure.clear()
    finally:
        if previous is None:
            os.environ.pop('MPLCONFIGDIR', None)
        else:
            os.environ['MPLCONFIGDIR'] = previous
