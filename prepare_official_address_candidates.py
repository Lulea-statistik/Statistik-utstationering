"""Prepare official Swedish address point candidates from an authorized CSV export.

Input CSV: Adress;Kommun;Latitud;Longitud;Kalla
Coordinates must already be WGS84 EPSG:4326. Does NOT promote points to production.
"""
import argparse
import csv
import math
import re
from pathlib import Path

def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().casefold()

def address_parts(s):
    s = re.sub(r"\s+\d{5}\b.*$", "", norm(s)).strip()
    m = re.fullmatch(r"(.+?)\s+(\d+\s*[a-zåäö]?)", s)
    return (norm(m.group(1)), re.sub(r"\s+", "", m.group(2))) if m else None

def rows(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("official_csv", help="Authorized Swedish address export as UTF-8 semicolon CSV")
    parser.add_argument("--latest", default="data/latest.csv")
    parser.add_argument("--history", default="data/history.csv")
    parser.add_argument("--out", default="data/official_address_review.csv")
    args = parser.parse_args()
    known = set()
    for path in (args.latest, args.history):
        for r in rows(path):
            key = (norm(r.get("Kommun")), address_parts(r.get("Plats")))
            if key[0] in ("luleå", "boden") and key[1]:
                known.add((r["Plats"].strip(), r["Kommun"].strip(), key))
    index = {}
    for r in rows(args.official_csv):
        muni, parts = norm(r.get("Kommun")), address_parts(r.get("Adress"))
        if muni not in ("luleå", "boden") or not parts:
            continue
        lat, lon = float(str(r.get("Latitud", "")).replace(",", ".")), float(str(r.get("Longitud", "")).replace(",", "."))
        if not (math.isfinite(lat) and math.isfinite(lon) and 65.4 <= lat <= 66.1 and 21.1 <= lon <= 23.3):
            continue
        index.setdefault((muni, parts), []).append((lat, lon, r.get("Kalla", "")))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        w = csv.writer(handle, delimiter=";")
        w.writerow(["Adress", "Kommun", "Latitud", "Longitud", "Kalla", "Status"])
        for place, muni, key in sorted(known):
            hits = set(index.get(key, []))
            if len(hits) == 1:
                lat, lon, source = next(iter(hits))
                w.writerow([place, muni, lat, lon, source, "Entydig husnummermatch – kontrollera före manuell import"])
            elif len(hits) > 1:
                w.writerow([place, muni, "", "", "", "Flera adresspunkter – manuell granskning"])
    print("Prepared official address candidate review:", out)

if __name__ == "__main__":
    main()
