import urllib.request, json, time, re, sys
BASE="https://<REDACTED>"; TOKEN="<REDACTED>"  # NS base+token redacted for public repo
def get(url, tries=6):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            sys.stderr.write(f"retry {i} {e}\n"); time.sleep(3+3*i)
    raise RuntimeError("failed "+url)

days=[f"2026-06-{d:02d}" for d in range(27,31)]+[f"2026-07-{d:02d}" for d in range(1,8)]
# devicestatus
ds_rows=[]
for i in range(len(days)-1):
    a,b=days[i],days[i+1]
    url=f"{BASE}/api/v1/devicestatus.json?token={TOKEN}&count=20000&find[created_at][$gte]={a}&find[created_at][$lt]={b}"
    recs=get(url)
    for rec in recs:
        s=rec.get('openaps',{}).get('suggested',{})
        if not s: continue
        ce=" ".join(s.get('consoleError',[])) if isinstance(s.get('consoleError'),list) else ""
        reason=s.get('reason','')
        blob=reason+" "+ce
        m=re.search(r'steps15m=(\d+)', blob)
        steps15=int(m.group(1)) if m else None
        if steps15 is None:
            m=re.search(r'Steps:.*?15m=(\d+)', blob)
            steps15=int(m.group(1)) if m else None
        ds_rows.append(dict(
            date=s.get('timestamp') or rec.get('created_at'),
            ms=rec.get('date'),
            hrAvg15=s.get('hrBpmAvg15m'),
            hrLatest=s.get('hrBpmLatest'),
            hrCount15=s.get('hrReadingsCount15m'),
            sleep=s.get('sleepState'),
            hrSrc=s.get('hrSource_resolved'),
            steps15=steps15,
            bg=s.get('bg'),
        ))
    sys.stderr.write(f"ds {a}: {len(recs)} recs, total {len(ds_rows)}\n")
json.dump(ds_rows, open('hr_bg_devicestatus.json','w'))
print("devicestatus rows:", len(ds_rows))

# entries (sgv)
ent=[]
for i in range(len(days)-1):
    a,b=days[i],days[i+1]
    url=f"{BASE}/api/v1/entries/sgv.json?token={TOKEN}&count=20000&find[dateString][$gte]={a}&find[dateString][$lt]={b}"
    recs=get(url)
    for r in recs:
        if r.get('sgv') is None: continue
        ent.append(dict(ms=r.get('date'), sgv=r.get('sgv'), ds=r.get('dateString')))
    sys.stderr.write(f"ent {a}: {len(recs)} recs, total {len(ent)}\n")
json.dump(ent, open('hr_bg_entries.json','w'))
print("entries rows:", len(ent))
