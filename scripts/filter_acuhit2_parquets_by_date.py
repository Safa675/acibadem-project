#!/usr/bin/env python3
"""
Filter ACUHIT 2 parquet files by a minimum date.

Reads:
  .cache/acuhit2_lab_from2021.parquet (date)
  .cache/acuhit2_anadata_from2021.parquet (visit_date)
  .cache/acuhit2_recete_from2021.parquet (date)

Writes (for --min-date 2025-01-01):
  .cache/acuhit2_lab_from2025.parquet
  .cache/acuhit2_anadata_from2025.parquet
  .cache/acuhit2_recete_from2025.parquet

Usage:
  python scripts/filter_acuhit2_parquets_by_date.py --min-date 2025-01-01 --overwrite
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq


@dataclass(frozen=True)
class FileSpec:
    """Parquet file filter specification."""

    key: str
    source_name: str
    date_column: str


@dataclass
class FilterSummary:
    """Summary stats for one filtered parquet file."""

    key: str
    source_path: Path
    output_path: Path
    input_rows: int
    output_rows: int
    dropped_rows: int
    min_kept_date: pd.Timestamp | None
    max_kept_date: pd.Timestamp | None


FILE_SPECS = [
    FileSpec(
        key="lab",
        source_name="acuhit2_lab_from2021.parquet",
        date_column="date",
    ),
    FileSpec(
        key="anadata",
        source_name="acuhit2_anadata_from2021.parquet",
        date_column="visit_date",
    ),
    FileSpec(
        key="recete",
        source_name="acuhit2_recete_from2021.parquet",
        date_column="date",
    ),
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create filtered ACUHIT parquet files from a minimum date."
    )
    parser.add_argument(
        "--min-date",
        default="2025-01-01",
        help="Inclusive minimum date to keep (YYYY-MM-DD). Default: 2025-01-01",
    )
    parser.add_argument(
        "--cache-dir",
        default=".cache",
        help="Directory containing input/output parquet files. Default: .cache",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output files if they already exist.",
    )
    return parser.parse_args()


def _parse_min_date(value: str) -> pd.Timestamp:
    min_date = pd.to_datetime(value, errors="raise")
    return pd.Timestamp(min_date).tz_localize(None)


def _format_ts(ts: pd.Timestamp | None) -> str:
    if ts is None or pd.isna(ts):
        return "N/A"
    return pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _cutoff_scalar(min_date: pd.Timestamp, field_type: pa.DataType) -> pa.Scalar:
    """Build a typed scalar matching the parquet date column type."""
    if pa.types.is_timestamp(field_type):
        return pa.scalar(min_date.to_datetime64(), type=field_type)

    if pa.types.is_date32(field_type) or pa.types.is_date64(field_type):
        return pa.scalar(min_date.date(), type=field_type)

    raise TypeError(
        f"Unsupported date column type {field_type}; expected timestamp/date type"
    )


def _update_min_max(
    current_min: pd.Timestamp | None,
    current_max: pd.Timestamp | None,
    batch_values: pa.Array,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Update running min/max timestamps from one record batch column."""
    batch_min = pc.min(batch_values).as_py()
    batch_max = pc.max(batch_values).as_py()

    if batch_min is not None:
        ts_min = pd.Timestamp(batch_min).tz_localize(None)
        current_min = ts_min if current_min is None else min(current_min, ts_min)
    if batch_max is not None:
        ts_max = pd.Timestamp(batch_max).tz_localize(None)
        current_max = ts_max if current_max is None else max(current_max, ts_max)

    return current_min, current_max


def _filter_one_file(
    spec: FileSpec,
    cache_dir: Path,
    min_date: pd.Timestamp,
    suffix: str,
    overwrite: bool,
) -> FilterSummary:
    source_path = cache_dir / spec.source_name
    output_path = cache_dir / f"acuhit2_{spec.key}_{suffix}.parquet"

    if not source_path.exists():
        raise FileNotFoundError(f"Input parquet not found: {source_path}")

    if output_path.exists():
        if not overwrite:
            raise FileExistsError(
                f"Output file already exists: {output_path}. Use --overwrite to replace it."
            )
        output_path.unlink()

    dataset = ds.dataset(source_path, format="parquet")
    schema = dataset.schema

    if spec.date_column not in schema.names:
        raise KeyError(
            f"Date column '{spec.date_column}' not found in {source_path.name}. "
            f"Available columns: {schema.names}"
        )

    date_index = schema.get_field_index(spec.date_column)
    date_field_type = schema.field(spec.date_column).type
    cutoff = _cutoff_scalar(min_date, date_field_type)
    filter_expr = pc.field(spec.date_column) >= cutoff

    input_rows = dataset.count_rows()
    output_rows = 0
    min_kept_date: pd.Timestamp | None = None
    max_kept_date: pd.Timestamp | None = None

    scanner = dataset.scanner(
        columns=schema.names,
        filter=filter_expr,
        batch_size=250_000,
        use_threads=True,
    )

    writer = pq.ParquetWriter(
        where=output_path,
        schema=schema,
        compression="snappy",
    )
    try:
        for batch in scanner.to_batches():
            writer.write_batch(batch)
            output_rows += batch.num_rows
            min_kept_date, max_kept_date = _update_min_max(
                min_kept_date,
                max_kept_date,
                batch.column(date_index),
            )
    finally:
        writer.close()

    return FilterSummary(
        key=spec.key,
        source_path=source_path,
        output_path=output_path,
        input_rows=input_rows,
        output_rows=output_rows,
        dropped_rows=input_rows - output_rows,
        min_kept_date=min_kept_date,
        max_kept_date=max_kept_date,
    )


def main() -> None:
    args = _parse_args()
    min_date = _parse_min_date(args.min_date)
    cache_dir = Path(args.cache_dir)

    if not cache_dir.exists():
        raise FileNotFoundError(f"Cache directory not found: {cache_dir}")

    suffix = f"from{min_date.year}"

    print("=" * 72)
    print("ACUHIT Parquet Date Filter")
    print("=" * 72)
    print(f"Cache dir : {cache_dir.resolve()}")
    print(f"Min date  : {min_date.strftime('%Y-%m-%d %H:%M:%S')} (inclusive)")
    print(f"Suffix    : {suffix}")

    summaries: list[FilterSummary] = []
    for spec in FILE_SPECS:
        print(f"\n[{spec.key}] Filtering {spec.source_name} on '{spec.date_column}'...")
        summary = _filter_one_file(
            spec=spec,
            cache_dir=cache_dir,
            min_date=min_date,
            suffix=suffix,
            overwrite=args.overwrite,
        )
        summaries.append(summary)

        print(f"  Input rows    : {summary.input_rows:,}")
        print(f"  Output rows   : {summary.output_rows:,}")
        print(f"  Dropped rows  : {summary.dropped_rows:,}")
        print(f"  Min kept date : {_format_ts(summary.min_kept_date)}")
        print(f"  Max kept date : {_format_ts(summary.max_kept_date)}")
        print(f"  Output file   : {summary.output_path.name}")

    total_input = sum(s.input_rows for s in summaries)
    total_output = sum(s.output_rows for s in summaries)
    total_dropped = sum(s.dropped_rows for s in summaries)

    print("\n" + "=" * 72)
    print("FILTER COMPLETE")
    print("=" * 72)
    print(f"Total input rows   : {total_input:,}")
    print(f"Total output rows  : {total_output:,}")
    print(f"Total dropped rows : {total_dropped:,}")


if __name__ == "__main__":
    main()
