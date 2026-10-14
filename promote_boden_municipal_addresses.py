"""Promote exact Boden address candidates to the public coordinate cache.

Only municipality, street and house-number matches from the public municipal
locator are accepted. Manual positions and existing exact matches take priority.
"""
import csv
import json
import math
import re
from pathlib import Path

ROOT=Path("data")
CANDIDATES=ROOT/"boden_municipal_address_candidates.csv"
CACHE=ROOT/"geocoded_addresses.json"
SOURCE="Bodens kommun, GaidaLocator_Address/GeocodeServer"
SOURCE_URL="https://gisportal.boden.se/server/rest/services/Gaida/GaidaLocator_Address/GeocodeServer"

def norm(s):
    return re.sub(r"[^a-zåäö0-9]","",str(s or "").casefold())
def street_house(place):
    place=re.sub(r"\s+\d{5}\b.*$","",str(place or "")).strip()
    place=re.sub(r"\s+Boden$","",place,flags=re.IGNORECASE).strip()
    return norm(place)
def main():
    with CACHE.open(encoding="utf-8") as f:
        cache=json.load(f)
    with CANDIDATES.open(encoding="utf-8-sig",newline="") as f:
        candidates=list(csv.DictReader(f,delimiter=";"))
    changed=0
    for row in candidates:
        place=row["Adress"].strip()
        key=place+"|Boden"
        existing=cache.get(key) or {}
        if existing.get("verified") or existing.get("precision")=="exact":
            continue
        if not row.get("Status","").startswith("Entydig adresskandidat"):
            continue
        matched=row.get("Matchad_adress","").split(",")[0]
        if not matched or street_house(place)!=norm(matched):
            continue
        try:
            score=float(row["Score"])
            lat=float(row["Latitud"])
            lon=float(row["Longitud"])
        except (ValueError,KeyError):
            continue
        if not (score>=70 and math.isfinite(lat) and math.isfinite(lon)
                and 65.4<=lat<=66.45 and 21.0<=lon<=23.3):
            continue
        cache[key]={"lat":lat,"lon":lon,"precision":"exact","source":SOURCE,
                    "source_url":SOURCE_URL,"matched_name":row["Matchad_adress"],
                    "match_score":score,"verification":"municipal_address_match"}
        changed+=1
        print("Boden municipal address accepted:",key)
    CACHE.write_text(json.dumps(cache,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(f"Accepted {changed} municipal address coordinates; cached {len(cache)}")
if __name__=="__main__":
    main()
