import { useEffect, useRef, useState } from 'react';
import { query, requestJSON, useResource } from './api';
import { Loading, Notice, Transaction } from './components';
import { compact, utc, verificationBody } from './domain';
import type { Batch, Proof, Station, Verification } from './types';

export function Verify({stations, params}: {stations: Station[]; params: URLSearchParams}) {
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const batches = useResource<Batch[]>(`/api/batches?limit=10&offset=${offset}`, revision);
  const [selection, setSelection] = useState({station: params.get('station') || '', ts: params.get('ts') || '', batch: params.get('batch') || ''});
  const [proof, setProof] = useState<Proof | null>(null);
  const [record, setRecord] = useState('');
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');
  const [verifyError, setVerifyError] = useState('');
  const [result, setResult] = useState<Verification | null>(null);
  const pending = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const autoLoaded = useRef(false);
  useEffect(() => () => {pending.current?.abort(); generation.current++;}, []);

  function clearCheck() {
    pending.current?.abort(); generation.current++;
    setResult(null); setVerifyError(''); setChecking(false);
  }
  function updateSelection(next: typeof selection) {
    clearCheck(); setSelection(next); setProof(null); setRecord(''); setError(''); setLoading(false);
  }
  function edit(value: string) {clearCheck(); setRecord(value);}
  async function loadProof(values = selection) {
    clearCheck(); setProof(null); setRecord(''); setError(''); setLoading(true);
    const controller = new AbortController(); pending.current = controller;
    try {
      const data = await requestJSON<Proof>(query('proof', {station: values.station, ts: values.ts, ...(values.batch ? {batch_id: values.batch} : {})}), {signal: controller.signal});
      if (!controller.signal.aborted) {setProof(data); setRecord(data.canonical_record);}
    } catch (e) {if (!controller.signal.aborted) setError((e as Error).message);}
    finally {if (!controller.signal.aborted) setLoading(false);}
  }
  useEffect(() => {
    if (!autoLoaded.current && selection.station && selection.ts) {
      autoLoaded.current = true; void loadProof(selection);
    }
  }, []);

  async function verify() {
    if (!proof) return;
    clearCheck(); setChecking(true);
    const controller = new AbortController(); pending.current = controller;
    try {
      const answer = await requestJSON<Verification>('/api/verify', {method: 'POST', signal: controller.signal,
        headers: {'Content-Type': 'application/json'}, body: verificationBody(proof.batch.batch_id, proof.leaf_index, record, proof.path)});
      if (!controller.signal.aborted) setResult(answer);
    } catch (e) {if (!controller.signal.aborted) setVerifyError((e as Error).message);}
    finally {if (!controller.signal.aborted) setChecking(false);}
  }
  return <>
    <div className="page-heading"><div><p className="eyebrow">An auditable record</p><h1>Verify what was recorded.</h1><p>Trace a reading from its canonical payload to the registry root.</p></div><span className="tag">SHA-256 · Merkle proofs</span></div>
    <div className="verify-layout"><aside className="panel batch-panel"><div className="section-heading"><h2>Saved batches</h2><button className="text-button" onClick={() => setRevision(n => n + 1)}>Refresh batches</button></div>
      <p className="caption">Saved metadata. Verification reads the chain again.</p>
      {batches.loading && <Loading text="Loading batches…"/>}
      {batches.error && <Notice title="Batches unavailable">{batches.error}</Notice>}
      {batches.data?.length === 0 && <Notice title="No batches on this page">Confident VALID observations must be prepared before they have a proof.</Notice>}
      <div className="batch-list">{batches.data?.map(batch => <div className={`batch-card ${selection.batch === batch.batch_id ? 'selected' : ''}`} key={batch.batch_id}>
        <button className="batch-select" onClick={() => updateSelection({station: selection.station || stations[0]?.station_id || '', ts: batch.window_start, batch: batch.batch_id})} aria-pressed={selection.batch === batch.batch_id}>
          <span className="mono">{utc(batch.window_start)}</span><strong>{batch.record_count} {batch.record_count === 1 ? 'record' : 'records'} <span className="tag">{batch.tx_hash ? 'Mined' : 'Saved only'}</span></strong><code>{compact(batch.merkle_root)}</code>
        </button><Transaction chain={batch.chain_id} hash={batch.tx_hash}/>
      </div>)}</div>
      <div className="pagination"><button className="button secondary" disabled={offset === 0 || batches.loading} onClick={() => setOffset(n => Math.max(0, n - 10))}>Previous</button>
        <span className="caption">Page {offset / 10 + 1}</span><button className="button secondary" disabled={batches.loading || !batches.data || batches.data.length < 10} onClick={() => setOffset(n => n + 10)}>Next</button></div>
    </aside><div className="proof-column">
      <section className="panel"><div className="section-heading"><div><p className="eyebrow">01 / Select</p><h2>Find a record</h2></div></div>
        <form className="proof-form" onSubmit={e => {e.preventDefault(); void loadProof();}}>
          <label>Station ID<input required list="station-ids" value={selection.station} onChange={e => updateSelection({...selection, station: e.target.value})} placeholder="Choose or enter a station ID"/></label>
          <datalist id="station-ids">{stations.map(s => <option key={s.station_id} value={s.station_id}>{s.name || s.station_id}</option>)}</datalist>
          <label>Observation timestamp (UTC or offset)<input required value={selection.ts} onChange={e => updateSelection({...selection, ts: e.target.value})} placeholder="YYYY-MM-DDTHH:MM:SSZ"/></label>
          <label className="wide">Batch ID <span className="muted">· optional for current records</span><input value={selection.batch} onChange={e => updateSelection({...selection, batch: e.target.value})} placeholder="Choose a saved batch, or leave blank" className="mono"/></label>
          <div className="wide"><button className="button" type="submit" disabled={loading}>{loading ? 'Loading proof…' : 'Load proof'}</button></div>
        </form>
        <p className="caption">An explicit batch ID retrieves its retained snapshot, even after the current data has changed.</p>
        {error && <Notice title="Proof unavailable" error>{error}</Notice>}
      </section>
      {!proof && !loading && !error && <div className="proof-placeholder"><span aria-hidden="true">◇</span><h2>Every proof starts with a record.</h2><p>Select a reading on Monitor, or choose a batch and enter a station and timestamp.</p></div>}
      {proof && <>
        <section className="panel"><div className="section-heading"><div><p className="eyebrow">02 / Inspect</p><h2>Record & inclusion path</h2></div><span className="tag">Leaf {proof.leaf_index + 1} / {proof.batch.record_count}</span></div>
          <dl className="hash-details"><div><dt>Leaf hash</dt><dd><code>{proof.record_hash}</code></dd></div><div><dt>Saved Merkle root</dt><dd><code>{proof.root}</code></dd></div></dl>
          <details className="merkle-path" open><summary>Merkle path · {proof.path.length} {proof.path.length === 1 ? 'sibling' : 'siblings'}</summary>
            {proof.path.length ? <ol>{proof.path.map((step, i) => <li key={i}><span className="path-side">{step.side === 'left' ? '← Left' : 'Right →'}</span><code>{step.sibling_hash}</code></li>)}</ol>
              : <p>Single-record batch: the leaf hash is the root. No sibling hashes are needed.</p>}
          </details>
          <details><summary>Exact saved canonical JSON</summary><pre>{proof.canonical_record}</pre></details>
        </section>
        <section className="panel"><div className="section-heading"><div><p className="eyebrow">03 / Verify</p><h2>Check against the chain</h2></div></div>
          <p>Edit a value to test the proof, or upload a replacement record. Numbers are committed at four decimal places.</p>
          <label className="record-editor">Record JSON<textarea value={record} onChange={e => edit(e.target.value)} spellCheck={false} rows={10}/></label>
          <div className="editor-actions"><button className="text-button" onClick={() => edit(proof.canonical_record)}>Restore saved record</button><label className="file-label">Upload JSON<input type="file" accept=".json,application/json" onChange={async e => {
            const file = e.target.files?.[0]; e.target.value = ''; if (!file) return;
            clearCheck(); const token = generation.current;
            if (file.size > 65536) {setVerifyError('Choose a JSON file smaller than 64 KiB.'); return;}
            try {const text = await file.text(); if (generation.current === token) setRecord(text);}
            catch {if (generation.current === token) setVerifyError('The selected file could not be read.');}
          }}/></label></div>
          <button className="button verify-button" disabled={checking || !record.trim()} onClick={() => void verify()}>{checking ? 'Reading the registry…' : 'Verify record'}</button>
          {verifyError && <Notice title="Verification unavailable" error>{verifyError}<p>No verification verdict was returned.</p></Notice>}
          {result && <div className={`verification-result ${result.verified ? 'success' : result.code === 'unanchored' ? 'unanchored' : 'failure'}`} role="status">
            <h3>{result.verified ? '✓ Record verified' : result.code === 'unanchored' ? 'Batch is not anchored' : 'Record verification failed'}</h3><p>{result.reason}</p>
            <Transaction chain={result.chain_id} hash={result.tx_hash}/><dl className="hash-details"><div><dt>Uploaded record hash</dt><dd><code>{result.record_hash}</code></dd></div>
              <div><dt>Registry root</dt><dd><code>{result.on_chain_root || 'No anchor'}</code></dd></div><div><dt>Anchor time</dt><dd>{utc(result.anchored_at)}</dd></div></dl>
          </div>}
          <p className="integrity-note">A matching proof establishes that the canonical record was included at anchoring time. It does not establish that the sensor was correct.</p>
        </section>
      </>}
    </div></div>
  </>;
}
