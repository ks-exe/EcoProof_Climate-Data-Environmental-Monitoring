import { useState } from 'react';
import { useResource } from './api';
import { Loading, Notice } from './components';
import { utc } from './domain';
import type { Evaluation as Report } from './types';

export function validReport(report: Report): boolean {
  if (report.schema_version !== 1 || !['blocked', 'complete'].includes(report.status)
      || !/^eval-[a-f0-9]{32}\.png$/.test(report.chart) || report.synthetic_interventions !== true
      || typeof report.input_kind !== 'string'
      || ![report.start_utc, report.end_exclusive_utc, report.generated_at_utc].every(value => typeof value === 'string' && Number.isFinite(Date.parse(value)))) return false;
  if (report.status === 'blocked') return report.metrics === null;
  if (!report.metrics || typeof report.metrics !== 'object' || !Object.keys(report.metrics).length) return false;
  return Object.values(report.metrics).every(group => group && group.methods && typeof group.methods === 'object'
    && Number.isInteger(group.case_count) && group.case_count >= 0
    && ['ecoproof', 'threshold'].every(method => group.methods[method] && ['precision', 'recall', 'f1'].every(name => {
      const value = group.methods[method][name as 'precision' | 'recall' | 'f1'];
      return value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1);
    })));
}
export const ratio = (value: number | null) => value === null ? 'Undefined' : `${(value * 100).toFixed(1)}%`;

export function Evaluation() {
  const [revision, setRevision] = useState(0);
  const [failedChart, setFailedChart] = useState('');
  const report = useResource<Report>('/reports/eval.json', revision);
  const data = report.data;
  return <>
    <div className="page-heading"><div><p className="eyebrow">Measured, not assumed</p><h1>Evaluate the detector.</h1><p>Known faults in copied observations, compared with a fixed threshold.</p></div><button className="button secondary" disabled={report.loading} onClick={() => {setFailedChart(''); setRevision(n => n + 1);}}>↻ Refresh report</button></div>
    {report.loading && <Loading text="Loading the evaluation report…"/>}
    {report.error && <Notice title="Evaluation unavailable" error>{report.error}</Notice>}
    {data && (!validReport(data) ? <Notice title="Evaluation report is invalid" error>No metrics are shown because the report does not match the expected schema.</Notice> : <>
      <div className="evaluation-banner"><span className="tag">Synthetic interventions</span><p>Faults and plume controls are injected into copies. These results do not establish accuracy on real, independently labeled sensor faults.</p></div>
      <section className="panel"><div className="section-heading"><div><p className="eyebrow">Published evaluation</p><h2>{data.status === 'blocked' ? 'Evaluation has not run' : 'Detection results'}</h2></div><span className={`badge ${data.status === 'blocked' ? 'low' : 'valid'}`}><i/>{data.status === 'blocked' ? 'Blocked' : 'Complete'}</span></div>
        {data.status === 'blocked' && <Notice title="No measured results are available">{data.reason || 'The required evaluation inputs are not available.'}</Notice>}
        <dl className="report-meta"><div><dt>Region</dt><dd>{data.region_id || 'Not specified'}</dd></div><div><dt>Input</dt><dd>{data.input_kind === 'silver_observations' ? 'Silver observations' : data.input_kind}</dd></div>
          <div><dt>Window (UTC, end exclusive)</dt><dd>{utc(data.start_utc)} → {utc(data.end_exclusive_utc)}</dd></div><div><dt>Generated</dt><dd>{utc(data.generated_at_utc)}</dd></div></dl>
        {failedChart === data.chart ? <Notice title="Evaluation chart unavailable">The referenced image could not be loaded.</Notice>
          : <img key={`${data.chart}:${revision}`} className="evaluation-chart" src={`/reports/${data.chart}`} alt={data.status === 'blocked' ? 'Evaluation not run: the generated report contains no measured metrics.' : 'Measured fault-injection precision, recall and F1 compared with the threshold baseline.'} onError={() => setFailedChart(data.chart)}/>}
        {data.status === 'complete' && data.metrics && <><div className="table-scroll"><table><thead><tr><th>Injection</th><th>Method</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead><tbody>
          {Object.entries(data.metrics).flatMap(([kind, group]) => ['ecoproof', 'threshold'].map(method => <tr key={`${kind}:${method}`}><td>{kind.replaceAll('_', ' ')}</td><td>{method === 'ecoproof' ? 'EcoProof' : 'Threshold baseline'}</td>
            <td>{ratio(group.methods[method].precision)}</td><td>{ratio(group.methods[method].recall)}</td><td>{ratio(group.methods[method].f1)}</td></tr>))}
        </tbody></table></div><p className="caption">Undefined ratios are preserved. No missing metric is replaced with zero.</p>
          <Notice title={`Plume negative control: ${data.plume_negative_control_passed === true ? 'passed' : data.plume_negative_control_passed === false ? 'failed' : 'not determined'}`}>This checks false fault calls on injected plume patterns, not proof of atmospheric transport.</Notice></>}
        <a className="text-link" href="/reports/eval.json" download="eval.json">Download the source report ↓</a>
      </section>
    </>)}
  </>;
}
