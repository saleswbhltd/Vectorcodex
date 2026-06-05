r"""
VECTOR003_BRIDGE.py — Python signal bridge for VECTOR003 EA.

Architecture:
  EA writes M5 panel state to vector003_request.json
  Bridge polls for file, runs 8 GBMs, writes decision to vector003_response.json
  EA reads decision and acts on it

Communication:
  Files in MT5 Common\Files\ directory (cross-process safe)
  Synchronous: EA waits for response within deadline (~3s)
  Heartbeat: vector003_bridge.heartbeat written every ~1s
  Single-instance: bridge refuses to start if a fresh heartbeat exists

Models loaded from: /home/cmake/Vector/models/
Manifest:           /home/cmake/Vector/models/manifest.json
"""

import os
import json
import time
import pickle
import signal
import sys
import pandas as pd
import numpy as np
from datetime import datetime

# Models live next to this script (override with $VECTOR_MODELS).
MODEL_DIR = os.environ.get(
    "VECTOR_MODELS",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "models"),
)

# MT5 Common\Files — resolved per-OS (override with $MT5_COMMON_DIR).
def _resolve_mt5_common():
    env = os.environ.get("MT5_COMMON_DIR")
    if env:
        return env
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "")
        return os.path.join(appdata, "MetaQuotes", "Terminal", "Common", "Files")
    return "/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/Common/Files"

MT5_COMMON = _resolve_mt5_common()
REQUEST_FILE   = f"{MT5_COMMON}/vector003_request.json"
RESPONSE_FILE  = f"{MT5_COMMON}/vector003_response.json"
LOG_FILE       = f"{MT5_COMMON}/vector003_bridge.log"
HEARTBEAT_FILE = f"{MT5_COMMON}/vector003_bridge.heartbeat"

POLL_INTERVAL    = 0.1   # seconds — fast poll
MAX_AGE_SEC      = 30    # discard requests older than this
HEARTBEAT_PERIOD = 1.0   # seconds — write heartbeat at least this often
LIVE_THRESHOLD   = 5.0   # seconds — heartbeat newer than this means another bridge is alive

# ───────────────────────────────────────────────────────────────────
# Globals: loaded once at startup
# ───────────────────────────────────────────────────────────────────
manifest = None
models = {}        # ctx → {model, features, feature_medians}
stage1_rules = {}  # ctx → {zone_pct, K, rules: [{indicator, direction, threshold}]}


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def write_heartbeat():
    try:
        with open(HEARTBEAT_FILE, "w") as f:
            json.dump({"pid": os.getpid(), "ts": time.time()}, f)
    except Exception as e:
        log(f"heartbeat write failed: {e}")


def check_single_instance():
    """Refuse to start if another bridge is already writing a fresh heartbeat."""
    if not os.path.exists(HEARTBEAT_FILE):
        return True
    try:
        with open(HEARTBEAT_FILE) as f:
            hb = json.load(f)
        age = time.time() - float(hb.get("ts", 0))
        if age < LIVE_THRESHOLD:
            log(f"!! Another bridge is alive (pid={hb.get('pid')}, hb age={age:.1f}s)")
            log(f"!! Refusing to start. Kill the other bridge first.")
            return False
        log(f"Stale heartbeat ({age:.1f}s old) — taking over")
    except Exception as e:
        log(f"could not parse heartbeat ({e}) — taking over")
    return True


def cleanup_heartbeat(*_):
    try:
        if os.path.exists(HEARTBEAT_FILE):
            os.remove(HEARTBEAT_FILE)
    except Exception:
        pass
    log("Bridge stopped — heartbeat cleared")
    sys.exit(0)


def load_models():
    global manifest, models, stage1_rules
    log("Loading manifest...")
    with open(f"{MODEL_DIR}/manifest.json") as f:
        manifest = json.load(f)
    log(f"  classes: {len(manifest['classes'])}")
    for ctx in manifest["classes"]:
        path = f"{MODEL_DIR}/gbm_{ctx}.pkl"
        if not os.path.exists(path):
            log(f"  ! missing model: {path}")
            continue
        with open(path, "rb") as f:
            models[ctx] = pickle.load(f)
        log(f"  loaded {ctx}: {len(models[ctx]['features'])} features")
    log(f"Total models loaded: {len(models)}")

    # Load Stage 1 OR-ensemble thresholds (from VECTOR003_CONTRACT.md / stage1_thresholds.json)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    s1_path = os.path.join(script_dir, "research", "stage1_thresholds.json")
    if os.path.exists(s1_path):
        with open(s1_path) as f:
            stage1_rules = json.load(f)
        log(f"Stage 1 rules loaded: {len(stage1_rules)} classes")
    else:
        log("WARNING: stage1_thresholds.json not found — Stage 1 gate disabled")
        stage1_rules = {}


def stage1_passes(features, ctx):
    """
    Check if bar passes Stage 1 OR ensemble for a given class.
    Returns True if ANY rule fires (indicator in pivot zone).
    If no rules defined for class, passes by default.
    """
    if ctx not in stage1_rules:
        return True  # no rules defined → pass through
    rules = stage1_rules[ctx]["rules"]
    for rule in rules:
        ind = rule["indicator"]
        val = features.get(ind)
        if val is None:
            continue
        thr = rule["threshold"]
        if rule["direction"] == ">=" and val >= thr:
            return True
        if rule["direction"] == "<=" and val <= thr:
            return True
    return False  # no rule fired → bar not a candidate for this class


def predict_all_classes(features_dict):
    """
    Run 8 GBMs but ONLY for classes that pass Stage 1 OR ensemble.
    Classes that fail Stage 1 get prob=0.0 (cheaper than running GBM).
    Returns per-class probabilities dict.
    """
    probs = {}
    for ctx, m in models.items():
        # Gate 2: Stage 1 OR ensemble check
        if not stage1_passes(features_dict, ctx):
            probs[ctx] = 0.0
            continue

        feat_list = m["features"]
        medians = m["feature_medians"]
        X = []
        for fname in feat_list:
            v = features_dict.get(fname)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                v = medians.get(fname, 0.0)
            X.append(float(v))
        X = np.array(X, dtype=np.float64).reshape(1, -1)
        try:
            p = float(m["model"].predict_proba(X)[0, 1])
        except Exception as e:
            log(f"  predict failed for {ctx}: {e}")
            p = 0.0
        probs[ctx] = p
    return probs


def decide(probs, request_data):
    """
    Apply VECTOR003 decision rules:
      - max prob ≥ threshold
      - cooldown elapsed (per-direction: BUY/SELL tracked separately by EA)
      - local-extreme check is done EA-side
    """
    threshold    = request_data.get("threshold",    manifest["default_params"]["threshold"])
    cooldown_min = request_data.get("cooldown_min", manifest["default_params"]["cooldown_min"])

    best_class = max(probs, key=probs.get)
    best_prob  = probs[best_class]
    side       = manifest["label_to_side"][manifest["class_to_label"][best_class]]

    decision = {
        "fire": False,
        "best_class": best_class,
        "best_prob":  best_prob,
        "side":       side,
        "all_probs":  probs,
        "reason":     "",
    }

    if best_prob < threshold:
        decision["reason"] = f"prob {best_prob:.3f} < threshold {threshold}"
        return decision

    # Cooldown check — EA sends per-direction last signal times.
    # Use the one matching the determined side.
    bar_time = request_data.get("bar_time_unix", 0)
    if side == "BUY":
        last_sig = request_data.get("last_buy_signal_unix")
    else:
        last_sig = request_data.get("last_sell_signal_unix")

    if last_sig is not None and bar_time > 0:
        if bar_time - last_sig < cooldown_min * 60:
            decision["reason"] = "cooldown not elapsed"
            return decision

    decision["fire"]   = True
    decision["reason"] = "OK"
    return decision


def process_request(req):
    """req = parsed JSON from EA. Returns response dict."""
    features = req.get("features", {})
    if not features:
        return {"fire": False, "best_class": "", "best_prob": 0.0,
                "side": "", "reason": "no features in request"}
    probs    = predict_all_classes(features)
    decision = decide(probs, req)
    decision["request_id"] = req.get("request_id", "")
    decision["timestamp"]  = datetime.now().isoformat()
    return decision


def main():
    log("=" * 60)
    log("VECTOR003 Bridge starting")
    log("=" * 60)
    if not check_single_instance():
        sys.exit(1)
    signal.signal(signal.SIGTERM, cleanup_heartbeat)
    signal.signal(signal.SIGINT,  cleanup_heartbeat)
    load_models()
    write_heartbeat()
    log(f"Polling {REQUEST_FILE} every {POLL_INTERVAL}s")
    log(f"Heartbeat: {HEARTBEAT_FILE}")
    log("Ctrl+C to stop")

    last_req_mtime = 0
    last_heartbeat = 0.0
    request_count = 0

    # Remove any stale response file so new EA instances don't pick up old data.
    if os.path.exists(RESPONSE_FILE):
        try: os.remove(RESPONSE_FILE)
        except Exception: pass

    while True:
        try:
            now = time.time()
            if now - last_heartbeat >= HEARTBEAT_PERIOD:
                write_heartbeat()
                last_heartbeat = now
            if not os.path.exists(REQUEST_FILE):
                time.sleep(POLL_INTERVAL); continue
            mtime = os.path.getmtime(REQUEST_FILE)
            if mtime == last_req_mtime:
                time.sleep(POLL_INTERVAL); continue
            # Check age before reading (don't mark mtime yet — retry if file is empty)
            if time.time() - mtime > MAX_AGE_SEC:
                last_req_mtime = mtime  # skip stale request
                time.sleep(POLL_INTERVAL); continue

            with open(REQUEST_FILE) as f:
                content = f.read()

            if not content.strip():
                # EA just truncated the file but hasn't written content yet; retry shortly.
                time.sleep(0.03); continue

            req = json.loads(content)
            last_req_mtime = mtime  # mark as processed only after successful parse

            t0 = time.time()
            response = process_request(req)
            elapsed_ms = (time.time() - t0) * 1000

            # Atomic write: write to .tmp then rename so EA never reads a partial file.
            tmp = RESPONSE_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(response, f)
            os.replace(tmp, RESPONSE_FILE)

            request_count += 1
            if response.get("fire"):
                log(f"#{request_count}  FIRE  {response['side']}  "
                    f"class={response['best_class']}  prob={response['best_prob']:.3f}  "
                    f"({elapsed_ms:.0f}ms)")
            else:
                if request_count % 100 == 0:
                    log(f"#{request_count}  noop  max_prob={response.get('best_prob',0):.3f}  "
                        f"({elapsed_ms:.0f}ms)")
        except KeyboardInterrupt:
            log("Stopped by user")
            break
        except Exception as e:
            log(f"Error: {e}")
            time.sleep(0.05)  # short sleep then retry

    cleanup_heartbeat()


if __name__ == "__main__":
    main()
