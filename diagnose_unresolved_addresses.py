"""Diagnose unresolved addresses against public municipal APIs, without publishing guesses."""
import csv
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT=Path("data")
OUT=ROOT/"unresolved_address_diagnostics.csv"
LULEA="https://kartportal.lulea.se/server/rest/services/adresskarta/MapServer/86/query"
BODEN="https://gisportal.boden.se/server/rest/services/Gaida/GaidaLocator_Address/GeocodeServer/findAddressCandidates"

def query(url,params):
    req=urllib.request.Request(url+"?"+urllib.parse.urlencode(params),headers={
        "User-Agent":"LuleaStatistikAddressDiagnostics/1.0 (https://github.com/Lulea-statistik/Statistik-utstationering)"})
    with urllib.request.urlopen(req,timeout=25) as r:
        return json.load(r)

def clean(address):
    return re.sub(r"\s+\d{5}\b.*$","",address).strip()

def main():
    with (ROOT/"geocoding_review.csv").open(encoding="utf-8-sig",newline="") as h:
        pending=list(csv.DictReader(h,delimiter=";"))
    results=[]
    for item in pending:
        place,muni=item["Adress"],item["Kommun"]
        base=clean(place)
        if muni=="Boden":
            base=re.sub(r"\s+Boden$","",base,flags=re.I).strip()
            try:
                response=query(BODEN,{"SingleLine":base+", Boden","f":"json","outSR":4326,"maxLocations":5})
                candidates=response.get("candidates") or []
                names=" | ".join(str(c.get("address","")) for c in candidates[:5])
                status="Inga förslag från adresslocator" if not candidates else "Endast granskningsförslag; ingen automatisk import"
                results.append([place,muni,"Boden GeocodeServer",len(candidates),names,status])
            except (OSError,ValueError,TypeError) as e:
                results.append([place,muni,"Boden GeocodeServer","","","Fel: "+str(e)[:120]])
        elif muni=="Luleå":
            street=re.sub(r"\s+\d+[a-zA-ZÅÄÖåäö]?\s*$","",base).strip()
            try:
                result=query(LULEA,{"f":"json","where":"UPPER(ADRESS) LIKE '"+street.upper().replace("'","''")+"%'",
                    "returnGeometry":"false","outFields":"ADRESS","resultRecordCount":10})
                if result.get("error"):
                    raise ValueError(str(result["error"])[:120])
                features=result.get("features") or []
                names=" | ".join(str((f.get("attributes") or {}).get("ADRESS","")) for f in features)
                status="Inga gatunamnsförslag" if not features else "Kontrollera om adressnamn eller husnummer avviker"
                results.append([place,muni,"Luleå adresskarta/86",len(features),names,status])
            except (OSError,ValueError,TypeError) as e:
                results.append([place,muni,"Luleå adresskarta/86","","","Fel: "+str(e)[:120]])
    with OUT.open("w",encoding="utf-8-sig",newline="") as h:
        writer=csv.writer(h,delimiter=";")
        writer.writerow(["Adress","Kommun","Kalla","Antal_forslag","Forslag","Bedömning"])
        writer.writerows(results)
    print("Unresolved diagnostics:",len(results),"addresses")
if __name__=="__main__":
    main()
