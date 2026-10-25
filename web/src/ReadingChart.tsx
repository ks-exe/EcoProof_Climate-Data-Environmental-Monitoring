import { lineSegments, number } from './domain';
import type { Reading } from './types';

export interface Comparison {name: string; rows: Reading[]; color: string}
export function ReadingChart({rows, comparisons, start, end}: {rows: Reading[]; comparisons: Comparison[]; start: string; end: string}) {
  const width = 900, height = 260, left = 48, top = 24, right = 20, bottom = 42;
  const from = Date.parse(start), to = Date.parse(end);
  const values = [...rows.flatMap(r => [r.value, r.expected ?? 0]), ...comparisons.flatMap(s => s.rows.map(r => r.value))];
  const maximum = Math.max(10, Math.ceil(Math.max(...values, 0) / 10) * 10);
  const x = (time: number) => left + (time - from) / (to - from) * (width - left - right);
  const y = (value: number) => height - bottom - value / maximum * (height - top - bottom);
  const series = [{name: 'Observed', rows, field: 'value' as const, color: '#226a52', dash: undefined},
    {name: 'Expected', rows, field: 'expected' as const, color: '#383f4a', dash: '6 5'},
    ...comparisons.map(s => ({...s, field: 'value' as const, dash: '3 5'}))];
  return <div className="chart-wrap">
    <div className="chart-legend">{series.map(s => <span key={s.name}><i style={{background: s.color}}/>{s.name}</span>)}</div>
    <svg className="reading-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Observed and expected hourly PM2.5 with nearby station comparisons. Missing hours remain gaps.">
      <text x={left} y={12} className="axis-label">PM2.5 · µg/m³</text>
      {[0, 1, 2, 3, 4].map(n => <g key={n}>
        <line x1={left} y1={y(maximum * n / 4)} x2={width - right} y2={y(maximum * n / 4)} className="gridline"/>
        <text x={left - 10} y={y(maximum * n / 4) + 4} textAnchor="end" className="axis-label">{number(maximum * n / 4)}</text>
        <text x={x(from + (to - from) * n / 4)} y={height - 16} textAnchor={n === 0 ? 'start' : n === 4 ? 'end' : 'middle'} className="axis-label">
          {new Date(from + (to - from) * n / 4).toISOString().slice(5, 16).replace('T', ' ')}
        </text>
      </g>)}
      {series.map(s => <g key={s.name} stroke={s.color} fill={s.color}>
        {lineSegments(s.rows, s.field).map((segment, index) => <g key={index}>
          <path d={segment.map((p, i) => `${i ? 'L' : 'M'} ${x(p.time)} ${y(p.value)}`).join(' ')} fill="none" strokeWidth={s.name === 'Observed' ? 2.8 : 1.7} strokeDasharray={s.dash}/>
          {segment.map(p => <circle key={p.time} cx={x(p.time)} cy={y(p.value)} r={s.name === 'Observed' ? 3.5 : 2} strokeWidth="0"><title>{s.name} · {new Date(p.time).toISOString()} · {p.value} µg/m³</title></circle>)}
        </g>)}
      </g>)}
    </svg>
    <p className="caption">All times UTC · Hourly observations · Gaps are not interpolated</p>
  </div>;
}
