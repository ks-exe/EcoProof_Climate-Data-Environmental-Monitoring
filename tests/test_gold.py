"""Synthetic Silver -> classifier -> real Parquet and DuckDB integration checks."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

import duckdb
import pytest

from ecoproof.config import Settings
from ecoproof.detect.__main__ import main
from ecoproof.detect.classifier import DetectorConfig
from ecoproof.transform.gold import build_classifications, hourly_readings, publish_classifications
from ecoproof.transform.silver import create_tables, publish_views
from ecoproof.transform.validation import PM25_UNIT


START = datetime(2026, 10, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


@pytest.fixture
def silver(tmp_path: Path) -> Callable[..., Settings]:
    def create(*, plume: bool = False, no_weather: bool = False, no_stations: bool = False) -> Settings:
        settings = Settings(tmp_path / "data's directory")
        build = settings.silver_dir / 'synthetic-source'
        build.mkdir(parents=True)
        with duckdb.connect() as db:
            create_tables(db)
            if not no_stations:
                db.executemany('INSERT INTO stations VALUES (?,?,?,?,?,?)',
                               [(station, 'Synthetic', 0, longitude, 'Test only', 'test')
                                for station, longitude in [('a', 0), ('b', .05), ('c', -.05)]])
                rows = []
                for station in ('a', 'b', 'c'):
                    for hour in range(40):
                        value = 60 if station == 'a' and hour == 24 else 20
                        if plume and station == 'b' and hour == 25:
                            value = 35
                        rows.append((station, (START + hour * HOUR).replace(tzinfo=None), 'pm25', value, PM25_UNIT))
                # This nearby station belongs to a different region and must not leak into the graph.
                db.execute("INSERT INTO stations VALUES ('other','Synthetic',0,0,'Test only','elsewhere')")
                rows.append(('other', (START + 24 * HOUR).replace(tzinfo=None), 'pm25', 1000, PM25_UNIT))
                db.executemany('INSERT INTO readings VALUES (?,?,?,?,?)', rows)
            if not no_weather:
                db.executemany('INSERT INTO weather VALUES (?,?,?,?,?,?)',
                               [('test', (START + hour * HOUR).replace(tzinfo=None), 2, 270, 20, 1000)
                                for hour in range(40)])
            for table in ('stations', 'readings', 'weather'):
                db.sql(f'SELECT * FROM {table}').write_parquet(str(build / f'{table}.parquet'))
        publish_views(settings.duckdb_path, build)
        return settings
    return create


def build(settings: Settings, *, start: int = 24, end: int = 37) -> dict:
    return build_classifications(settings, region_id='test', baseline_start=START,
                                 baseline_end=START + 24 * HOUR, start=START + start * HOUR,
                                 end=START + end * HOUR, config=DetectorConfig(sigma_km=10, alpha=.5))


def query(settings: Settings, sql: str) -> list:
    with duckdb.connect(str(settings.duckdb_path), read_only=True) as db:
        return db.execute(sql).fetchall()


def test_end_to_end_output_confidence_region_isolation_and_rebuild(silver: Callable) -> None:
    settings = silver()
    source_files = list(settings.silver_dir.rglob('*.parquet'))
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files}
    report = build(settings)
    assert report['classified_records'] == 39
    assert report['raw_readings_with_context'] == 120
    assert report['baselines']['a']['sample_count'] == 24
    assert report['baselines']['a']['sigma'] == 1
    assert len(report['station_coverage']) == 3
    assert report['low_confidence_records'] > 0
    assert query(settings, 'SELECT count(*), count(record_hash), count(batch_id) FROM gold.classified') == [(39, 39, 0)]
    assert query(settings, "SELECT count(*) FROM gold.classified WHERE station_id = 'other'") == [(0,)]
    joined = query(settings, """
        SELECT c.station_id, c.ts, c.label, e.low_confidence, e.reason
        FROM gold.classified c JOIN gold.classification_evidence e USING (station_id,ts)
        WHERE c.station_id = 'a' AND c.ts = TIMESTAMP '2026-10-02 00:00:00'
    """)
    assert joined == [('a', datetime(2026, 10, 2), 'SENSOR_FAULT_DRIFT', False, 'suspected_isolated_anomaly')]
    rows = query(settings, 'SELECT * FROM gold.classified ORDER BY station_id,ts')
    evidence = query(settings, 'SELECT * FROM gold.classification_evidence ORDER BY station_id,ts')
    original = Path(report['build_dir'])
    assert json.loads((original / 'build_report.json').read_text()) == report
    again = build(settings)
    assert original != Path(again['build_dir']) and original.is_dir()
    assert query(settings, 'SELECT * FROM gold.classified ORDER BY station_id,ts') == rows
    assert query(settings, 'SELECT * FROM gold.classification_evidence ORDER BY station_id,ts') == evidence
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files} == before


def test_saved_plume_evidence_contains_real_computed_values(silver: Callable) -> None:
    settings = silver(plume=True)
    report = build(settings)
    assert report['labels'].get('SENSOR_FAULT_DRIFT', 0) == 0
    payload = query(settings, """
        SELECT e.plume_evidence_json FROM gold.classification_evidence e
        JOIN gold.classified c USING (station_id,ts) WHERE c.label = 'VERIFIED_PLUME_EVENT'
    """)[0][0]
    evidence = json.loads(payload)[0]
    assert evidence['station_id'] == 'b'
    assert evidence['ts'] == '2026-10-02T01:00:00Z'
    assert evidence['rise'] == 15 and evidence['lag_hours'] == 1
    sources = query(settings, """
        SELECT plume_sources_json FROM gold.classification_evidence
        WHERE station_id = 'b' AND ts = TIMESTAMP '2026-10-02 01:00:00'
    """)[0][0]
    assert json.loads(sources) == [{'station_id': 'a', 'ts': '2026-10-02T00:00:00Z'}]


def test_missing_weather_persists_nulls_and_low_confidence(silver: Callable) -> None:
    settings = silver(no_weather=True)
    report = build(settings)
    assert report['low_confidence_records'] == 39
    assert report['labels'] == {'VALID': 39}
    assert query(settings, 'SELECT count(expected), count(z), count(wind_speed) FROM gold.classified') == [(0, 0, 0)]
    assert query(settings, 'SELECT DISTINCT reason FROM gold.classification_evidence') == [('missing_weather',)]


def test_no_stations_or_output_readings_does_not_create_gold(silver: Callable) -> None:
    settings = silver(no_stations=True)
    with pytest.raises(ValueError, match='No Silver stations'):
        build(settings)
    assert not settings.gold_dir.exists()


def test_empty_window_preserves_previously_published_gold(silver: Callable) -> None:
    settings = silver()
    build(settings)
    before = query(settings, 'SELECT * FROM gold.classified ORDER BY station_id,ts')
    folders = list(settings.gold_dir.iterdir())
    with pytest.raises(ValueError, match='No Silver PM2.5 readings'):
        build(settings, start=100, end=110)
    assert list(settings.gold_dir.iterdir()) == folders
    assert query(settings, 'SELECT * FROM gold.classified ORDER BY station_id,ts') == before


def test_view_switch_rolls_back_both_views_and_preserves_batches(silver: Callable, tmp_path: Path) -> None:
    settings = silver()
    report = build(settings)
    with duckdb.connect(str(settings.duckdb_path)) as db:
        db.execute("""INSERT INTO gold.batches VALUES ('test-only-existing-batch',
                   TIMESTAMP '2026-10-01 00:00:00', TIMESTAMP '2026-10-01 01:00:00',
                   1, 'synthetic-placeholder', NULL, NULL, NULL)""")
    before = query(settings, 'SELECT * FROM gold.classified ORDER BY station_id,ts')
    incomplete = tmp_path / 'incomplete'
    incomplete.mkdir()
    shutil.copy2(Path(report['build_dir']) / 'classified.parquet', incomplete / 'classified.parquet')
    with pytest.raises(duckdb.Error):
        publish_classifications(settings.duckdb_path, incomplete)
    assert query(settings, 'SELECT * FROM gold.classified ORDER BY station_id,ts') == before
    assert query(settings, 'SELECT count(*) FROM gold.classification_evidence') == [(39,)]
    assert query(settings, 'SELECT batch_id FROM gold.batches') == [('test-only-existing-batch',)]


def test_hourly_ending_bins_mean_samples_and_do_not_fill_gaps() -> None:
    rows = [('a', datetime(2026, 10, 1, 10), 10, PM25_UNIT),
            ('a', datetime(2026, 10, 1, 10, 5), 20, PM25_UNIT),
            ('a', datetime(2026, 10, 1, 10, 55), 30, PM25_UNIT),
            ('a', datetime(2026, 10, 1, 12), 0, PM25_UNIT)]
    assert hourly_readings(rows) == {
        ('a', START + 10 * HOUR): 10, ('a', START + 11 * HOUR): 25, ('a', START + 12 * HOUR): 0,
    }


@pytest.mark.parametrize('bad', [-1, 1501, float('nan'), True])
def test_invalid_samples_cannot_be_hidden_by_hourly_averaging(bad) -> None:
    with pytest.raises(ValueError):
        hourly_readings([('a', datetime(2026, 10, 1, 10, 5), bad, PM25_UNIT),
                         ('a', datetime(2026, 10, 1, 10, 30), 20, PM25_UNIT)])


def test_cli_runs_real_pipeline_on_synthetic_silver(silver: Callable, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    settings = silver()
    monkeypatch.setenv('ECOPROOF_DATA_DIR', str(settings.data_dir))
    monkeypatch.setattr(sys, 'argv', ['detect', '--region', 'test', '--sigma-km', '10', '--alpha', '.5',
                                    '--baseline-start', '2026-10-01T00:00:00Z',
                                    '--baseline-end', '2026-10-02T00:00:00Z',
                                    '--start', '2026-10-02T00:00:00Z', '--end', '2026-10-02T13:00:00Z'])
    main()
    output = json.loads(capsys.readouterr().out)
    assert output['classified_records'] == 39
    assert Path(output['report']).is_file()


def test_one_command_rebuilds_from_synthetic_bronze(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    settings = Settings(tmp_path / 'bronze-to-gold')
    settings.bronze_dir.mkdir(parents=True)
    times = [START + hour * HOUR for hour in range(40)]
    records = [{'id': node, 'isMobile': False,
                'coordinates': {'latitude': 0, 'longitude': node * .05},
                'sensors': [{'id': node * 10, 'parameter': {'id': 2, 'name': 'pm25'}}]}
               for node in (1, 2, 3)]
    envelopes = [('openaq', '/v3/locations', {'coordinates': '0.0000,0.0500', 'radius': 25000}, {}, {'results': records})]
    for node in (1, 2, 3):
        results = [{'value': 20, 'parameter': {'id': 2, 'name': 'pm25', 'units': PM25_UNIT},
                    'period': {'datetimeTo': {'utc': ts.isoformat()}}} for ts in times]
        envelopes.append(('openaq', f'/v3/sensors/{node * 10}/measurements', {},
                          {'location_id': node, 'sensor_id': node * 10}, {'results': results}))
    weather = {'utc_offset_seconds': 0,
               'hourly_units': {'time': 'iso8601', 'wind_speed_10m': 'm/s', 'wind_direction_10m': '°',
                                'temperature_2m': '°C', 'surface_pressure': 'hPa'},
               'hourly': {'time': [ts.replace(tzinfo=None).isoformat() for ts in times],
                          'wind_speed_10m': [2] * 40, 'wind_direction_10m': [270] * 40,
                          'temperature_2m': [20] * 40, 'surface_pressure': [1000] * 40}}
    envelopes.append(('openmeteo', '/v1/archive', {'latitude': 0, 'longitude': .05}, {'region_id': 'test'}, weather))
    for index, (source, path, params, context, response) in enumerate(envelopes):
        host = 'https://api.openaq.org' if source == 'openaq' else 'https://archive-api.open-meteo.com'
        doc = {'schema_version': 1, 'source': source, 'fetched_at': '2026-10-19T00:00:00Z',
               'request': {'url': host + path, 'params': params, 'context': context}, 'response': response}
        (settings.bronze_dir / f'{source}_{index}.json').write_text(json.dumps(doc), encoding='utf-8')
    before = {path: path.read_bytes() for path in settings.bronze_dir.iterdir()}
    monkeypatch.setenv('ECOPROOF_DATA_DIR', str(settings.data_dir))
    monkeypatch.setattr(sys, 'argv', ['detect', '--rebuild-silver', '--region', 'test', '--sigma-km', '10', '--alpha', '.5',
                                    '--baseline-start', '2026-10-01T00:00:00Z', '--baseline-end', '2026-10-02T00:00:00Z',
                                    '--start', '2026-10-02T00:00:00Z', '--end', '2026-10-02T13:00:00Z'])
    main()
    report = json.loads(capsys.readouterr().out)
    assert report['classified_records'] == 39
    assert query(settings, 'SELECT count(*) FROM silver.readings') == [(120,)]
    assert query(settings, 'SELECT count(*) FROM gold.classified') == [(39,)]
    assert {path: path.read_bytes() for path in settings.bronze_dir.iterdir()} == before
