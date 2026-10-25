import type { ReactNode } from 'react';
import { number, status, windToward, transactionLink, chainName } from './domain';
import type { Reading } from './types';

export function Logo() {
  return <span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 32 32"><path d="M7 24C1 10 12 3 27 5c1 14-7 24-20 19Z"/><path d="M6 27 23 10M12 21l-1-8m6 3 7 1"/></svg></span>;
}
export function Badge({reading}: {reading: Reading | null}) {
  const value = status(reading);
  return <span className={`badge ${value.tone}`}><i/>{value.text}</span>;
}
export function Notice({title, children, error = false}: {title: string; children?: ReactNode; error?: boolean}) {
  return <div className={`notice ${error ? 'error' : ''}`} role={error ? 'alert' : 'status'}><strong>{title}</strong>{children && <div>{children}</div>}</div>;
}
export function Loading({text = 'Loading observations…'}: {text?: string}) {
  return <div className="loading" role="status"><span className="spinner"/>{text}</div>;
}
export function Wind({reading}: {reading: Reading | null}) {
  if (!reading || reading.wind_speed === null || reading.wind_dir_deg === null) return <span className="muted">Wind unavailable</span>;
  if (reading.wind_speed === 0) return <span className="wind">Calm · 0 m/s</span>;
  const toward = windToward(reading.wind_dir_deg);
  return <span className="wind" title={`Wind from ${reading.wind_dir_deg}°, toward ${toward}°`}>
    <svg aria-hidden="true" viewBox="0 0 24 24" style={{transform: `rotate(${toward}deg)`}}><path d="M12 21V3m-6 6 6-6 6 6"/></svg>
    {number(reading.wind_speed)} m/s <span className="muted">toward {number(toward, 0)}°</span>
  </span>;
}
export function Transaction({chain, hash}: {chain: number | null; hash: string | null}) {
  const link = transactionLink(chain, hash);
  return <div className="transaction"><span>{chainName(chain)}</span>{hash && (link
    ? <a href={link} target="_blank" rel="noopener noreferrer">View transaction ↗</a>
    : <code>{hash}</code>)}</div>;
}
