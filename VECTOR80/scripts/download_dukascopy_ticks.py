#!/usr/bin/env python3
"""Resumable monthly Dukascopy tick downloader with validation metadata."""

from __future__ import annotations

import argparse
import gzip
import json
import lzma
import struct
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests


BASE_URL = "https://datafeed.dukascopy.com/datafeed"
HEADERS = {"User-Agent": "Mozilla/5.0"}
POINT_FACTOR = {"EURUSD": 100000}
COLUMNS = ["datetime", "bid", "ask", "bid_vol", "ask_vol", "mid"]


def month_starts(start: datetime, end: datetime):
    current = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while current < end:
        next_month = (
            current.replace(year=current.year + 1, month=1)
            if current.month == 12
            else current.replace(month=current.month + 1)
        )
        yield max(current, start), min(next_month, end)
        current = next_month


def hours(start: datetime, end: datetime):
    current = start.replace(minute=0, second=0, microsecond=0)
    while current < end:
        yield current
        current += timedelta(hours=1)


def hour_url(symbol: str, value: datetime) -> str:
    return (
        f"{BASE_URL}/{symbol}/{value.year}/{value.month - 1:02d}/"
        f"{value.day:02d}/{value.hour:02d}h_ticks.bi5"
    )


def expected_market_closed(value: datetime) -> bool:
    # Dukascopy commonly returns 503 rather than 404 for some weekend hours.
    weekday = value.weekday()
    return (
        weekday == 5
        or (weekday == 6 and value.hour < 21)
        or (weekday == 4 and value.hour >= 22)
    )


def parse_ticks(data: bytes, hour: datetime, factor: int) -> list[tuple]:
    raw = lzma.decompress(data)
    if len(raw) % 20:
        raise ValueError(f"invalid decompressed byte count: {len(raw)}")
    rows = []
    for offset in range(0, len(raw), 20):
        ms, ask_raw, bid_raw, ask_vol, bid_vol = struct.unpack(
            ">IIIff", raw[offset : offset + 20]
        )
        timestamp = hour + timedelta(milliseconds=ms)
        bid = bid_raw / factor
        ask = ask_raw / factor
        rows.append((timestamp, bid, ask, bid_vol, ask_vol, (bid + ask) / 2.0))
    return rows


def fetch_hour(
    symbol: str, hour: datetime, factor: int, retries: int
) -> tuple[datetime, str, list[tuple], str | None]:
    url = hour_url(symbol, hour)
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            if response.status_code == 404:
                return hour, "missing", [], None
            response.raise_for_status()
            if not response.content:
                return hour, "empty", [], None
            return hour, "ok", parse_ticks(response.content, hour, factor), None
        except Exception as error:
            if attempt + 1 == retries:
                if expected_market_closed(hour):
                    return hour, "missing", [], None
                return hour, "error", [], str(error)
            time.sleep(1.0 + attempt)
    raise AssertionError("unreachable")


def validate_month(frame: pd.DataFrame, start: datetime, end: datetime) -> dict:
    duplicate_count = int(frame["datetime"].duplicated().sum())
    invalid_quote = int((frame["ask"] < frame["bid"]).sum())
    outside = int(((frame["datetime"] < start) | (frame["datetime"] >= end)).sum())
    return {
        "rows": int(len(frame)),
        "start": frame["datetime"].min().isoformat() if len(frame) else None,
        "end": frame["datetime"].max().isoformat() if len(frame) else None,
        "duplicate_timestamps": duplicate_count,
        "ask_below_bid": invalid_quote,
        "outside_requested_period": outside,
        "min_bid": float(frame["bid"].min()) if len(frame) else None,
        "max_ask": float(frame["ask"].max()) if len(frame) else None,
    }


def download_month(
    symbol: str,
    start: datetime,
    end: datetime,
    output: Path,
    workers: int,
    retries: int,
) -> dict:
    factor = POINT_FACTOR[symbol]
    requested_hours = list(hours(start, end))
    rows = []
    statuses = []
    errors = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_hour, symbol, hour, factor, retries): hour
            for hour in requested_hours
        }
        completed = 0
        for future in as_completed(futures):
            hour, status, hour_rows, error = future.result()
            statuses.append((hour, status))
            rows.extend(hour_rows)
            if error:
                errors[hour.isoformat()] = error
            completed += 1
            if completed % 100 == 0 or completed == len(requested_hours):
                print(
                    f"\r  {start:%Y-%m}: {completed}/{len(requested_hours)} hours, "
                    f"{len(rows):,} ticks",
                    end="",
                    flush=True,
                )
    print()

    frame = pd.DataFrame(rows, columns=COLUMNS)
    if len(frame):
        frame["datetime"] = pd.to_datetime(frame["datetime"], utc=True)
        frame = (
            frame.sort_values("datetime")
            .drop_duplicates(["datetime", "bid", "ask", "bid_vol", "ask_vol"])
            .reset_index(drop=True)
        )
        frame = frame[(frame["datetime"] >= start) & (frame["datetime"] < end)]
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(
        output,
        index=False,
        compression="gzip",
        float_format="%.5f",
        date_format="%Y-%m-%dT%H:%M:%S.%f%z",
    )
    status_counts = pd.Series([status for _, status in statuses]).value_counts()
    metadata = {
        "symbol": symbol,
        "requested_start": start.isoformat(),
        "requested_end_exclusive": end.isoformat(),
        "requested_hours": len(requested_hours),
        "hour_status": {str(k): int(v) for k, v in status_counts.items()},
        "error_hours": errors,
        "file": str(output),
        **validate_month(frame, start, end),
    }
    output.with_suffix(output.suffix + ".metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


def existing_valid(path: Path, start: datetime, end: datetime) -> bool:
    metadata_path = path.with_suffix(path.suffix + ".metadata.json")
    if not path.exists() or not metadata_path.exists():
        return False
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return (
        metadata.get("requested_start") == start.isoformat()
        and metadata.get("requested_end_exclusive") == end.isoformat()
        and not metadata.get("error_hours")
        and metadata.get("duplicate_timestamps") == 0
        and metadata.get("ask_below_bid") == 0
        and metadata.get("outside_requested_period") == 0
    )


def consolidate_year(
    symbol: str, year: int, parts: list[Path], output_dir: Path
) -> tuple[Path, dict]:
    output = output_dir / f"{symbol}_TICK_dukascopy_{year}.csv.gz"
    rows = 0
    first_timestamp = None
    last_timestamp = None
    last_line = None
    duplicates = 0
    with gzip.open(output, "wt", encoding="utf-8", newline="") as destination:
        destination.write(",".join(COLUMNS) + "\n")
        for part in sorted(parts):
            with gzip.open(part, "rt", encoding="utf-8") as source:
                next(source, None)
                for line in source:
                    if line == last_line:
                        duplicates += 1
                        continue
                    timestamp = line.split(",", 1)[0]
                    if first_timestamp is None:
                        first_timestamp = timestamp
                    last_timestamp = timestamp
                    destination.write(line)
                    last_line = line
                    rows += 1
    metadata = {
        "symbol": symbol,
        "year": year,
        "file": str(output),
        "parts": [str(part) for part in sorted(parts)],
        "rows": rows,
        "start": first_timestamp,
        "end": last_timestamp,
        "adjacent_duplicate_rows_removed": duplicates,
    }
    output.with_suffix(output.suffix + ".metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return output, metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("start", help="inclusive UTC date")
    parser.add_argument("end", help="exclusive UTC date")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    symbol = args.symbol.upper().replace("/", "")
    if symbol not in POINT_FACTOR:
        raise SystemExit(f"unsupported symbol: {symbol}")
    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if end <= start:
        raise SystemExit("end must be later than start")

    parts_dir = args.output_dir / ".parts"
    summaries = []
    parts_by_year: dict[int, list[Path]] = {}
    for month_start, month_end in month_starts(start, end):
        output = parts_dir / (
            f"{symbol}_TICK_{month_start:%Y%m%d}_{month_end:%Y%m%d}_exclusive.csv.gz"
        )
        parts_by_year.setdefault(month_start.year, []).append(output)
        if not args.force and existing_valid(output, month_start, month_end):
            print(f"skip validated: {output.name}")
            summaries.append(
                json.loads(
                    output.with_suffix(output.suffix + ".metadata.json").read_text()
                )
            )
            continue
        print(f"download: {month_start.date()} -> {month_end.date()} exclusive")
        summaries.append(
            download_month(
                symbol,
                month_start,
                month_end,
                output,
                args.workers,
                args.retries,
            )
        )

    years = []
    for year, parts in sorted(parts_by_year.items()):
        year_output, year_metadata = consolidate_year(
            symbol, year, parts, args.output_dir
        )
        years.append(year_metadata)
        print(f"year file: {year_output} ({year_metadata['rows']:,} rows)")

    manifest = {
        "symbol": symbol,
        "requested_start": start.isoformat(),
        "requested_end_exclusive": end.isoformat(),
        "months": summaries,
        "years": years,
        "rows": int(sum(month["rows"] for month in summaries)),
        "error_hours": int(sum(len(month["error_hours"]) for month in summaries)),
    }
    manifest_path = args.output_dir / (
        f"{symbol}_TICK_{start:%Y%m%d}_{end:%Y%m%d}_exclusive.manifest.json"
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("manifest:", manifest_path)
    print("rows:", f"{manifest['rows']:,}")
    print("error hours:", manifest["error_hours"])


if __name__ == "__main__":
    main()
