import { useEffect, useState } from 'react';
import { query, requestJSON, useResource } from './api';
import { Badge, Loading, Notice, Wind } from './components';
import { HOUR, nearby, number, utc } from './domain';
import { ReadingChart, type Comparison } from './ReadingChart';
import type { Reading, Station } from './types';

export type OpenProof = (station: string, ts: string, batch: string | null) => void;

export function StationDetail({station, stations, focus, onVerify}: {station: Station; stations: Station[]; focus?: string; onVerify: OpenProof}) {
  const anchor = focus || station.latest?.ts;
  const initialEnd = anchor ? new Date(Date.parse(anchor) + HOUR).toISOString() : '';
  const initialStart = anchor ? new Date(Date.parse(anchor) - 23 * HOUR).toISOString() : '';
  const [bounds, setBounds] = useState({start: initialStart, end: initialEnd});
  const [draft, setDraft] = useState({start: initialStart.slice(0, 16), end: initialEnd.slice(0, 16)});
  const [formError, setFormError] = useState('');
  const [revision, setRevision] = useState(0);
  const [compareId, setCompareId] = useState('');
  const [comparison, setComparison] = useState<{key: string; series: Comparison | null; error: string}>({key: '', series: null, error: ''});
  const url = bounds.start && bounds.end ? query('readings', {station: station.station_id, from: bounds.start, to: bounds.end}) : null;
  const readings = useResource<Reading[]>(url, revision);
  const neighbors = nearby(station, stations);
  const compareKey = `${compareId}:${bounds.start}:${bounds.end}:${revision}`;
  useEffect(() => {
    const controller = new AbortController();
    if (compareId && bounds.start && bounds.end) {
      requestJSON<Reading[]>(query('readings', {station: compareId, from: bounds.start, to: bounds.end}), {signal: controller.signal}).then(
        rows => { if (!controller.signal.aborted) setComparison({key: compareKey, series: {name: `Nearby ${compareId}`, rows, color: '#b47735'}, error: ''}); },
        error => { if (!controller.signal.aborted) setComparison({key: compareKey, series: null, error: error.message}); },
      );
    }
    return () => controller.abort();
  }, [compareId, bounds.start, bounds.end, revision, compareKey]);
  const selectedComparison = comparison.key === compareKey ? comparison : null;
  const [selectedTime, setSelectedTime] = useState(focus || '');
  const selected = readings.data?.find(row => row.ts === selectedTime) ?? readings.data?.at(-1) ?? null;
  return <section className="panel station-detail" aria-labelledby="station-heading">
    <div className="section-heading"><div><p className="eyebrow">Station detail</p><h2 id="station-heading">{station.name || station.station_id}</h2>
      <p className="muted">{station.provider || 'Provider not recorded'} · {station.lat.toFixed(4)}°, {station.lon.toFixed(4)}°</p></div><Badge reading={station.latest}/></div>
    {!anchor ? <Notice title="No classified readings">This station has a location but no current classification to chart.</Notice> : <>
      <form className="range-form" onSubmit={event => {
        event.preventDefault();
        const start = new Date(`${draft.start}:00Z`), end = new Date(`${draft.end}:00Z`);
        if (!Number.isFinite(+start) || !Number.isFinite(+end) || +end <= +start || +end - +start > 31 * 24 * HOUR) {
          setFormError('Choose a UTC interval of up to 31 days, with the end after the start.'); return;
        }
        setFormError(''); setBounds({start: start.toISOString(), end: end.toISOString()});
      }}>
        <label>From (UTC)<input type="datetime-local" value={draft.start} required onChange={e => setDraft({...draft, start: e.target.value})}/></label>
        <label>To, exclusive (UTC)<input type="datetime-local" value={draft.end} required onChange={e => setDraft({...draft, end: e.target.value})}/></label>
        <button className="button secondary" type="submit">Apply window</button>
      </form>
      {formError && <Notice title="Check the time window" error>{formError}</Notice>}
      <label className="compare-label">Compare a nearby station
        <select value={compareId} onChange={e => setCompareId(e.target.value)}><option value="">No comparison</option>
          {neighbors.map(({station: s, km}) => <option key={s.station_id} value={s.station_id}>{s.name || s.station_id} · {number(km)} km</option>)}
        </select>
      </label>
      <p className="caption">Geographic context within 20 km in this cluster. These are not necessarily the neighbors used by the detector.</p>
      {readings.loading && <Loading/>}
      {readings.error && <Notice title="Readings unavailable" error>{readings.error}<button className="text-button" onClick={() => setRevision(r => r + 1)}>Retry readings</button></Notice>}
      {selectedComparison?.error && <Notice title="Nearby readings unavailable">{selectedComparison.error}</Notice>}
      {compareId && !selectedComparison && <p role="status" className="caption">Loading nearby observations…</p>}
      {selectedComparison?.series?.rows.length === 0 && <p className="caption">No comparison observations in this window.</p>}
      {readings.data && (readings.data.length ? <>
        <ReadingChart rows={readings.data} comparisons={selectedComparison?.series ? [selectedComparison.series] : []} start={bounds.start} end={bounds.end}/>
        {selected && <div className="reading-inspector">
          <div className="inspector-heading"><span className="mono">{utc(selected.ts)}</span><Badge reading={selected}/></div>
          <div className="reading-stats"><div><span>Observed</span><strong>{number(selected.value)} <small>µg/m³</small></strong></div><div><span>Expected</span><strong>{number(selected.expected)}</strong></div>
            <div><span>Residual z</span><strong>{number(selected.z, 2)}</strong></div><div><span>Usable neighbors</span><strong>{selected.neighbor_count}</strong></div></div>
          <Wind reading={selected}/><p>{selected.reason}</p>
          <button className="button" disabled={!selected.batch_id} onClick={() => onVerify(selected.station_id, selected.ts, selected.batch_id)}>Inspect record proof <span aria-hidden="true">↗</span></button>
          {!selected.batch_id && <p className="caption">No prepared proof for this record. Batches currently include confident VALID readings only.</p>}
        </div>}
        <details className="readings-table"><summary>Observed rows ({readings.data.length})</summary><div className="table-scroll"><table><thead><tr><th>Hour (UTC)</th><th>Observed</th><th>Expected</th><th>Classification</th><th>Inspect</th></tr></thead>
          <tbody>{readings.data.map(row => <tr key={row.ts}><td className="mono">{utc(row.ts)}</td><td>{number(row.value)}</td><td>{number(row.expected)}</td><td><Badge reading={row}/></td><td><button className="text-button" onClick={() => setSelectedTime(row.ts)}>Select hour</button></td></tr>)}</tbody>
        </table></div></details>
      </> : <Notice title="No observations in this window">Try another interval. Missing hours have not been filled.</Notice>)}
    </>}
  </section>;
}
