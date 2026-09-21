"""Lab 3 Task 4 — client-side canary test."""
from __future__ import annotations

import json
import random
import time
from collections import defaultdict
from datetime import datetime, timezone
from urllib import request as urlrequest
from urllib.error import URLError


GOOD = "https://itcs355-serve.lemonriver-4fb1eda0.koreacentral.azurecontainerapps.io"
CANARY = "https://itcs355-serve-canary.lemonriver-4fb1eda0.koreacentral.azurecontainerapps.io"

CANARY_WEIGHT = 0.10
DURATION_S = 300
REQUESTS_PER_SEC = 2
DEGRADATION_THRESHOLD = 0.05

PAYLOADS = [
    {"temp_c": 78.4, "vibration_mm_s": 3.1, "pressure_kpa": 315.2,
     "hours_since_service": 4200.0, "load_pct": 68.0, "ambient_humidity": 55.0},
    {"temp_c": 95.0, "vibration_mm_s": 8.2, "pressure_kpa": 420.0,
     "hours_since_service": 12000.0, "load_pct": 92.0, "ambient_humidity": 70.0},
    {"temp_c": 55.0, "vibration_mm_s": 1.2, "pressure_kpa": 210.0,
     "hours_since_service": 800.0, "load_pct": 30.0, "ambient_humidity": 40.0},
    {"temp_c": 110.0, "vibration_mm_s": 12.0, "pressure_kpa": 500.0,
     "hours_since_service": 18000.0, "load_pct": 95.0, "ambient_humidity": 80.0},
]


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def call(endpoint: str, payload: dict) -> float | None:
    url = f"{endpoint}/predict"
    data = json.dumps(payload).encode()
    req = urlrequest.Request(url, data=data,
                             headers={"Content-Type": "application/json"})
    try:
        with urlrequest.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read()).get("probability")
    except (URLError, TimeoutError, json.JSONDecodeError):
        return None


def main() -> int:
    random.seed(42)
    start_ts = ts()
    stats: dict[str, list[float]] = defaultdict(list)
    detection_time: str | None = None

    print(f"[{start_ts}] starting canary — {CANARY_WEIGHT*100:.0f}% canary, "
          f"{DURATION_S}s at {REQUESTS_PER_SEC} req/s")
    print(f"[{start_ts}] good   = {GOOD}")
    print(f"[{start_ts}] canary = {CANARY}\n")

    start = time.time()
    while time.time() - start < DURATION_S:
        payload = random.choice(PAYLOADS)
        route_canary = random.random() < CANARY_WEIGHT
        endpoint = CANARY if route_canary else GOOD
        label = "canary" if route_canary else "good"

        prob = call(endpoint, payload)
        if prob is not None:
            stats[label].append(prob)

        if (detection_time is None
                and len(stats["good"]) >= 20
                and len(stats["canary"]) >= 20):
            good_mean = sum(stats["good"]) / len(stats["good"])
            canary_mean = sum(stats["canary"]) / len(stats["canary"])
            delta = abs(canary_mean - good_mean)
            if delta > DEGRADATION_THRESHOLD:
                detection_time = ts()
                print(f"[{detection_time}] DEGRADATION DETECTED")
                print(f"    good mean:   {good_mean:.4f}  (n={len(stats['good'])})")
                print(f"    canary mean: {canary_mean:.4f}  (n={len(stats['canary'])})")
                print(f"    delta:       {delta:.4f}\n")

        time.sleep(1 / REQUESTS_PER_SEC)

    print(f"\n[{ts()}] test finished")
    print(f"    good   mean: {sum(stats['good'])/len(stats['good']):.4f}  (n={len(stats['good'])})")
    print(f"    canary mean: {sum(stats['canary'])/len(stats['canary']):.4f}  (n={len(stats['canary'])})")

    if detection_time:
        elapsed = (datetime.strptime(detection_time, "%Y-%m-%dT%H:%M:%SZ")
                   - datetime.strptime(start_ts, "%Y-%m-%dT%H:%M:%SZ")).total_seconds()
        print(f"    detection took: {elapsed:.0f}s from start")
    else:
        print("    no degradation detected above threshold")

    print(f"[{ts()}] ROLLBACK — routing 100% to good endpoint")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
