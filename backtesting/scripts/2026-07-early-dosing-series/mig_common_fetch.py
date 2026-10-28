#!/usr/bin/env python3
"""Fetch NS treatments (28d) for users F and H; cache to JSON in scratchpad."""
import json, sys, time
import requests
from datetime import datetime, timedelta, timezone

SCRATCH = "/private/tmp/claude-501/-Users-USER-StudioProjects-AndroidAPS/db82de70-d40e-4e73-9c47-395352be1ee8/scratchpad"
SITES = {
    "F": ("https://<REDACTED>", "<REDACTED>"),  # NS base+token redacted for public repo
    "H": ("https://<REDACTED>", "<REDACTED>"),  # NS base+token redacted for public repo
}
NOW = datetime(2026, 7, 6, 10, 15, tzinfo=timezone.utc)  # anchor "now"
SINCE = (NOW - timedelta(days=28)).strftime("%Y-%m-%dT%H:%M:%SZ")

def fetch(base, token, since, retries=6):
    out = []
    t0 = NOW - timedelta(days=28)
    while t0 < NOW:
        t1 = min(t0 + timedelta(days=7), NOW)
        params = {
            "token": token, "count": 5000,
            "find[created_at][$gte]": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "find[created_at][$lt]": t1.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        for attempt in range(retries):
            try:
                r = requests.get(f"{base}/api/v1/treatments.json", params=params, timeout=120)
                r.raise_for_status()
                chunk = r.json()
                out.extend(chunk)
                print(f"  {t0.date()}..{t1.date()}: {len(chunk)} treatments", flush=True)
                break
            except Exception as e:
                print(f"  retry {attempt+1} ({e})", flush=True)
                time.sleep(10)
        else:
            raise RuntimeError(f"failed window {t0}")
        t0 = t1
        time.sleep(3)
    return out

for tag, (base, token) in SITES.items():
    print(f"[{tag}] {base}")
    tr = fetch(base, token, SINCE)
    with open(f"{SCRATCH}/mig_{tag}_treatments_28d.json", "w") as f:
        json.dump(tr, f)
    print(f"[{tag}] saved {len(tr)} treatments")
