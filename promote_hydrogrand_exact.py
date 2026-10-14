"""Import unambiguous postal-address match for Hydrogränd 2 from Boden locator."""
import csv
import json
import math
import re
from pathlib import Path

ROOT = Path("data")
CACHE = ROOT / "geocoded_addresses.json"
CANDIDATES = ROOT / "remaining_address_variants.csv"
KEY = "Hydrogränd 2 96143 Boden|Boden"
def normalized(s):
    return re.sub(r"[^a-zåäö0-9]", "", s.casefold())
def main():
    with CANDIDATES.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter=";"))
    matches = []
    for row in rows:
        if row.get("Originaladress") != KEY.split("|")[0] or row.get("Kommun") != "Boden":
            continue
        candidate = (row.get("API_matchning") or "").split(",")
        if len(candidate) < 2 or normalized(candidate[0]) != normalized("Hydrogränd 2"):
            continue
        if normalized(candidate[1]) != normalized("96143 Boden"):
            continue
        try:
            lat, lon = float(row["Latitud"]), float(row["Longitud"])
        except (ValueError, TypeError, KeyError):
            continue
        if math.isfinite(lat) and math.isfinite(lon) and 65.4 <= lat <= 66.45 and 21.0 <= lon <= 23.3:
            matches.append((lat, lon))
    if len(set(matches)) != 1 or not matches:
        print("No unique exact Hydrogränd 2 match; do not import")
        return
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    existing = cache.get(KEY) or {}
    if existing.get("verified") or existing.get("precision") == "exact":
        print("Existing verified/exact point retained")
        return
    lat, lon = matches[0]
    cache[KEY] = {
        "lat": lat, "lon": lon, "precision": "exact",
        "matched_name": "Hydrogränd 2, 961 43 Boden",
        "source": "Bodens kommun, GaidaLocator_Address/GeocodeServer",
        "source_url": "https://gisportal.boden.se/server/rest/services/Gaida/GaidaLocator_Address/GeocodeServer",
        "verification": "municipal_address_match"
    }
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("Accepted Hydrogränd 2 exact municipal address",lat,lon)
if __name__ == "__main__":
    main()
