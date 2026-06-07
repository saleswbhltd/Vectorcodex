#!/usr/bin/env python3
"""Summarize completed VECTOR80 adaptive-threshold shadow outcomes."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Outcome:
    candidate_id: str
    utc_slot: str
    engine_id: str
    score: float
    validated_threshold: float
    score_gap: float
    in_rule_window: bool
    result: str
    pips: float


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def load_outcomes(path: Path) -> list[Outcome]:
    latest: dict[str, Outcome] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row.get("event") != "OUTCOME":
                continue
            candidate_id = row["candidate_id"]
            latest[candidate_id] = Outcome(
                candidate_id=candidate_id,
                utc_slot=row["utc_slot"],
                engine_id=row["engine_id"],
                score=float(row["score"]),
                validated_threshold=float(row["validated_threshold"]),
                score_gap=max(0.0, float(row["score_gap"])),
                in_rule_window=parse_bool(row["in_rule_window"]),
                result=row["outcome"],
                pips=float(row["outcome_pips"]),
            )
    return list(latest.values())


def wilson_lower(wins: int, total: int, z: float = 1.96) -> float:
    if total == 0:
        return 0.0
    rate = wins / total
    denominator = 1.0 + z * z / total
    centre = rate + z * z / (2.0 * total)
    margin = z * math.sqrt((rate * (1.0 - rate) + z * z / (4.0 * total)) / total)
    return (centre - margin) / denominator


def summarize(rows: list[Outcome]) -> tuple[int, int, float, float]:
    total = len(rows)
    wins = sum(row.result == "TARGET" for row in rows)
    avg_pips = sum(row.pips for row in rows) / total if total else 0.0
    return total, wins, avg_pips, wilson_lower(wins, total)


def print_delta_table(
    outcomes: list[Outcome], deltas: list[float], score_floor: float, minimum: int
) -> None:
    print("\nThreshold delta scan (completed outcomes)")
    print(" delta  trades  targets  hit_rate  avg_pips  wilson_low  status")
    ranked: list[tuple[float, float, float, int]] = []
    for delta in deltas:
        rows = [
            row
            for row in outcomes
            if row.score_gap <= delta + 1e-9 and row.score >= score_floor
        ]
        total, wins, avg_pips, lower = summarize(rows)
        status = "eligible" if total >= minimum else "insufficient"
        print(
            f" {delta:5.2f}  {total:6d}  {wins:7d}  "
            f"{wins / total:8.1%}  {avg_pips:8.2f}  {lower:10.1%}  {status}"
            if total
            else f" {delta:5.2f}       0        0       n/a      0.00        n/a  {status}"
        )
        if total >= minimum:
            ranked.append((lower, avg_pips, -delta, total))

    if not ranked:
        print(f"\nRecommendation: collect at least {minimum} completed outcomes per delta.")
        return
    _, _, negative_delta, total = max(ranked)
    print(
        f"\nEvidence leader: delta={-negative_delta:.2f} "
        f"(ranked by 95% Wilson lower bound, n={total})."
    )


def print_group_table(outcomes: list[Outcome], minimum: int) -> None:
    groups: dict[tuple[str, str], list[Outcome]] = defaultdict(list)
    for row in outcomes:
        groups[("UTC slot", row.utc_slot)].append(row)
        groups[("Engine", row.engine_id)].append(row)

    print("\nCompleted outcomes by group")
    print(" group     value           trades  hit_rate  avg_pips  wilson_low  status")
    for (kind, value), rows in sorted(groups.items()):
        total, wins, avg_pips, lower = summarize(rows)
        status = "usable" if total >= minimum else "small"
        print(
            f" {kind:9} {value[:15]:15} {total:6d}  {wins / total:8.1%}  "
            f"{avg_pips:8.2f}  {lower:10.1%}  {status}"
        )


def parse_deltas(value: str) -> list[float]:
    deltas = sorted({round(float(item), 4) for item in value.split(",")})
    if not deltas or any(delta < 0.0 for delta in deltas):
        raise argparse.ArgumentTypeError("deltas must be non-negative comma-separated values")
    return deltas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path, help="VECTOR80 adaptive threshold CSV")
    parser.add_argument(
        "--deltas",
        type=parse_deltas,
        default=parse_deltas("0.02,0.04,0.06,0.08,0.10,0.12,0.15"),
    )
    parser.add_argument("--score-floor", type=float, default=0.70)
    parser.add_argument("--minimum-sample", type=int, default=30)
    parser.add_argument(
        "--rule-window-only",
        action="store_true",
        help="analyze only rows marked inside the configured UTC rule window",
    )
    args = parser.parse_args()

    outcomes = load_outcomes(args.log)
    if args.rule_window_only:
        outcomes = [row for row in outcomes if row.in_rule_window]
    if not outcomes:
        print("No completed OUTCOME rows found.")
        return 1

    print(f"Loaded {len(outcomes)} unique completed outcomes from {args.log}")
    print_delta_table(outcomes, args.deltas, args.score_floor, args.minimum_sample)
    print_group_table(outcomes, args.minimum_sample)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
