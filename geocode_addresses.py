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
    """Find exact address first, otherwise a marked approximate street location."""
    postal = re.search(r"\\b\\d{5}\\b", place)
    street = re.sub(r"\\s+\\d{5}\\b.*$", "", place).strip()
    # Municipality can be absent in provider display name: validate by postcode or local area.
    queries = [
        re.sub(r"\\s+\\d{5}\\b", "", place).strip() + ", Sweden",
        street + ", " + municipality + ", Sweden",
    ]
    for i, query in enumerate(dict.fromkeys(queries)):
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
            "q": query, "format": "json", "limit": "8",
            "countrycodes": "se", "addressdetails": "1"
        })
        req = urllib.request.Request(url, headers={
            "User-Agent": "LuleaStatistikUtstationering/1.0 (https://github.com/Lulea-statistik/Statistik-utstationering)",
            "Accept": "application/json"
        })
        with urllib.request.urlopen(req, timeout=25) as reply:
            matches = json.load(reply)
        for match in matches:
            address = match.get("address") or {}
            display = normalize(match.get("display_name")).lower()
            full = " ".join(str(x) for x in address.values()).lower() + " " + display
            # Reject unrelated addresses. Require municipality or matching postal code.
            zip_code = re.sub(r"\\s+", "", address.get("postcode", ""))
            valid_place = municipality.lower() in full or (postal and postal.group() == zip_code)
            if not valid_place:
                continue
            lat, lon = float(match["lat"]), float(match["lon"])
            if not (65.4 <= lat <= 66.1 and 21.1 <= lon <= 23.3):
                continue
            kind = match.get("type")
            if kind in ("administrative", "city", "town", "village", "residential"):
                continue
            exact = bool(address.get("house_number")) and i == 0
            if i == 1 and kind not in ("road", "residential", "pedestrian", "service", "tertiary", "unclassified"):
                continue
            return {"lat": lat, "lon": lon, "source": "OpenStreetMap Nominatim",
                    "precision": "exact" if exact else "street",
                    "matched_name": match.get("display_name", "")}
        time.sleep(1.2)
    return None

def main():
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    rows = read_rows(LATEST) + read_rows(HISTORY)
    address_list = sorted({(normalize(r.get("Plats")), normalize(r.get("Kommun"))) for r in rows if r.get("Plats") and r.get("Kommun")})
    limit = int(os.environ.get("GEOCODE_LIMIT", "200"))
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
