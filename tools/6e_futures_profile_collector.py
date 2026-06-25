# pip install yfinance pandas numpy

from datetime import datetime, timezone, timedelta
from pathlib import Path
import time
import traceback

import numpy as np
import pandas as pd
import yfinance as yf


TICKER = "6E=F"
DAYS_BACK = 3
INTERVAL = "15m"
PRICE_STEP = 0.00005
VALUE_AREA_PCT = 0.70
TOP_N_HVN_LVN = 10

SESSION_HOURS = {
    "Asian": (0, 8),
    "London": (8, 16),
    "NewYork": (13, 21),
}

OUT_PROFILE = "6E_volume_profile.csv"
OUT_LEVELS = "6E_profile_levels.csv"
LOCAL_OUTPUT_DIR = Path(__file__).resolve().parent
OLD_ROBOFOREX_DATA_ID = "5FFA568149E88FCD5B44D926DCFEAA79"
MT5_FILES_PATH = (
    Path.home()
    / "AppData"
    / "Roaming"
    / "MetaQuotes"
    / "Terminal"
    / OLD_ROBOFOREX_DATA_ID
    / "MQL5"
    / "Files"
)
PORTABLE_MT5_ROOT = Path.home() / "MT5"
PORTABLE_MT5_FILES_PATHS = [
    PORTABLE_MT5_ROOT / f"RoboF{i}" / "MQL5" / "Files"
    for i in range(1, 6)
]

RUN_CONTINUOUSLY = True
REFRESH_MINUTES = 5


def flatten_yfinance_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [str(col[0]).lower() for col in df.columns]
    else:
        df.columns = [str(col).lower() for col in df.columns]
    return df


def download_recent(ticker: str, days_back: int, interval: str) -> pd.DataFrame:
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days_back)
    df = yf.download(
        ticker,
        start=start_dt,
        end=end_dt,
        interval=interval,
        auto_adjust=False,
        progress=False,
    )
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = flatten_yfinance_columns(df)
    df = df.loc[:, ["open", "high", "low", "close", "volume"]]
    df = df.apply(pd.to_numeric, errors="coerce").dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


def detect_session() -> str:
    hour = datetime.now(timezone.utc).hour
    for name, (start_hour, end_hour) in SESSION_HOURS.items():
        if start_hour <= hour < end_hour:
            return name
    return "OffHours"


def filter_by_session(df: pd.DataFrame, session_name: str) -> pd.DataFrame:
    if df.empty or session_name not in SESSION_HOURS:
        return df.iloc[0:0]
    start_hour, end_hour = SESSION_HOURS[session_name]
    return df[(df.index.hour >= start_hour) & (df.index.hour < end_hour)]


def build_profile(df: pd.DataFrame, price_step: float) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["price", "volume"])

    low_min = float(df["low"].min())
    high_max = float(df["high"].max())
    price_min = float(np.floor(low_min / price_step) * price_step)
    price_max = float(np.ceil(high_max / price_step) * price_step)
    prices = np.round(np.arange(price_min, price_max + price_step, price_step), 10)
    volumes = np.zeros(len(prices), dtype=float)

    for _, row in df.iterrows():
        low = float(row["low"])
        high = float(row["high"])
        volume = float(row["volume"])
        if not np.isfinite(volume) or volume <= 0:
            continue

        if high <= low:
            idx = int(np.argmin(np.abs(prices - float(row["close"]))))
            volumes[idx] += volume
            continue

        touched = np.where((prices >= low) & (prices <= high))[0]
        if len(touched) == 0:
            idx = int(np.argmin(np.abs(prices - float(row["close"]))))
            volumes[idx] += volume
        else:
            volumes[touched] += volume / len(touched)

    profile = pd.DataFrame({"price": prices, "volume": volumes})
    return profile[profile["volume"] > 0].reset_index(drop=True)


def poc_vah_val(profile: pd.DataFrame, value_area_pct: float):
    prof = profile.sort_values("price").reset_index(drop=True)
    poc_idx = int(prof["volume"].idxmax())
    poc_price = float(prof.loc[poc_idx, "price"])
    total = float(prof["volume"].sum())
    target = value_area_pct * total
    cumulative = float(prof.loc[poc_idx, "volume"])
    lo = hi = poc_idx

    while cumulative < target:
        left = float(prof.loc[lo - 1, "volume"]) if lo > 0 else -1.0
        right = float(prof.loc[hi + 1, "volume"]) if hi < len(prof) - 1 else -1.0
        if right >= left and hi < len(prof) - 1:
            hi += 1
            cumulative += float(prof.loc[hi, "volume"])
        elif lo > 0:
            lo -= 1
            cumulative += float(prof.loc[lo, "volume"])
        else:
            break

    return poc_price, float(prof.loc[hi, "price"]), float(prof.loc[lo, "price"]), prof


def hvn_lvn(prof_sorted: pd.DataFrame, top_n: int):
    volumes = prof_sorted["volume"].to_numpy(float)
    prices = prof_sorted["price"].to_numpy(float)
    hvn = []
    lvn = []

    for idx in range(1, len(volumes) - 1):
        if volumes[idx] > volumes[idx - 1] and volumes[idx] > volumes[idx + 1]:
            hvn.append((prices[idx], volumes[idx]))
        if volumes[idx] < volumes[idx - 1] and volumes[idx] < volumes[idx + 1]:
            lvn.append((prices[idx], volumes[idx]))

    return (
        sorted(hvn, key=lambda item: item[1], reverse=True)[:top_n],
        sorted(lvn, key=lambda item: item[1])[:top_n],
    )


def levels_from_profile(profile: pd.DataFrame, tag: str, generated_utc: str) -> pd.DataFrame:
    if profile.empty:
        return pd.DataFrame(columns=["level_type", "price", "tag", "updated_utc"])

    poc, vah, val, prof_sorted = poc_vah_val(profile, VALUE_AREA_PCT)
    hvn, lvn = hvn_lvn(prof_sorted, TOP_N_HVN_LVN)
    rows = [
        {"level_type": "POC", "price": poc, "tag": tag, "updated_utc": generated_utc},
        {"level_type": "VAH", "price": vah, "tag": tag, "updated_utc": generated_utc},
        {"level_type": "VAL", "price": val, "tag": tag, "updated_utc": generated_utc},
    ]
    rows += [
        {"level_type": "HVN", "price": float(price), "tag": tag, "updated_utc": generated_utc}
        for price, _ in hvn
    ]
    rows += [
        {"level_type": "LVN", "price": float(price), "tag": tag, "updated_utc": generated_utc}
        for price, _ in lvn
    ]
    return pd.DataFrame(rows)


def get_last_trading_day() -> datetime.date:
    now = datetime.utcnow()
    weekday = now.weekday()
    if weekday == 0:
        return (now - timedelta(days=3)).date()
    if weekday == 6:
        return (now - timedelta(days=2)).date()
    if weekday == 5:
        return (now - timedelta(days=1)).date()
    return (now - timedelta(days=1)).date()


def save_outputs(hist_profile: pd.DataFrame, levels_df: pd.DataFrame) -> None:

    output_paths = [MT5_FILES_PATH] + [path for path in PORTABLE_MT5_FILES_PATHS if path.exists()]
    for files_path in output_paths:
        files_path.mkdir(parents=True, exist_ok=True)
        hist_profile.to_csv(files_path / OUT_PROFILE, index=False)
        levels_df.to_csv(files_path / OUT_LEVELS, index=False, sep=";")


def run_once() -> None:
    df = download_recent(TICKER, DAYS_BACK, INTERVAL)
    generated_dt = datetime.now(timezone.utc)
    generated_utc = generated_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    session_now = detect_session()
    utc_today = datetime.utcnow().date()
    start_today = datetime(utc_today.year, utc_today.month, utc_today.day)
    end_today = start_today + timedelta(days=1)
    today_df = df[(df.index >= start_today) & (df.index < end_today)]
    session_df = filter_by_session(today_df, session_now)

    session_profile = build_profile(session_df, PRICE_STEP)
    session_levels = levels_from_profile(session_profile, session_now, generated_utc)

    yday = get_last_trading_day()
    start_yday = datetime(yday.year, yday.month, yday.day)
    end_yday = start_yday + timedelta(days=1)
    yesterday_df = df[(df.index >= start_yday) & (df.index < end_yday)]
    yesterday_profile = build_profile(yesterday_df, PRICE_STEP)
    yesterday_levels = levels_from_profile(yesterday_profile, "Yesterday", generated_utc)

    levels_df = pd.concat([session_levels, yesterday_levels], ignore_index=True)
    meta = pd.DataFrame(
        [
            {
                "level_type": "generated_utc",
                "price": generated_dt.timestamp(),
                "tag": "meta",
                "updated_utc": generated_utc,
            }
        ]
    )

    if levels_df.empty:
        composite = build_profile(df, PRICE_STEP)
        levels_df = levels_from_profile(composite, "Composite", generated_utc)
        hist_profile = composite
    elif not session_profile.empty:
        hist_profile = session_profile
    else:
        hist_profile = yesterday_profile

    levels_df = pd.concat([meta, levels_df], ignore_index=True)
    save_outputs(hist_profile, levels_df)
    print(f"[{generated_utc}] wrote {len(levels_df)} rows to {MT5_FILES_PATH / OUT_LEVELS} and portable RoboF files")


def is_weekday_utc() -> bool:
    return datetime.utcnow().weekday() < 5


def main() -> None:
    if not RUN_CONTINUOUSLY:
        run_once()
        return

    print(f"Live mode: refresh every {REFRESH_MINUTES} min. Ctrl+C to stop.")
    try:
        while True:
            if is_weekday_utc():
                try:
                    run_once()
                except Exception as exc:
                    print("Error in run_once():", exc)
                    traceback.print_exc()
            else:
                print(f"[{datetime.utcnow()}] weekend detected; sleeping")
            time.sleep(REFRESH_MINUTES * 60)
    except KeyboardInterrupt:
        print("Stopped by user.")


if __name__ == "__main__":
    main()


