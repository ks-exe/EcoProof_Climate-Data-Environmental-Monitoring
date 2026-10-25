import type { Reading, Station } from './types';

export const HOUR = 3_600_000;
export function status(reading: Reading | null) {
  if (!reading) return {text: 'No classification', tone: 'muted', color: '#747d7a'};
  if (reading.low_confidence) return {text: 'Low confidence', tone: 'low', color: '#8b681b'};
  if (reading.label === 'SENSOR_FAULT_DRIFT') return {text: 'Suspected fault', tone: 'fault', color: '#b74f40'};
  if (reading.label === 'VERIFIED_PLUME_EVENT') return {text: 'Plume evidence', tone: 'plume', color: '#2e7088'};
  return {text: 'Valid', tone: 'valid', color: '#287359'};
}

export const number = (value: number | null | undefined, digits = 1) => value == null ? '—' : value.toLocaleString('en', {maximumFractionDigits: digits});
export const utc = (value: string | null) => value ? new Date(value).toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, ' UTC') : 'Not recorded';
export const compact = (value: string, size = 10) => `${value.slice(0, size)}…${value.slice(-6)}`;
export function transactionLink(chain: number | null, hash: string | null): string | null {
  return chain === 11155111 && hash && /^0x[0-9a-fA-F]{64}$/.test(hash) ? `https://sepolia.etherscan.io/tx/${hash}` : null;
}
export const chainName = (chain: number | null) => chain === null ? 'Not anchored' : chain === 11155111 ? 'Sepolia' : chain === 31337 ? 'Local test chain (31337)' : `Chain ${chain}`;

export function distance(a: Station, b: Station): number {
  const radians = Math.PI / 180;
  const x = Math.sin((b.lat - a.lat) * radians / 2) ** 2
    + Math.cos(a.lat * radians) * Math.cos(b.lat * radians) * Math.sin((b.lon - a.lon) * radians / 2) ** 2;
  return 2 * 6371.0088 * Math.asin(Math.sqrt(Math.min(1, Math.max(0, x))));
}
export function nearby(station: Station, stations: Station[]) {
  return stations.filter(s => s.station_id !== station.station_id && s.cluster_id === station.cluster_id)
    .map(s => ({station: s, km: distance(station, s)})).filter(s => s.km <= 20)
    .sort((a, b) => a.km - b.km || a.station.station_id.localeCompare(b.station.station_id));
}
export const windToward = (from: number) => (from + 180) % 360;

/** Disconnected segments preserve nulls and missing hourly samples. */
export function lineSegments(rows: Reading[], field: 'value' | 'expected') {
  const segments: {time: number; value: number}[][] = [];
  let segment: {time: number; value: number}[] = [];
  for (const row of rows) {
    const time = Date.parse(row.ts), value = row[field];
    if (value === null || (segment.length && time - segment.at(-1)!.time > HOUR)) {
      if (segment.length) segments.push(segment);
      segment = [];
    }
    if (value !== null) segment.push({time, value});
  }
  if (segment.length) segments.push(segment);
  return segments;
}

/** Keep the edited JSON text intact; do not parse and reserialize its decimals. */
export function verificationBody(batchId: string, index: number, recordText: string, path: unknown) {
  return `{"batch_id":${JSON.stringify(batchId)},"leaf_index":${index},"record":${recordText},"path":${JSON.stringify(path)}}`;
}
