"""Investigate Rödkallen 66: case variants first, then addresses 36–96.

Review-only: neighboring house numbers are not the requested address.
"""
import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENDPOINT="https://kartportal.lulea.se/server/rest/services/adresskarta/MapServer/86/query"
OUTPUT=Path("data/rodkallen_address_probe.csv")
def fetch(where,limit=100):
    params=urllib.parse.urlencode({"f":"json","where":where,"outFields":"ADRESS",
        "returnGeometry":"true","outSR":"4326","resultRecordCount":limit})
    request=urllib.request.Request(ENDPOINT+"?"+params,headers={
        "User-Agent":"LuleaStatistikRödkallenProbe/1.0 (https://github.com/Lulea-statistik/Statistik-utstationering)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request,timeout=30) as result:
                payload=json.load(result)
            if payload.get("error"):
                raise ValueError(str(payload["error"]))
            return payload.get("features") or []
        except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,ValueError) as exc:
            if attempt==2:
                print("ArcGIS Rödkallen query failed, preserving the review queue:",where,str(exc))
                return None
            time.sleep(1.5*(attempt+1))
    return None
def checked(feature):
    geometry=feature.get("geometry") or {}
    lat,lon=geometry.get("y"),geometry.get("x")
    return (isinstance(lat,(int,float)) and isinstance(lon,(int,float))
        and 65.4<=lat<=66.45 and 21.0<=lon<=23.3)
def main():
    rows=[]
    exact_match=False
    for address in ("RÖDKALLEN 66","rödkallen 66"):
        for feature in (fetch("ADRESS = '"+address+"'") or []):
            name=str((feature.get("attributes") or {}).get("ADRESS",""))
            geo=feature.get("geometry") or {}
            exact=name.casefold()==address.casefold() and checked(feature)
            exact_match=exact_match or exact
            rows.append([address,name,geo.get("y",""),geo.get("x",""),
                "Exakt adress med giltig WGS84-punkt" if exact else "Exakt textsökning men koordinat behöver granskas"])
    # One bounded API query covers every requested neighboring number. Avoid 60 calls.
    candidates=[]
    for feature in (fetch("UPPER(ADRESS) LIKE 'RÖDKALLEN %'",100) or []):
        name=str((feature.get("attributes") or {}).get("ADRESS",""))
        parts=name.upper().split()
        if len(parts)!=2 or parts[0]!="RÖDKALLEN" or not parts[1].isdigit():
            continue
        number=int(parts[1])
        if not 36<=number<=96 or number==66:
            continue
        candidates.append((abs(number-66),number,feature,name))
    for distance,number,feature,name in sorted(candidates):
        geo=feature.get("geometry") or {}
        rows.append(["RÖDKALLEN "+str(number),name,geo.get("y",""),geo.get("x",""),
            "Närliggande annat husnummer – endast ungefärligt geografiskt referensläge"
            if checked(feature) else "Annat husnummer och ogiltig/saknad koordinat"])
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    with OUTPUT.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.writer(f,delimiter=";")
        writer.writerow(["Sokt_adress","Matchad_adress","Latitud","Longitud","Bedömning"])
        writer.writerows(rows)
    print("Rödkallen: exact valid coordinate:",exact_match,"neighbor candidates:",len(candidates))
    print("No neighbor automatically assigned to Rödkallen 66")
if __name__=="__main__":
    main()
