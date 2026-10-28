#!/usr/bin/env python3
"""Fetch 14d of devicestatus + entries from the developer's NS, chunked <=7d, 15s backoff. Cache to scratchpad."""
import json, os, time, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = "https://<REDACTED>"  # NS base URL redacted for public repo
TOKEN = "<REDACTED>"  # NS token redacted for public repo
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ns_14d.json")
DAY_MS = 86_400_000
CHUNK_DAYS = 7
WINDOW_DAYS = 14


def _get(path, params, attempts=5, backoff=15):
    p = dict(params); p["token"] = TOKEN
    url = f"{BASE}/api/v1/{path}.json?" + urllib.parse.urlencode(p, safe="[]$<>")
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  attempt {i+1} failed: {e}", flush=True)
            if i < attempts - 1:
                time.sleep(backoff)
    raise last


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def main():
    now = int(time.time() * 1000)
    start = now - WINDOW_DAYS * DAY_MS
    ds, ent, we = [], [], now
    while we > start:
        ws = max(start, we - CHUNK_DAYS * DAY_MS)
        print(f"chunk {_iso(ws)} .. {_iso(we)}", flush=True)
        ds += _get("devicestatus", {"count": 200000, "find[created_at][$gte]": _iso(ws), "find[created_at][$lte]": _iso(we)})
        time.sleep(2)
        ent += _get("entries", {"count": 200000, "find[date][$gte]": int(ws), "find[date][$lte]": int(we)})
        time.sleep(2)
        we = ws - 1
    print(f"devicestatus: {len(ds)}  entries: {len(ent)}", flush=True)

    # keep only what we need
    sgv = sorted({(int(e["date"]), float(e["sgv"])) for e in ent if e.get("sgv") and e.get("date")})
    preds = []
    seen = set()
    for d in ds:
        s = (d.get("openaps") or {}).get("suggested") or {}
        ca = d.get("created_at", "")
        if not s or not ca or ca in seen:
            continue
        seen.add(ca)
        try:
            ts = int(datetime.strptime(ca[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)
        except ValueError:
            continue
        pb = s.get("predBGs") or {}
        preds.append({
            "ts": ts,
            "bg": s.get("bg"),
            "eventualBG": s.get("eventualBG"),
            "IOB": pb.get("IOB"), "ZT": pb.get("ZT"), "UAM": pb.get("UAM"),
            "COB": pb.get("COB"), "aCOB": pb.get("aCOB"),
        })
    preds.sort(key=lambda p: p["ts"])
    with open(OUT, "w") as f:
        json.dump({"sgv": sgv, "preds": preds}, f)
    print(f"wrote {OUT}: {len(preds)} suggested records, {len(sgv)} sgv", flush=True)


if __name__ == "__main__":
    main()
