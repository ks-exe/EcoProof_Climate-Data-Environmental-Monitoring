import { describe, expect, it } from 'vitest';
import { distance, HOUR, lineSegments, nearby, status, transactionLink, verificationBody, windToward } from './domain';
import { ratio, validReport } from './Evaluation';
import type { Evaluation, Reading, Station } from './types';

const reading = {station_id: 's', ts: '2026-10-21T00:00:00Z', value: 12.5, expected: 12,
  low_confidence: false, label: 'VALID'} as Reading;
const station = {station_id: 's', lat: 0, lon: 0, cluster_id: 'test', latest: reading} as Station;

describe('honest classification and geographic context', () => {
  it('keeps absent and low-confidence classifications distinct from valid', () => {
    expect(status(null).text).toBe('No classification');
    expect(status({...reading, low_confidence: true}).text).toBe('Low confidence');
    expect(status({...reading, label: 'SENSOR_FAULT_DRIFT'}).text).toBe('Suspected fault');
  });
  it('uses the meteorological FROM direction to draw travel arrows', () => {
    expect(windToward(0)).toBe(180); expect(windToward(270)).toBe(90);
  });
  it('limits nearby context by distance and cluster, excluding self', () => {
    const close = {...station, station_id: 'near', lon: .05};
    const far = {...station, station_id: 'far', lon: 1};
    expect(distance(station, far)).toBeCloseTo(111.195, 2);
    expect(nearby(station, [station, far, close, {...close, station_id: 'other', cluster_id: 'other'}]).map(s => s.station.station_id)).toEqual(['near']);
  });
  it('keeps gaps and unavailable expected values out of line segments', () => {
    const make = (hour: number, expected: number | null = 12) => ({...reading, ts: new Date(Date.parse(reading.ts) + hour * HOUR).toISOString(), expected});
    const rows = [make(0), make(1, null), make(2), make(5), make(6)];
    expect(lineSegments(rows, 'value').map(s => s.length)).toEqual([3, 2]);
    expect(lineSegments(rows, 'expected').map(s => s.length)).toEqual([1, 1, 2]);
  });
});

describe('verification transport', () => {
  it('never converts exact edited decimals through JavaScript floats', () => {
    const text = '{"value":12.500050000000000000001,"reason":"a,b"}';
    const body = verificationBody('batch"x', 2, text, []);
    expect(body).toContain(text);
    expect(JSON.parse(body).batch_id).toBe('batch"x');
  });
  it('does not silently remove duplicate uploaded keys before the server can reject them', () => {
    expect(verificationBody('id', 0, '{"value":1,"value":2}', [])).toContain('"value":1,"value":2');
  });
  it('only constructs explorer links for a real-shaped Sepolia transaction hash', () => {
    const hash = `0x${'a'.repeat(64)}`;
    expect(transactionLink(11155111, hash)).toBe(`https://sepolia.etherscan.io/tx/${hash}`);
    expect(transactionLink(31337, hash)).toBeNull();
    expect(transactionLink(null, hash)).toBeNull();
    expect(transactionLink(11155111, 'javascript:alert(1)')).toBeNull();
  });
});

describe('evaluation display boundaries (schema inputs, not measured results)', () => {
  const report = {schema_version: 1, status: 'blocked', chart: `eval-${'a'.repeat(32)}.png`,
    input_kind: 'synthetic_fixture', synthetic_interventions: true, metrics: null,
    generated_at_utc: reading.ts, start_utc: reading.ts, end_exclusive_utc: '2026-10-22T00:00:00Z'} as Evaluation;
  it('preserves undefined metrics and formats zero as an actual value', () => {
    expect(ratio(null)).toBe('Undefined'); expect(ratio(0)).toBe('0.0%');
  });
  it('accepts a blocked report without fabricating a metrics table', () => expect(validReport(report)).toBe(true));
  it('rejects a complete status without metrics and unsafe chart references', () => {
    expect(validReport({...report, status: 'complete'})).toBe(false);
    expect(validReport({...report, chart: '../.env'})).toBe(false);
    expect(validReport({...report, generated_at_utc: 'unknown'})).toBe(false);
  });
  it('rejects malformed method objects without throwing', () => {
    expect(validReport({...report, status: 'complete', metrics: {spike: {case_count: 1, methods: null}}} as unknown as Evaluation)).toBe(false);
  });
});
