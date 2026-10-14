"""Review-only fallback: seek exact Lulea municipal address points after OSM.

Never updates geocoded_addresses.json; results need reuse-rights review.
"""
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("data")
BASE = "https://kartportal.lulea.se/server/rest/services/adresskarta/MapServer/86/query"
OUT = ROOT / "municipal_address_candidates.csv"
def read_csv(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))
def clean_address(s):
    s = re.sub(r"\s+\d{5}\b.*$", "", str(s or "")).strip()
    return re.sub(r"\s+", " ", s).strip()
def exact_key(s):
    return re.sub(r"\s+", "", clean_address(s).casefold())
def fetch(address):
    sql = "ADRESS = '" + address.upper().replace("'", "''") + "'"
    params = urllib.parse.urlencode({"f":"json", "where":sql, "outFields":"ADRESS",
                                      "returnGeometry":"true","outSR":"4326","resultRecordCount":"5"})
    req = urllib.request.Request(BASE + "?" + params,headers={
        "User-Agent":"LuleaStatistikMunicipalFallback/1.0 (https://github.com/Lulea-statistik/Statistik-utstationering)"})
    with urllib.request.urlopen(req, timeout=25) as f:
        return json.load(f)
def main():
    cache = json.loads((ROOT/"geocoded_addresses.json").read_text(encoding="utf-8"))
    addresses = {(r["Plats"].strip(),r["Kommun"].strip())
                 for p in ("latest.csv","history.csv") for r in read_csv(ROOT/p)
                 if r.get("Plats") and r.get("Kommun") and r["Kommun"].strip()=="Luleå"}
    selected = []
    for place, muni in sorted(addresses):
        loc = cache.get(place+"|"+muni) or {}
        if loc.get("verified") and loc.get("precision")=="exact":
            continue
        if loc.get("precision")=="exact":
            continue
        selected.append((place,muni,loc.get("precision","missing")))
    records=[]
    for place,muni,current in selected:
        address=clean_address(place)
        if not re.search(r"\b\d+\s*[a-zA-ZÅÄÖåäö]?\s*$",address):
            records.append([place,muni,current,"","","","Husnummer saknas i källadress"])
            continue
        try:
            result=fetch(address)
            if result.get("error"):
                raise ValueError(str(result["error"])[:150])
            features=result.get("features") or []
            matches=[f for f in features if exact_key((f.get("attributes") or {}).get("ADRESS"))==exact_key(address)]
            if len(features)==1 and len(matches)==1:
                geom=matches[0].get("geometry") or {}
                lat,lon=geom.get("y"),geom.get("x")
                if isinstance(lat,(int,float)) and isinstance(lon,(int,float)) and 65.4<=lat<=66.1 and 21.1<=lon<=23.3:
                    records.append([place,muni,current,lat,lon,"Luleå kommun ArcGIS adresskarta lager 86","Kandidat: exakt adressmatchning, publiceringsrätt ej verifierad"])
                else:
                    records.append([place,muni,current,"","","","Träff utan giltig WGS84-punkt"])
            else:
                records.append([place,muni,current,"","","",f"Ingen entydig exakt adressmatchning ({len(features)} träffar)"])
        except (OSError,ValueError,TypeError) as err:
            records.append([place,muni,current,"","","","Tjänstfel: "+str(err)[:120]])
        time.sleep(0.4)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.writer(f,delimiter=";")
        writer.writerow(["Adress","Kommun","Nuvarande_precision","Latitud","Longitud","Kalla","Status"])
        writer.writerows(records)
    print("Municipal fallback review:",len(records),"addresses;",sum(bool(r[3]) for r in records),"candidates")
if __name__=="__main__":
    main()
