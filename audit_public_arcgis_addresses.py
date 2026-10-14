"""Audit publicly accessible ArcGIS services for searchable address point layers.

Metadata-only: never geocodes or imports coordinates. No authentication or scraping.
"""
import csv
import json
import urllib.request
import urllib.error
from pathlib import Path

SERVICES = [
    ("Luleå", "https://kartportal.lulea.se/server/rest/services/adresskarta/MapServer"),
    ("Luleå", "https://kartportal.lulea.se/server/rest/services/adresskartan_niva2/MapServer"),
    ("Boden", "https://gisportal.boden.se/server/rest/services"),
]
OUT = Path("data/public_arcgis_address_audit.csv")
KEYWORDS = ("adress", "belägenhet", "gatu", "husnummer", "address", "street")

def get_json(url):
    req = urllib.request.Request(url + ("&" if "?" in url else "?") + "f=pjson",
                                 headers={"User-Agent": "LuleaStatistikAddressAudit/1.0 (https://github.com/Lulea-statistik/Statistik-utstationering)"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)

def main():
    records = []
    for municipality, url in SERVICES:
        try:
            service = get_json(url)
            if service.get("error"):
                raise ValueError(str(service["error"]))
            if "services" in service and "layers" not in service:
                records.append([municipality, url, "", "", "", "", "Tjänstekatalog hittad – sökbar adresspunkttjänst ej verifierad"])
                for entry in service.get("services") or []:
                    name = entry.get("name", "")
                    if not any(k in name.casefold() for k in KEYWORDS):
                        continue
                    target = url.rstrip("/") + "/" + name + "/" + entry.get("type", "MapServer")
                    try:
                        item = get_json(target)
                        for layer in item.get("layers") or []:
                            detail = get_json(target + "/" + str(layer["id"]))
                            fields = [field.get("name", "") for field in detail.get("fields") or []]
                            matches = [v for v in fields if any(k in v.casefold() for k in KEYWORDS)]
                            geom = detail.get("geometryType", "")
                            status = "Möjligt adresslager – kontrollera licens och husnummer" if geom == "esriGeometryPoint" and matches and "Query" in detail.get("capabilities", "") else "Ej verifierat som sökbart adresspunktlager"
                            records.append([municipality, target, layer["id"], layer.get("name", ""), geom, ", ".join(matches), status])
                    except (OSError, ValueError, KeyError) as err:
                        records.append([municipality, target, "", "", "", "", "Metadatafel: " + str(err)[:120]])
                continue
            layers = service.get("layers") or []
            if not layers:
                records.append([municipality, url, "", "", "", "", "Inga inspekterbara lager i metadata"])
            for layer in layers:
                name = layer.get("name", "")
                layer_url = url + "/" + str(layer["id"])
                try:
                    details = get_json(layer_url)
                    fields = [f.get("name", "") for f in details.get("fields") or []]
                    matches = [f for f in fields if any(k in f.casefold() for k in KEYWORDS)]
                    queryable = bool(details.get("capabilities", "").find("Query") >= 0)
                    geom = details.get("geometryType", "")
                    status = ("Möjligt adresslager – kontrollera licens, husnummer och frågor"
                              if queryable and matches and geom == "esriGeometryPoint"
                              else "Ej verifierat som frågebart adresspunktlager")
                    if matches or any(k in name.casefold() for k in KEYWORDS):
                        records.append([municipality, url, layer["id"], name, geom,
                                        ", ".join(matches), status])
                except (OSError, ValueError) as err:
                    records.append([municipality, url, layer["id"], name, "", "", "Metadatafel: " + str(err)[:120]])
        except (OSError, ValueError) as err:
            records.append([municipality, url, "", "", "", "", "Tjänst ej tillgänglig: " + str(err)[:120]])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as h:
        writer = csv.writer(h, delimiter=";")
        writer.writerow(["Kommun", "Tjänst", "LagerID", "Lagernamn", "Geometri", "Adressfalt", "Bedömning"])
        writer.writerows(records)
    print("ArcGIS public service audit:", len(records), "results; see", OUT)

if __name__ == "__main__":
    main()
