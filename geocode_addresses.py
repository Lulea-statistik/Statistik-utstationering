"""Geokoda nya adresser utan att gissa positioner. WGS84 (EPSG:4326)."""
import csv
import math
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
REVIEW = ROOT / "geocoding_review.csv"
MANUAL = ROOT / "manual_coordinates.csv"

def read_rows(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))

def normalize(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def fetch(place, municipality):
    """Find exact address first, otherwise a marked approximate street location."""
    postal = re.search(r"\b\d{5}\b", place)
    street = re.sub(r"\s+\d{5}\b.*$", "", place).strip()
    # Municipality can be absent in provider display name: validate by postcode or local area.
    queries = [
        re.sub(r"\s+\d{5}\b", "", place).strip() + ", Sweden",
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
            zip_code = re.sub(r"\s+", "", address.get("postcode", ""))
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

def load_manual():
    """Load manually checked WGS84 positions; refuse ambiguous/invalid entries."""
    verified = {}
    for row_number, row in enumerate(read_rows(MANUAL), start=2):
        place = normalize(row.get("Adress"))
        muni = normalize(row.get("Kommun"))
        if not place and not muni:
            continue
        if muni not in ("Luleå", "Boden") or not place:
            raise ValueError(f"Manual row {row_number}: invalid address/municipality")
        key = place + "|" + muni
        if key in verified:
            raise ValueError(f"Manual row {row_number}: duplicate {key}")
        try:
            lat = float(str(row.get("Latitud", "")).replace(",", "."))
            lon = float(str(row.get("Longitud", "")).replace(",", "."))
        except ValueError as exc:
            raise ValueError(f"Manual row {row_number}: invalid coordinates") from exc
        if not math.isfinite(lat) or not math.isfinite(lon) or not (65.4 <= lat <= 66.1 and 21.1 <= lon <= 23.3):
            raise ValueError(f"Manual row {row_number}: coordinates out of accepted range")
        precision = normalize(row.get("Precision")).lower()
        if precision not in ("exact", "street", "approximate"):
            raise ValueError(f"Manual row {row_number}: Precision must be exact, street or approximate")
        source = normalize(row.get("Kalla"))
        checked = normalize(row.get("Kontrollerad_datum"))
        if not source or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", checked):
            raise ValueError(f"Manual row {row_number}: source and YYYY-MM-DD review date required")
        verified[key] = {"lat": lat, "lon": lon, "source": source,
                         "precision": precision, "verified": True, "reviewed_at": checked}
    return verified

def main():
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    manual = load_manual()
    cache.update(manual)
    latest_rows = read_rows(LATEST)
    rows = latest_rows + read_rows(HISTORY)
    priority = {}
    for r in latest_rows:
        k = normalize(r.get("Plats")) + "|" + normalize(r.get("Kommun"))
        try:
            priority[k] = priority.get(k, 0) + float(str(r.get("Arbetstagare") or "0").replace(",", "."))
        except ValueError:
            pass
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
    with REVIEW.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Adress", "Kommun", "Arbetstagare senaste", "Status", "OpenStreetMap", "Kommunal karta", "Lantmateriet Min karta", "Google Maps", "Hitta"])
        for place, muni in sorted(address_list, key=lambda x: (-priority.get(x[0] + "|" + x[1], 0), x[0])):
            if place + "|" + muni in cache:
                continue
            query = urllib.parse.quote(place + ", " + muni + ", Sverige")
            writer.writerow([
                place, muni, int(priority.get(place + "|" + muni, 0)), "Ej geokodad",
                "https://www.openstreetmap.org/search?query=" + query,
                "https://kartor.lulea.se/kommunkarta/" if muni == "Luleå" else "https://gisportal.boden.se/",
                "https://minkarta.lantmateriet.se/",
                "https://www.google.com/maps/search/?api=1&query=" + query,
                "https://www.hitta.se/sök?vad=" + query,
            ])
    print(f"Manual verified coordinates: {len(manual)}")
    print("Review queue:", REVIEW)
    print(f"Coordinates cached: {len(cache)}; checked this run: {tries}")

if __name__ == "__main__":
    main()
