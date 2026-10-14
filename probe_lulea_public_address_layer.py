"""Probe one public Lulea ArcGIS address layer with targeted queries.

Review-only: no writes to geocoding cache. Public service, low query volume.
"""
import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://kartportal.lulea.se/server/rest/services/adresskarta/MapServer/86"
OUT = Path("data/public_arcgis_address_probe.csv")
SAMPLES = ["Svartövägen 22", "Siktgatan 7", "Björnmossevägen 17"]
def fetch(url, params):
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(url + "?" + query, headers={"User-Agent": "LuleaStatistikArcGISProbe/1.0 (https://github.com/Lulea-statistik/Statistik-utstationering)"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)

def main():
    report = []
    try:
        meta = fetch(BASE, {"f": "json"})
        fields = [f.get("name", "") for f in (meta.get("fields") or [])]
        address_field = next((f for f in fields if f.casefold() == "adress"), None)
        if not address_field or "Query" not in (meta.get("capabilities") or ""):
            report.append(["", "", "", "", "", "Ingen verifierad frågefunktion eller ADRESS-fält"])
        else:
            for address in SAMPLES:
                # Exact equality only, with properly escaped apostrophes and no broad bulk query.
                sql = address_field + " = '" + address.replace("'", "''") + "'"
                try:
                    result = fetch(BASE + "/query", {"where": sql, "outFields": address_field,
                          "returnGeometry": "true", "outSR": "4326", "f": "json", "resultRecordCount": "5"})
                    if result.get("error"):
                        report.append([address, "", "", "", "", "API-fel: " + str(result["error"])[:160]])
                        continue
                    features = result.get("features") or []
                    if len(features) != 1:
                        report.append([address, "", "", "", str(len(features)), "Ingen entydig exakt match"])
                        continue
                    feature = features[0]
                    geom = feature.get("geometry") or {}
                    if "x" not in geom or "y" not in geom:
                        report.append([address, "", "", "", "1", "Träff utan punktgeometri"])
                        continue
                    label = str((feature.get("attributes") or {}).get(address_field, ""))
                    report.append([address, label, geom["y"], geom["x"], "1", "Kandidat – verifiera licens och adressfältsformat; ej importerad"])
                except (OSError, ValueError) as exc:
                    report.append([address, "", "", "", "", "Frågefel: " + str(exc)[:160]])
    except (OSError, ValueError) as exc:
        report.append(["", "", "", "", "", "Metadatafel: " + str(exc)[:160]])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Sokt_adress", "Matchad_adress", "Latitud", "Longitud", "Antal_traffar", "Bedömning"])
        writer.writerows(report)
    print("Address test report:", OUT, "rows:", len(report))
if __name__ == "__main__":
    main()
