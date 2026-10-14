"""Review-only sequential address-variant search for three unresolved locations."""
import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT=Path("data/remaining_address_variants.csv")
LULEA="https://kartportal.lulea.se/server/rest/services/adresskarta/MapServer/86/query"
BODEN="https://gisportal.boden.se/server/rest/services/Gaida/GaidaLocator_Address/GeocodeServer/findAddressCandidates"
TESTS=[
 ("Viktoriavägen 1 97437 Luleå","Luleå","VIKTORIAVÄGEN 1"),
 ("Viktoriavägen 1 97437 Luleå","Luleå","viktoriavägen 1"),
 ("Viktoriavägen 1 97437 Luleå","Luleå","VICTORIAVÄGEN 1"),
 ("Viktoriavägen 1 97437 Luleå","Luleå","VIKTORIAVÄGEN %"),
 ("Flarkenvägen 15 Boden","Boden","Flarkenvägen 15"),
 ("Flarkenvägen 15 Boden","Boden","Flarkenvägen 15, 961 92 Boden"),
 ("Flarkenvägen 15 Boden","Boden","Flarken 15 Boden"),
 ("Flarkenvägen 15 Boden","Boden","Flarkenvägen Boden"),
 ("Hydrogränd 2 96143 Boden","Boden","Hydrogränd 2"),
 ("Hydrogränd 2 96143 Boden","Boden","Hydrogränd 2, 961 43 Boden"),
 ("Hydrogränd 2 96143 Boden","Boden","Hydrogränd Boden"),
 ("Hydrogränd 2 96143 Boden","Boden","Hydrogränd 1 Boden"),
 ("Hydrogränd 2 96143 Boden","Boden","Hydrogränd 3 Boden"),
]
def request(url,params):
    req=urllib.request.Request(url+"?"+urllib.parse.urlencode(params),
        headers={"User-Agent":"LuleaStatistikAddressVariants/1.0 (https://github.com/Lulea-statistik/Statistik-utstationering)"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req,timeout=25) as response:
                return json.load(response), ""
        except Exception as exc:
            if attempt:
                return {},str(exc)[:160]
            time.sleep(2)
    return {},"No response"
def main():
    rows=[]
    for original,muni,variant in TESTS:
        if muni=="Luleå":
            condition="ADRESS LIKE '"+variant.replace("'","''")+"'" if "%" in variant else "ADRESS = '"+variant.replace("'","''")+"'"
            payload,error=request(LULEA,{"f":"json","where":condition,
                "outFields":"ADRESS","returnGeometry":"true","outSR":"4326","resultRecordCount":"30"})
            features=payload.get("features") or []
            matches=[((f.get("attributes") or {}).get("ADRESS",""),f.get("geometry") or {}) for f in features]
        else:
            payload,error=request(BODEN,{"f":"json","SingleLine":variant,
                "outSR":"4326","maxLocations":5})
            matches=[(f.get("address",""),f.get("location") or {}) for f in payload.get("candidates") or []]
        if payload.get("error"):
            error=str(payload["error"])[:160]
        if not matches:
            rows.append([original,muni,variant,"","","","",error or "Ingen träff"])
        for name,geometry in matches:
            latitude=geometry.get("y","")
            longitude=geometry.get("x","")
            status="GRANSKA – endast exakt husnummer får markeras som exakt adress" if not error else error
            rows.append([original,muni,variant,name,latitude,longitude,"Ej importerad",status])
        time.sleep(1.25)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open("w",encoding="utf-8-sig",newline="") as file:
        writer=csv.writer(file,delimiter=";")
        writer.writerow(["Originaladress","Kommun","Sokvariant","API_matchning","Latitud","Longitud","Import","Bedömning"])
        writer.writerows(rows)
    print("Variant diagnostics:",len(rows),"records and",sum(bool(x[3]) for x in rows),"API matches; none imported")
if __name__=="__main__":
    main()
