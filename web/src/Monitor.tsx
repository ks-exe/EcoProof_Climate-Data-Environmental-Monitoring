import { useCallback, useState } from 'react';
import { useResource } from './api';
import { Badge, Loading, Notice, Wind } from './components';
import { number, status, utc } from './domain';
import { StationDetail, type OpenProof } from './StationDetail';
import { StationMap } from './StationMap';
import type { Event, Station } from './types';

export function Monitor({stations, loading, error, revision, refresh, onVerify}: {stations: Station[]; loading: boolean; error: string | null; revision: number; refresh: () => void; onVerify: OpenProof}) {
  const [selection, setSelection] = useState<{id: string; focus?: string}>({id: ''});
  const [search, setSearch] = useState('');
  const [eventLabel, setEventLabel] = useState('');
  const selected = stations.find(s => s.station_id === selection.id) ?? stations.find(s => s.latest) ?? stations[0];
  const onSelect = useCallback((id: string) => setSelection({id}), []);
  const events = useResource<Event[]>(`/api/events?limit=12${eventLabel ? `&label=${eventLabel}` : ''}`, revision);
  const filtered = stations.filter(s => `${s.name} ${s.station_id} ${s.cluster_id}`.toLowerCase().includes(search.toLowerCase()));
  const classified = stations.filter(s => s.latest);
  const latest = classified.map(s => s.latest!.ts).sort().at(-1);
  return <>
    <div className="page-heading"><div><p className="eyebrow">Observation network</p><h1>Air quality, with evidence.</h1><p>Follow the readings. Inspect the context. Verify the record.</p></div>
      <button className="button secondary" onClick={refresh} disabled={loading}>↻ Refresh observations</button></div>
    {error && <Notice title="Station data unavailable" error>{error}</Notice>}
    <div className="overview-stats">
      {[['Stations', stations.length, 'Locations in the current dataset'], ['Suspected faults', stations.filter(s => status(s.latest).tone === 'fault').length, 'Latest classification per station'],
        ['Plume evidence', stations.filter(s => status(s.latest).tone === 'plume').length, 'Supported by neighbor observations'], ['Low confidence', stations.filter(s => s.latest?.low_confidence).length, 'Needs more supporting evidence']].map(([title, value, caption]) =>
        <div key={title} className="stat"><span>{title}</span><strong>{loading || error ? '—' : value}</strong><small>{caption}</small></div>)}
    </div>
    <section className="panel network-panel" aria-label="Station network">
      <div className="section-heading"><div><h2>Station network</h2><p className="muted">{latest ? `Latest observation · ${utc(latest)}` : 'No classified observations available'}</p></div><span className="tag">PM2.5 · µg/m³</span></div>
      {loading ? <Loading/> : <div className="network-grid"><div className="map-column"><StationMap stations={stations} selected={selected?.station_id || ''} onSelect={onSelect}/>
        <div className="map-legend">{[['Valid', 'valid'], ['Suspected fault', 'fault'], ['Plume evidence', 'plume'], ['Low confidence', 'low'], ['No classification', 'muted']].map(([text, tone]) => <span key={tone} className={`badge ${tone}`}><i/>{text}</span>)}</div>
      </div><aside className="station-list" aria-label="Station selection"><label className="search-label">Find a station<input type="search" placeholder="Station name or ID" value={search} onChange={e => setSearch(e.target.value)}/></label>
        {!stations.length && <p className="muted">No air-quality stations are available yet. Add observations to populate this view.</p>}
        {!!stations.length && !filtered.length && <p className="muted">No stations match your search.</p>}
        <div className="station-options">{filtered.map(s => <button key={s.station_id} className={`station-option ${selected?.station_id === s.station_id ? 'active' : ''}`} aria-pressed={selected?.station_id === s.station_id} onClick={() => onSelect(s.station_id)}>
          <span className="station-name">{s.name || s.station_id}</span><span className="station-reading">{s.latest ? number(s.latest.value) : '—'} <small>µg/m³</small></span><Badge reading={s.latest}/><small className="station-id">{s.station_id} · {s.cluster_id}</small>
        </button>)}</div>
      </aside></div>}
    </section>
    {selected && <StationDetail key={`${selected.station_id}:${selection.focus || ''}:${revision}`} station={selected} stations={stations} focus={selection.focus} onVerify={onVerify}/>}
    <section className="panel events-panel" aria-labelledby="events-heading"><div className="section-heading"><div><p className="eyebrow">Context matters</p><h2 id="events-heading">Recent events</h2></div>
      <label className="inline-label">Show<select value={eventLabel} onChange={e => setEventLabel(e.target.value)}><option value="">Faults and plumes</option><option value="SENSOR_FAULT_DRIFT">Suspected faults</option><option value="VERIFIED_PLUME_EVENT">Plume evidence</option></select></label></div>
      <p className="caption">A local pollution source can resemble a sensor fault. Plume labels use retrospective neighbor and wind evidence.</p>
      {events.loading && <Loading text="Loading event evidence…"/>}
      {events.error && <Notice title="Event evidence unavailable">{events.error}</Notice>}
      {events.data?.length === 0 && <Notice title="No recorded events">There are no fault or plume records matching this filter.</Notice>}
      <div className="event-grid">{events.data?.map(event => <article className="event-card" key={`${event.station_id}:${event.ts}`}><Badge reading={event}/><h3>{stations.find(s => s.station_id === event.station_id)?.name || event.station_id}</h3>
        <time className="caption">{utc(event.ts)}</time><p>{event.reason}</p><Wind reading={event}/><p className="caption">{event.neighbor_count} usable neighbors · {number(event.value)} µg/m³</p>
        <details><summary>Neighbor evidence</summary>{!event.plume_evidence.length && !event.plume_sources.length && <p>No separate neighbor trace was saved; the recorded count and reason are shown above.</p>}
          {event.plume_evidence.map(e => <p key={`${e.station_id}:${e.ts}`}><strong>{e.station_id}</strong> rose {number(e.rise)} µg/m³ over {number(e.reference)} at {utc(e.ts)}. Lag {e.lag_hours} h; travel estimate {number(e.travel_hours)} h.</p>)}
          {event.plume_sources.map(e => <p key={`${e.station_id}:${e.ts}`}>Linked source: {e.station_id} at {utc(e.ts)}.</p>)}</details>
        <button className="text-button" onClick={() => {setSelection({id: event.station_id, focus: event.ts}); document.querySelector('.station-detail')?.scrollIntoView({block: 'start'});}}>Inspect event readings →</button>
      </article>)}</div>
    </section>
  </>;
}
