"""Promote only exact Rödkallen 66 municipal match; never nearby numbers."""
import csv
import json
from pathlib import Path

ROOT=Path("data")
probe=ROOT/"rodkallen_address_probe.csv"
cache_path=ROOT/"geocoded_addresses.json"
key="Rödkallen 66 97592 Luleå|Luleå"
with probe.open(encoding="utf-8-sig",newline="") as f:
    rows=list(csv.DictReader(f,delimiter=";"))
valid=[]
for row in rows:
    if row["Sokt_adress"].casefold()!="rödkallen 66" or row["Matchad_adress"].casefold()!="rödkallen 66":
        continue
    try:
        lat,lon=float(row["Latitud"]),float(row["Longitud"])
    except (ValueError,TypeError):
        continue
    if 65.2<=lat<=66.45 and 21.0<=lon<=23.3:
        valid.append((lat,lon))
cache=json.loads(cache_path.read_text(encoding="utf-8"))
existing=cache.get(key,{})
if valid and len(set(valid))==1 and not existing.get("verified") and existing.get("precision")!="exact":
    lat,lon=valid[0]
    cache[key]={"lat":lat,"lon":lon,"precision":"exact",
        "source":"Luleå kommun ArcGIS adresskarta lager 86",
        "source_url":"https://kartportal.lulea.se/server/rest/services/adresskarta/MapServer/86",
        "matched_name":"RÖDKALLEN 66","verification":"municipal_address_match"}
    cache_path.write_text(json.dumps(cache,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("Accepted exact Rödkallen 66:",lat,lon)
else:
    print("No unambiguous exact Rödkallen coordinate to promote; keeping current cache")
