"""Geokoda nya adresser utan att gissa positioner. WGS84 (EPSG:4326)."""
import csv
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("data")
CACHE = ROOT / "geocoded_addresses.json"
LATEST = ROOT / "latest.csv"
HISTORY = ROOT / "history.csv"

def read_rows(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))

def normalize(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def fetch(place, municipality):
    query = f"{place}, {municipality}, Sweden"
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": query, "format": "json", "limit": "3", "countrycodes": "se",
        "addressdetails": "1"
    })
    req = urllib.request.Request(url, headers={
        "User-Agent": "LuleaStatistikUtstationering/1.0 (https://github.com/Lulea-statistik/Statistik-utstationering)",
        "Accept": "application/json"
    })
    with urllib.request.urlopen(req, timeout=25) as reply:
        matches = json.load(reply)
    for match in matches:
        display = normalize(match.get("display_name")).lower()
        address = match.get("address") or {}
        full = " ".join(str(x) for x in address.values()).lower() + " " + display
        if municipality.lower() not in full:
            continue
        # Do not use municipality or street centroid as if it were an exact address.
        if match.get("type") in ("administrative", "city", "town", "village", "residential"):
            continue
        if not (address.get("house_number") or match.get("type") in ("building", "house")):
            continue
        return {"lat": float(match["lat"]), "lon": float(match["lon"]), "source": "OpenStreetMap Nominatim"}
    return None

def main():
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    rows = read_rows(LATEST) + read_rows(HISTORY)
    address_list = sorted({(normalize(r.get("Plats")), normalize(r.get("Kommun"))) for r in rows if r.get("Plats") and r.get("Kommun")})
    limit = int(os.environ.get("GEOCODE_LIMIT", "80"))
    tries = 0
    for place, muni in address_list:
        key = place + "|" + muni
        if key in cache:
            continue
        if tries >= limit:
            break
        tries += 1
        try:
            matched = fetch(place, muni)
            if matched:
                cache[key] = matched
                print("OK", key)
            else:
                print("No exact location", key)
        except Exception as err:
            print("Lookup failed", key, err)
        time.sleep(1.2)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Coordinates cached: {len(cache)}; checked this run: {tries}")

if __name__ == "__main__":
    main()
