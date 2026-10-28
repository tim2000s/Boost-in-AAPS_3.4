#!/usr/bin/env python3
"""Fetch last-14d (and 28d) NS treatments for tags A and B -> scratchpad JSON."""
import json, sys, time, urllib.request, urllib.error, os

SCRATCH = os.path.dirname(os.path.abspath(__file__))
SITES = json.load(open(os.path.expanduser("~/.config/boost_backtest/sites.json")))["sites"]
NOW = time.time()

def fetch(url, retries=1):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            code = getattr(e, "code", None)
            print(f"  attempt {attempt}: {e} (code={code})", file=sys.stderr)
            if attempt < retries:
                time.sleep(5)
            else:
                raise

for tag in ("A", "B"):
    site = next(s for s in SITES if s["tag"] == tag)
    base, token = site["base"], site["token"]
    since_iso = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(NOW - 28 * 86400))
    out = []
    count = 1000
    url = (f"{base}/api/v1/treatments.json?count={count}"
           f"&find[created_at][$gte]={since_iso}&token={token}")
    batch = fetch(url)
    out.extend(batch)
    # page older if we hit the cap
    while len(batch) == count:
        oldest = min(b["created_at"] for b in batch if b.get("created_at"))
        url = (f"{base}/api/v1/treatments.json?count={count}"
               f"&find[created_at][$gte]={since_iso}&find[created_at][$lt]={oldest}&token={token}")
        batch = fetch(url)
        out.extend(batch)
        if len(out) > 40000:
            break
    path = os.path.join(SCRATCH, f"mig_{tag}_treatments28d.json")
    json.dump(out, open(path, "w"))
    # quick summary
    n_ins = sum(1 for t in out if t.get("insulin"))
    bad = [t.get("insulin") for t in out if t.get("insulin") is not None and not isinstance(t.get("insulin"), (int, float))]
    print(f"{tag}: {len(out)} treatments, {n_ins} with insulin, non-numeric insulin fields: {len(bad)} {bad[:3]}")
