export type Label = 'VALID' | 'SENSOR_FAULT_DRIFT' | 'VERIFIED_PLUME_EVENT';
export interface RecordPayload {
  station_id: string; ts: string; value: number; expected: number | null; residual: number | null;
  z: number | null; label: Label; neighbor_count: number; wind_speed: number | null;
  wind_dir_deg: number | null; low_confidence: boolean; reason: string;
}
export interface Reading extends RecordPayload {
  record_hash: string; batch_id: string | null; baseline_sigma: number | null; smoothed_z: number | null;
}
export interface Station {
  station_id: string; name: string | null; lat: number; lon: number; provider: string | null;
  cluster_id: string; latest: Reading | null;
}
export interface Event extends Reading {
  plume_evidence: { station_id: string; ts: string; lag_hours: number; travel_hours: number;
    alignment: number; rise: number; reference: number }[];
  plume_sources: { station_id: string; ts: string }[];
}
export interface Batch {
  batch_id: string; window_start: string; window_end: string; record_count: number; merkle_root: string;
  tx_hash: string | null; chain_id: number | null; anchored_at: string | null; contract_address: string | null;
}
export interface Proof {
  batch: Batch; leaf_index: number; record: RecordPayload; canonical_record: string;
  record_hash: string; path: { sibling_hash: string; side: 'left' | 'right' }[]; root: string;
}
export interface Verification {
  verified: boolean; code: 'verified' | 'unanchored' | 'batch_mismatch' | 'record_mismatch';
  reason: string; batch_id: string; leaf_index: number; record_hash: string; on_chain_root: string | null;
  record_count: number; chain_id: number; contract_address: string; anchored_at: string | null; tx_hash: string | null;
}
export interface Evaluation {
  schema_version: number; status: 'blocked' | 'complete'; reason?: string; chart: string;
  generated_at_utc: string; start_utc: string; end_exclusive_utc: string; region_id?: string;
  input_kind: string; synthetic_interventions: boolean; plume_negative_control_passed: boolean | null;
  metrics: null | {[kind: string]: {case_count: number; methods: {[method: string]: {
    precision: number | null; recall: number | null; f1: number | null; tp: number; fp: number; tn: number; fn: number;
  }}}};
}
