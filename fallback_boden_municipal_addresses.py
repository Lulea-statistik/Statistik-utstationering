"""Review exact Bodens municipal address locator candidates after OSM geocoding.

The resulting CSV is a review artifact; it does not modify the public map.
"""
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("data")
URL = "https://gisportal.boden.se/server/rest/services/Gaida/GaidaLocator_Address/GeocodeServer"
OUT = ROOT / "boden_municipal_address_candidates.csv"

def load_rows(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))

def clean(s):
    s = re.sub(r"\s+\d{5}\b.*$", "", str(s or "")).strip()
    return re.sub(r"\s+Boden$", "", s, flags=re.IGNORECASE).strip()

def normalized(s):
    return re.sub(r"[^a-zåäö0-9]", "", clean(s).casefold())

def fetch(address):
    params = urllib.parse.urlencode({"SingleLine": address + ", Boden",
        "f":"json", "outSR":"4326","maxLocations":5})
    req = urllib.request.Request(URL + "/findAddressCandidates?" + params,
        headers={"User-Agent":"LuleaStatistikBodenFallback/1.0 (https://github.com/Lulea-statistik/Statistik-utstationering)"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)

def main():
    cache = json.loads((ROOT/"geocoded_addresses.json").read_text(encoding="utf-8"))
    unique = sorted({r["Plats"].strip() for p in ("latest.csv", "history.csv")
        for r in load_rows(ROOT / p)
        if r.get("Plats") and r.get("Kommun","").strip()=="Boden"})
    rows=[]
    for place in unique:
        existing = cache.get(place+"|Boden") or {}
        if existing.get("precision")=="exact" or existing.get("verified") and existing.get("precision")=="exact":
            continue
        target=clean(place)
        if not re.search(r"\b\d+\s*[a-zåäö]?\s*$",target,re.IGNORECASE):
            rows.append([place,"", "", "", "", "Husnummer saknas"]); continue
        try:
            result=fetch(target)
            if result.get("error"):
                raise ValueError(str(result["error"])[:120])
            candidates=result.get("candidates") or []
            matching=[]
            for candidate in candidates:
                matched=clean((candidate.get("address") or "").split(",")[0])
                score=float(candidate.get("score") or 0)
                coords=candidate.get("location") or {}
                lat,lon=coords.get("y"),coords.get("x")
                if normalized(matched)==normalized(target) and score>=70 and isinstance(lat,(int,float)) and isinstance(lon,(int,float)) and 65.4<=lat<=66.45 and 21.0<=lon<=23.3:
                    matching.append((candidate,lat,lon))
            if len(matching)==1:
                candidate,lat,lon=matching[0]
                rows.append([place,candidate.get("address",""),candidate.get("score",""),lat,lon,
                    "Entydig adresskandidat – kontrollera geografisk precision och återanvändningsvillkor"])
            else:
                rows.append([place,"", "", "", "", f"Ingen entydig match ({len(candidates)} API-kandidater)"])
        except (OSError,ValueError,TypeError) as error:
            rows.append([place,"","","","","API-fel: "+str(error)[:120]])
        time.sleep(0.35)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer=csv.writer(f,delimiter=";")
        writer.writerow(["Adress","Matchad_adress","Score","Latitud","Longitud","Status"])
        writer.writerows(rows)
    print("Boden review",len(rows),"addresses;",sum(bool(r[3]) for r in rows),"coordinate candidates")
if __name__=="__main__":
    main()
