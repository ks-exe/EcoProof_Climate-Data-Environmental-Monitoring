import { useEffect, useState } from 'react';
import { useResource } from './api';
import { Logo } from './components';
import { Evaluation } from './Evaluation';
import { Monitor } from './Monitor';
import { Verify } from './Verify';
import type { Station } from './types';

export function App() {
  const [location, setLocation] = useState(window.location.hash);
  const [revision, setRevision] = useState(0);
  const network = useResource<Station[]>('/api/stations', revision);
  useEffect(() => {
    const change = () => {setLocation(window.location.hash); window.scrollTo(0, 0);};
    window.addEventListener('hashchange', change); return () => window.removeEventListener('hashchange', change);
  }, []);
  const [route, search = ''] = location.slice(1).split('?');
  const tab = ['monitor', 'verify', 'evaluation'].includes(route) ? route : 'monitor';
  const stations = network.data || [];
  return <><a href="#main" className="skip-link" onClick={event => {event.preventDefault(); document.getElementById('main')?.focus();}}>Skip to content</a>
    <header className="app-header"><a className="brand" href="#monitor" aria-label="EcoProof home"><Logo/><span>Eco<span>Proof</span><small>Air quality, with evidence</small></span></a>
      <nav aria-label="Primary navigation">{[['monitor', 'Monitor'], ['verify', 'Verify'], ['evaluation', 'Evaluation']].map(([key, label]) => <a key={key} href={`#${key}`} aria-current={tab === key ? 'page' : undefined}><span className="nav-symbol" aria-hidden="true">{key === 'monitor' ? '◉' : key === 'verify' ? '◇' : '▥'}</span>{label}</a>)}</nav>
      <span className="header-note">Climate data · Environmental monitoring</span>
    </header>
    <main id="main" tabIndex={-1}>
      {tab === 'monitor' && <Monitor stations={stations} loading={network.loading} error={network.error} revision={revision} refresh={() => setRevision(n => n + 1)}
        onVerify={(station, ts, batch) => {window.location.hash = `verify?${new URLSearchParams({station, ts, ...(batch ? {batch} : {})})}`;}}/>}
      {tab === 'verify' && <Verify key={location} stations={stations} params={new URLSearchParams(search)}/>}
      {tab === 'evaluation' && <Evaluation/>}
    </main>
    <footer><span>EcoProof <span aria-hidden="true">/</span> Climate data with a verifiable record.</span><span>Validation gives context. Provenance preserves the record.</span></footer>
  </>;
}
