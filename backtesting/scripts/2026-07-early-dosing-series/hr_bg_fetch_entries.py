import urllib.request, json, time, sys, datetime
BASE="https://<REDACTED>"; TOKEN="<REDACTED>"  # NS base+token redacted for public repo
def get(url, tries=6):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            sys.stderr.write(f"retry {i} {e}\n"); time.sleep(3+3*i)
    raise RuntimeError("failed")
def ms(y,m,d): return int(datetime.datetime(y,m,d,tzinfo=datetime.timezone.utc).timestamp()*1000)
bounds=[ms(2026,6,d) for d in range(27,31)]+[ms(2026,7,d) for d in range(1,8)]
ent=[]
for i in range(len(bounds)-1):
    a,b=bounds[i],bounds[i+1]
    url=f"{BASE}/api/v1/entries/sgv.json?token={TOKEN}&count=50000&find[date][$gte]={a}&find[date][$lt]={b}"
    recs=get(url)
    for r in recs:
        if r.get('sgv') is None: continue
        ent.append(dict(ms=r.get('date'), sgv=r.get('sgv')))
    sys.stderr.write(f"ent chunk {i}: {len(recs)}\n")
json.dump(ent, open('hr_bg_entries.json','w'))
print("entries rows:", len(ent))
