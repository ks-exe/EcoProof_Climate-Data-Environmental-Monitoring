"""Run bounded, cacheable pulls: python -m ecoproof.ingest --help."""

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
from typing import Any

import httpx

from ecoproof.config import load_settings
from ecoproof.ingest.common import CachedHTTP, IngestionError, Pull, validate_coordinates
from ecoproof.ingest.openaq import OpenAQClient, pm25_sensors
from ecoproof.ingest.openmeteo import fetch_weather


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Cache real OpenAQ/Open-Meteo JSON in Bronze.")
    result.add_argument("--source", choices=("all", "locations", "openaq", "openmeteo"), default="all")
    result.add_argument("--latitude", type=float, required=True)
    result.add_argument("--longitude", type=float, required=True)
    result.add_argument("--region", required=True, help="Local region identifier, e.g. delhi")
    result.add_argument("--radius-m", type=int, default=25000)
    result.add_argument("--start-date", type=date.fromisoformat, help="First UTC date (inclusive)")
    result.add_argument("--end-date", type=date.fromisoformat, help="Last UTC date (inclusive)")
    result.add_argument("--station-limit", type=int, default=10)
    result.add_argument("--refresh", action="store_true", help="Fetch new snapshots; keep existing Bronze files")
    return result


def eligible_locations(
    locations: list[dict[str, Any]], start: datetime, end: datetime,
) -> list[dict[str, Any]]:
    """Catalog time ranges are hints only; actual measurement counts are reported separately."""
    selected = []
    for location in locations:
        if location.get("isMobile") or not pm25_sensors(location):
            continue
        first = (location.get("datetimeFirst") or {}).get("utc")
        last = (location.get("datetimeLast") or {}).get("utc")
        if first and datetime.fromisoformat(first) > end:
            continue
        if last and datetime.fromisoformat(last) < start:
            continue
        selected.append(location)
    return sorted(selected, key=lambda item: (item.get("distance") or 0, item["id"]))


def run(args: argparse.Namespace) -> dict[str, Any]:
    validate_coordinates(args.latitude, args.longitude)
    if not args.region.strip() or args.station_limit <= 0:
        raise ValueError("region must be nonblank and station-limit must be positive")
    if args.source != "locations":
        if args.start_date is None or args.end_date is None:
            raise ValueError("--start-date and --end-date are required for data pulls")
        if args.start_date > args.end_date:
            raise ValueError("start date must not follow end date")
    settings = load_settings()
    pulls: list[Pull] = []
    summary: dict[str, Any] = {"region_id": args.region, "source": args.source}
    with httpx.Client() as client:
        http = CachedHTTP(client, settings.bronze_dir, min_interval=1.05)
        if args.source in ("all", "locations", "openaq"):
            openaq = OpenAQClient(http, settings.openaq_api_key)
            pages = openaq.locations(args.latitude, args.longitude, radius_m=args.radius_m, refresh=args.refresh)
            pulls.extend(pages)
            locations = [item for page in pages for item in page.response["results"]]
            summary["catalog_locations"] = len(locations)
            if args.source == "locations":
                summary["locations"] = [
                    {key: item.get(key) for key in ("id", "name", "distance", "datetimeFirst", "datetimeLast")}
                    | {"pm25_sensor_ids": pm25_sensors(item)} for item in locations
                ]
            else:
                start = datetime.combine(args.start_date, time.min, timezone.utc)
                end = datetime.combine(args.end_date + timedelta(days=1), time.min, timezone.utc)
                eligible = eligible_locations(locations, start, end)
                summary["catalog_locations_overlapping_window"] = len(eligible)
                if not eligible:
                    raise IngestionError("No stationary PM2.5 locations overlap the requested window")
                stations = []
                for location in eligible[:args.station_limit]:
                    count = 0
                    for sensor_id in pm25_sensors(location):
                        pages = openaq.measurements(sensor_id, location["id"], start, end, refresh=args.refresh)
                        pulls.extend(pages)
                        count += sum(len(page.response["results"]) for page in pages)
                    stations.append({"location_id": location["id"], "name": location.get("name"), "raw_readings": count})
                summary["stations"] = stations
                summary["stations_with_readings"] = sum(item["raw_readings"] > 0 for item in stations)
                summary["raw_readings"] = sum(item["raw_readings"] for item in stations)
                if not summary["raw_readings"]:
                    raise IngestionError("OpenAQ returned no readings for the requested stations and dates")
        if args.source in ("all", "openmeteo"):
            pull = fetch_weather(
                http, args.latitude, args.longitude, args.start_date, args.end_date,
                region_id=args.region, refresh=args.refresh,
            )
            pulls.append(pull)
            hourly = pull.response["hourly"]
            summary["weather_hours"] = len(hourly["time"])
            summary["weather_non_null_wind_hours"] = sum(
                speed is not None and direction is not None
                for speed, direction in zip(hourly["wind_speed_10m"], hourly["wind_direction_10m"])
            )
        summary["new_bronze_files"] = sum(not pull.from_cache for pull in pulls)
        summary["cached_responses"] = sum(pull.from_cache for pull in pulls)
        summary["files"] = [str(pull.path) for pull in pulls]
    return summary


def main() -> None:
    args = parser().parse_args()
    try:
        summary = run(args)
    except (IngestionError, ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from None
    print(json.dumps(summary, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
