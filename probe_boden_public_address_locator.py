"""Probe Bodens public address locator; review-only, never update map coordinates."""
import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://gisportal.boden.se/server/rest/services/Gaida/GaidaLocator_Address/GeocodeServer"
SAMPLES = ["Flarkenvägen 15 Boden", "Lakaträsk 404 Boden", "Övre Buddbyn 141 Boden",
           "Solskensvägen 25 Boden", "Hydrogränd 2 Boden", "Bullerleden 5 Boden"]
OUT = Path("data/boden_public_address_probe.csv")
def get(url, params):
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent":"LuleaStatistikBodenAddressProbe/1.0 (https://github.com/Lulea-statistik/Statistik-utstationering)"})
    with urllib.request.urlopen(req, timeout=25) as response:
        value = json.load(response)
    if value.get("error"):
        raise ValueError(str(value["error"])[:170])
    return value
def main():
    records = []
    try:
        metadata = get(BASE, {"f":"json"})
        locator_fields = [f.get("name","") for f in metadata.get("singleLineAddressField", {}).get("name", [])] if isinstance(metadata.get("singleLineAddressField",{}).get("name"),list) else []
        single = metadata.get("singleLineAddressField") or {}
        field = single.get("name") or "SingleLine"
        for addr in SAMPLES:
            try:
                result = get(BASE + "/findAddressCandidates", {
                    "f":"json", field:addr,"outSR":"4326","maxLocations":5})
                candidates = result.get("candidates") or []
                if not candidates:
                    records.append([addr,"","","","","Ingen kandidat"])
                    continue
                first=candidates[0]
                p=first.get("location") or {}
                records.append([addr,str(first.get("address","")),
                                str(first.get("score","")),str(p.get("y","")),str(p.get("x","")),
                                "Granska adress, husnummer, score och publiceringsrätt; ej importerad"
                                if len(candidates)==1 else f"{len(candidates)} kandidater – granska manuellt"])
            except (OSError,ValueError,TypeError) as exc:
                records.append([addr,"","","","","Sökfel: "+str(exc)[:150]])
    except (OSError,ValueError,TypeError) as exc:
        records.append(["","","","","","Metadatafel: "+str(exc)[:160]])
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open("w",encoding="utf-8-sig",newline="") as handle:
        w=csv.writer(handle,delimiter=";")
        w.writerow(["Sokt_adress","Matchad_adress","Score","Latitud","Longitud","Status"])
        w.writerows(records)
    print("Boden address locator probe:",len(records),"test rows")
if __name__ == "__main__":
    main()
