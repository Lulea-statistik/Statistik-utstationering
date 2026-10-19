"""Promote uniquely matched municipal address points only with explicit reuse approval.

Coordinates are supplied as WGS84 EPSG:4326 by fallback_lulea_municipal_addresses.py.
No changes to the public cache without a documented permission gate.
"""
import csv
import json
import math
import os
import re
from datetime import date
from pathlib import Path

ROOT=Path("data")
CANDIDATES=ROOT/"municipal_address_candidates.csv"
CACHE=ROOT/"geocoded_addresses.json"
AUDIT=ROOT/"municipal_address_promotion_audit.csv"
SOURCE="Luleå kommun ArcGIS adresskarta lager 86"
PERMISSION=ROOT/"lulea_address_reuse_approval.json"

def read_rows(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def norm(s):
    return re.sub(r"\\s+","",str(s or "").casefold())

def approved():
    if not PERMISSION.exists():
        return False
    data=json.loads(PERMISSION.read_text(encoding="utf-8"))
    return (data.get("source")==SOURCE and data.get("approved") is True
            and data.get("license_url") and data.get("scope")=="public-republication"
            and data.get("approved_by") and data.get("reviewed_at"))

def run():
    cache=json.loads(CACHE.read_text(encoding="utf-8"))
    allow=approved()
    records=[]
    seen=set()
    for row in read_rows(CANDIDATES):
        place=row.get("Adress","").strip();muni=row.get("Kommun","").strip()
        k=place+"|"+muni
        if not place or muni!="Luleå" or k in seen:
            records.append([k,"rejected","missing identity, municipality or duplicate"]);continue
        seen.add(k)
        if row.get("Kalla")!=SOURCE or "Kandidat: exakt adressmatchning" not in row.get("Status",""):
            records.append([k,"rejected","not a unique municipal exact-address candidate"]);continue
        try:
            lat=float(row["Latitud"]);lon=float(row["Longitud"])
        except (ValueError,TypeError,KeyError):
            records.append([k,"rejected","invalid coordinates"]);continue
        if not (math.isfinite(lat) and math.isfinite(lon) and 65.4<=lat<=66.1 and 21.1<=lon<=23.3):
            records.append([k,"rejected","out of bounds EPSG:4326"]);continue
        current=cache.get(k,{})
        if current.get("verified") and current.get("precision")=="exact":
            records.append([k,"unchanged","existing verified exact location"]);continue
        if not allow:
            records.append([k,"pending","public redistribution permission not approved"]);continue
        cache[k]={"lat":lat,"lon":lon,"precision":"exact","source":SOURCE,
                  "verified":True,"reviewed_at":date.today().isoformat(),
                  "source_crs":"EPSG:4326"}
        records.append([k,"promoted","unique exact matching with approved reuse"])
    with AUDIT.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f,delimiter=";");w.writerow(["AddressKey","Decision","Reason"]);w.writerows(records)
    if allow:
        CACHE.write_text(json.dumps(cache,ensure_ascii=False,indent=2,sort_keys=True)+"\\n",encoding="utf-8")
    print("Municipal source permission:", "approved" if allow else "not approved")
    print("Municipal candidates:",len(records),"promoted:",sum(r[1]=="promoted" for r in records))

if __name__=="__main__":run()
