#!/usr/bin/env python3
"""Persistent VECTOR80 MT5-to-Python scoring bridge."""

from __future__ import annotations

import argparse
import json
import os
import signal
import tempfile
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "2")

import joblib
import pandas as pd

from refresh_vector80_scores import COMMON, ENGINE_BY_ID, fit_engine_bundle, prepare_live_panel


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUESTS = COMMON / "VECTOR80_score_requests.csv"
DEFAULT_SCORES = COMMON / "VECTOR80_model_scores_live.csv"
DEFAULT_HEARTBEAT = COMMON / "VECTOR80_bridge_heartbeat.csv"
DEFAULT_MT5_HEARTBEAT = COMMON / "VECTOR80_mt5_heartbeat.csv"
DEFAULT_LOG = COMMON / "VECTOR80_bridge.log"
DEFAULT_STATE = COMMON / "VECTOR80_bridge_state.json"
DEFAULT_MODEL_CACHE = ROOT / "generated" / "VECTOR80_live_model_bundle.joblib"


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        Path(tmp_name).unlink(missing_ok=True)


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        frame.to_csv(tmp, index=False, float_format="%.6f")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class Bridge:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.stop = False
        self.status = "STARTING"
        self.detail = "loading_models"
        self.last_scored_bar = ""
        self.score_rows = 0
        self.processed: set[tuple[str, str]] = set()
        self.last_request_mtime_ns = -1
        self.models = {}
        self.features: list[str] = []
        self.fill_values = None

    def load_state(self) -> None:
        try:
            data = json.loads(self.args.state.read_text(encoding="utf-8"))
            self.processed = {tuple(item) for item in data.get("processed", [])}
        except (FileNotFoundError, ValueError, TypeError):
            self.processed = set()

    def save_state(self) -> None:
        recent = sorted(self.processed)[-self.args.max_processed_requests :]
        atomic_text(self.args.state, json.dumps({"processed": recent}, indent=2))

    def log(self, message: str) -> None:
        line = f"{pd.Timestamp.now().isoformat(timespec='seconds')} {message}"
        print(line, flush=True)
        with self.args.log.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def heartbeat(self) -> None:
        text = (
            "epoch,status,pid,last_scored_bar,score_rows,detail\n"
            f"{int(time.time())},{self.status},{os.getpid()},"
            f"{self.last_scored_bar},{self.score_rows},{self.detail}\n"
        )
        atomic_text(self.args.heartbeat, text)

    def mt5_is_fresh(self) -> bool:
        try:
            heartbeat = pd.read_csv(self.args.mt5_heartbeat)
            epoch = int(heartbeat.iloc[-1]["epoch"])
            return time.time() - epoch <= self.args.mt5_max_age_sec
        except (FileNotFoundError, KeyError, ValueError, IndexError, pd.errors.EmptyDataError):
            return False

    def load_requests(self) -> pd.DataFrame:
        try:
            mtime_ns = self.args.requests.stat().st_mtime_ns
        except FileNotFoundError:
            return pd.DataFrame()
        if mtime_ns == self.last_request_mtime_ns:
            return pd.DataFrame()
        self.last_request_mtime_ns = mtime_ns
        try:
            requests = pd.read_csv(self.args.requests)
        except (FileNotFoundError, pd.errors.EmptyDataError):
            return pd.DataFrame()
        required = {
            "bar_time",
            "engine_id",
            "pivot_time",
            "pivot_price",
            "label",
            "side",
        }
        if not required.issubset(requests.columns):
            raise RuntimeError(f"request file missing columns: {sorted(required - set(requests.columns))}")
        requests = requests[requests["engine_id"].isin(ENGINE_BY_ID)].copy()
        requests["bar_time"] = pd.to_datetime(requests["bar_time"])
        requests["pivot_time"] = pd.to_datetime(requests["pivot_time"])
        requests = requests.drop_duplicates(["bar_time", "engine_id"], keep="last")
        return requests.sort_values(["bar_time", "engine_id"])

    def pending_requests(self, requests: pd.DataFrame) -> pd.DataFrame:
        if requests.empty:
            return requests
        mask = [
            (row.bar_time.strftime("%Y-%m-%d %H:%M:%S"), str(row.engine_id))
            not in self.processed
            for row in requests.itertuples(index=False)
        ]
        return requests.loc[mask]

    def latest_live_tick_time(self) -> pd.Timestamp | None:
        live = sorted(COMMON.glob("VECTOR80_LIVE_TICKS_*.csv"))
        if not live:
            return None
        try:
            tail = pd.read_csv(live[-1], usecols=["datetime"]).tail(1)
            if tail.empty:
                return None
            return pd.Timestamp(tail.iloc[0]["datetime"])
        except (OSError, ValueError, KeyError, pd.errors.EmptyDataError):
            return None

    def discard_expired(self, pending: pd.DataFrame) -> pd.DataFrame:
        latest_tick = self.latest_live_tick_time()
        if latest_tick is None or pending.empty:
            return pending
        cutoff = latest_tick - pd.Timedelta(minutes=self.args.request_max_age_min)
        expired = pending[pending["bar_time"] < cutoff]
        for row in expired.itertuples(index=False):
            key = (row.bar_time.strftime("%Y-%m-%d %H:%M:%S"), str(row.engine_id))
            self.processed.add(key)
            self.log(f"EXPIRED bar={key[0]} engine={key[1]} latest_tick={latest_tick}")
        return pending[pending["bar_time"] >= cutoff]

    def tick_sources(self) -> list[Path]:
        live = sorted(COMMON.glob("VECTOR80_LIVE_TICKS_*.csv"))
        seeds = sorted(
            COMMON.glob("VECTOR80_BROKER_TICKS_*.csv"),
            key=lambda path: path.stat().st_mtime,
        )
        sources = ([seeds[-1]] if seeds else []) + live[-3:]
        unique: list[Path] = []
        for path in sources:
            if path not in unique:
                unique.append(path)
        return unique

    def build_tick_snapshot(self) -> Path:
        sources = self.tick_sources()
        if not sources:
            raise RuntimeError("no broker seed or live tick files found")
        frames = [pd.read_csv(path) for path in sources]
        ticks = pd.concat(frames, ignore_index=True)
        key = "time_msc" if "time_msc" in ticks.columns else "datetime"
        ticks = ticks.drop_duplicates(key, keep="last").sort_values(key)
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=self.args.tick_history_days)
        parsed = pd.to_datetime(ticks["datetime"], errors="coerce")
        ticks = ticks.loc[parsed >= cutoff]
        fd, name = tempfile.mkstemp(prefix="vector80_ticks_", suffix=".csv")
        os.close(fd)
        path = Path(name)
        ticks.to_csv(path, index=False)
        return path

    def requests_as_events(self, requests: pd.DataFrame) -> pd.DataFrame:
        events = requests.copy()
        events["event_time"] = events["bar_time"]
        return events

    def merge_scores(self, rows: pd.DataFrame) -> None:
        frames = []
        if self.args.scores.exists():
            try:
                frames.append(pd.read_csv(self.args.scores))
            except pd.errors.EmptyDataError:
                pass
        frames.append(rows)
        scores = pd.concat(frames, ignore_index=True)
        scores = scores.drop_duplicates(["time", "engine_id"], keep="last")
        scores = scores.sort_values(["time", "engine_id"]).tail(self.args.max_score_rows)
        atomic_csv(scores, self.args.scores)
        self.score_rows = len(scores)

    def score(self, requests: pd.DataFrame) -> None:
        pending = self.pending_requests(requests)
        if pending.empty:
            return
        pending = self.discard_expired(pending)
        if pending.empty:
            self.save_state()
            return
        keys = [
            (row.bar_time.strftime("%Y-%m-%d %H:%M:%S"), str(row.engine_id))
            for row in pending.itertuples(index=False)
        ]
        self.processed.update(keys)
        self.save_state()

        snapshot = self.build_tick_snapshot()
        try:
            panel = prepare_live_panel(
                snapshot,
                self.requests_as_events(requests),
                self.features,
                self.fill_values,
            )
        finally:
            snapshot.unlink(missing_ok=True)

        rows = []
        for request in pending.itertuples(index=False):
            bar_time = pd.Timestamp(request.bar_time)
            key = (bar_time.strftime("%Y-%m-%d %H:%M:%S"), str(request.engine_id))
            if bar_time not in panel.index:
                self.log(f"FAILED feature row unavailable bar={key[0]} engine={key[1]}")
                continue
            score = float(self.models[key[1]].predict_proba(panel.loc[[bar_time]])[0, 1])
            csv_time = bar_time - pd.Timedelta(minutes=self.args.score_shift_min)
            rows.append(
                {
                    "time": csv_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "engine_id": key[1],
                    "score": score,
                }
            )
            self.last_scored_bar = key[0]
            self.log(f"SCORE bar={key[0]} engine={key[1]} score={score:.6f}")
        if rows:
            self.merge_scores(pd.DataFrame(rows))

    def load_models(self) -> None:
        if self.args.model_cache.exists():
            bundle = joblib.load(self.args.model_cache)
            self.models = bundle["models"]
            self.features = bundle["features"]
            self.fill_values = bundle["fill_values"]
            self.log(f"loaded cached model bundle: {self.args.model_cache}")
            return

        self.log("building one-time frozen VECTOR80 model cache")
        self.models, self.features, self.fill_values, _, _ = fit_engine_bundle()
        self.args.model_cache.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(
            prefix=f".{self.args.model_cache.name}.",
            dir=self.args.model_cache.parent,
        )
        os.close(fd)
        tmp = Path(name)
        try:
            joblib.dump(
                {
                    "models": self.models,
                    "features": self.features,
                    "fill_values": self.fill_values,
                },
                tmp,
                compress=3,
            )
            os.replace(tmp, self.args.model_cache)
        finally:
            tmp.unlink(missing_ok=True)
        self.log(f"saved model cache: {self.args.model_cache}")

    def run(self) -> None:
        self.args.log.parent.mkdir(parents=True, exist_ok=True)
        self.load_state()
        self.heartbeat()
        self.load_models()
        self.status = "RUNNING"
        self.detail = "ready"
        self.heartbeat()
        self.log("bridge ready")

        last_heartbeat = 0.0
        while not self.stop:
            now = time.monotonic()
            if now - last_heartbeat >= self.args.heartbeat_sec:
                self.heartbeat()
                last_heartbeat = now
            if not self.mt5_is_fresh():
                self.detail = "waiting_for_mt5"
                time.sleep(self.args.poll_sec)
                continue
            self.detail = "ready"
            try:
                self.score(self.load_requests())
            except Exception as exc:
                self.status = "ERROR"
                self.detail = type(exc).__name__
                self.heartbeat()
                self.log(f"ERROR {type(exc).__name__}: {exc}")
                time.sleep(self.args.error_retry_sec)
                self.status = "RUNNING"
                self.detail = "retrying"
            time.sleep(self.args.poll_sec)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=Path, default=DEFAULT_REQUESTS)
    parser.add_argument("--scores", type=Path, default=DEFAULT_SCORES)
    parser.add_argument("--heartbeat", type=Path, default=DEFAULT_HEARTBEAT)
    parser.add_argument("--mt5-heartbeat", type=Path, default=DEFAULT_MT5_HEARTBEAT)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--poll-sec", type=float, default=2.0)
    parser.add_argument("--heartbeat-sec", type=float, default=5.0)
    parser.add_argument("--mt5-max-age-sec", type=int, default=15)
    parser.add_argument("--error-retry-sec", type=float, default=5.0)
    parser.add_argument("--score-shift-min", type=int, default=180)
    parser.add_argument("--tick-history-days", type=int, default=14)
    parser.add_argument("--max-score-rows", type=int, default=20000)
    parser.add_argument("--request-max-age-min", type=int, default=10)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--model-cache", type=Path, default=DEFAULT_MODEL_CACHE)
    parser.add_argument("--max-processed-requests", type=int, default=5000)
    return parser.parse_args()


def main() -> None:
    bridge = Bridge(parse_args())

    def stop(_signum: int, _frame: object) -> None:
        bridge.stop = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        bridge.run()
    finally:
        bridge.status = "STOPPED"
        bridge.detail = "shutdown"
        bridge.heartbeat()
        bridge.log("bridge stopped")


if __name__ == "__main__":
    main()
