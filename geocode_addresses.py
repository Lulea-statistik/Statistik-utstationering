"""Geokoda nya adresser utan att gissa positioner. WGS84 (EPSG:4326)."""
import csv
from datetime import date, timedelta
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
QUALITY = ROOT / "geocoding_quality_review.csv"
ATTEMPTS = ROOT / "geocoding_attempts.json"
CANDIDATES = ROOT / "address_source_candidates.csv"

def read_rows(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))

def normalize(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def fetch(place, municipality):
    """Search exact house number, then a distinctly labelled street-level fallback."""
    postal_match = re.search(r"\b(\d{5})\b", place)
    postal = postal_match.group(1) if postal_match else ""
    without_postal = re.sub(r"\s+\d{5}\b.*$", "", place).strip()
    house_match = re.match(r"^(.*?)\s+(\d+\s*[A-Za-zÅÄÖåäö]?)$", without_postal)
    street = house_match.group(1).strip() if house_match else without_postal
    house = re.sub(r"\s+", "", house_match.group(2)).lower() if house_match else ""
    if not street:
        return None
    # Each street-level search omits the house number. Never label a street as exact.
    queries = [(without_postal + ", " + municipality + ", Sverige", "house")]
    if postal:
        queries.append((without_postal + ", " + postal + ", Sverige", "house"))
    queries.append((street + ", " + municipality + ", Sverige", "street"))
    seen = set()
    for query, mode in queries:
        if query in seen:
            continue
        seen.add(query)
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
            lat, lon = float(match["lat"]), float(match["lon"])
            if not (65.4 <= lat <= 66.45 and 21.0 <= lon <= 23.3):
                continue
            full = (" ".join(str(v) for v in address.values()) + " " + match.get("display_name", "")).casefold()
            postcode = re.sub(r"\s+", "", address.get("postcode", ""))
            if municipality.casefold() not in full and not (postal and postal == postcode):
                continue
            # Make sure the returned street is the one requested; municipality alone is insufficient.
            names = [address.get(n, "") for n in ("road", "pedestrian", "residential", "footway", "path")]
            names.append(match.get("name", ""))
            def canonical(v):
                return re.sub(r"[^\w]", "", normalize(v).casefold())
            if canonical(street) not in {canonical(n) for n in names if n}:
                continue
            found_house = re.sub(r"\s+", "", str(address.get("house_number", ""))).lower()
            exact = mode == "house" and bool(house) and house == found_house
            if mode == "house" and found_house and not exact:
                continue
            if mode == "street" and found_house:
                continue
            if not exact and match.get("type") in ("administrative", "city", "town", "village"):
                continue
            return {
                "lat": lat, "lon": lon, "source": "OpenStreetMap Nominatim",
                "precision": "exact" if exact else "street",
                "matched_name": match.get("display_name", "")
            }
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

def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def candidate_index():
    by_address = {}
    for row in read_rows(CANDIDATES):
        address = normalize(row.get("Adress"))
        muni = normalize(row.get("Kommun"))
        if not address or not muni:
            continue
        key = address + "|" + muni
        by_address.setdefault(key, []).append(row)
    return by_address

def retry_due(item, today):
    if not item:
        return True
    try:
        return date.fromisoformat(item["next_retry"]) <= today
    except (KeyError, ValueError, TypeError):
        return True

def main():
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    manual = load_manual()
    attempts = json.loads(ATTEMPTS.read_text(encoding="utf-8")) if ATTEMPTS.exists() else {}
    candidates = candidate_index()
    today = date.today()
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
    pending = sorted(address_list, key=lambda x: (-priority.get(x[0] + "|" + x[1], 0), x[0]))
    for place, muni in pending:
        key = place + "|" + muni
        if key in cache or not retry_due(attempts.get(key), today):
            continue
        if tries >= limit:
            break
        tries += 1
        previous_failures = int(attempts.get(key, {}).get("failures", 0))
        try:
            matched = fetch(place, muni)
            if matched:
                cache[key] = matched
                attempts.pop(key, None)
                print("OK", key)
            else:
                failures = previous_failures + 1
                # Failed public-service queries back off exponentially, capped at 30 days.
                delay = min(30, 2 ** min(failures - 1, 5))
                attempts[key] = {"failures": failures, "last_attempt": today.isoformat(),
                                 "next_retry": (today + timedelta(days=delay)).isoformat(),
                                 "status": "not_found"}
                print("No address match", key, "retry after", delay, "days")
        except Exception as err:
            # Temporary outages should be retried tomorrow, without promoting bad positions.
            attempts[key] = {"failures": previous_failures, "last_attempt": today.isoformat(),
                             "next_retry": (today + timedelta(days=1)).isoformat(),
                             "status": "error"}
            print("Lookup failed", key, err)
        time.sleep(1.2)
    save_json(CACHE, cache)
    save_json(ATTEMPTS, attempts)
    with REVIEW.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Adress", "Kommun", "Arbetstagare senaste", "Status", "Nästa automatiska försök", "Antal kandidatkällor", "OpenStreetMap", "Kommunal karta", "Lantmateriet Min karta", "Google Maps", "Hitta"])
        for place, muni in sorted(address_list, key=lambda x: (-priority.get(x[0] + "|" + x[1], 0), x[0])):
            if place + "|" + muni in cache:
                continue
            query = urllib.parse.quote(place + ", " + muni + ", Sverige")
            writer.writerow([
                place, muni, int(priority.get(place + "|" + muni, 0)), "Kandidat att granska" if candidates.get(place + "|" + muni) else "Ej geokodad",
                attempts.get(place + "|" + muni, {}).get("next_retry", ""), len(candidates.get(place + "|" + muni, [])),
                "https://www.openstreetmap.org/search?query=" + query,
                "https://kartor.lulea.se/kommunkarta/" if muni == "Luleå" else "https://gisportal.boden.se/portal/apps/experiencebuilder/experience/?id=8e6928656bba4c108953d59b6fb38523",
                "https://minkarta.lantmateriet.se/",
                "https://www.google.com/maps/search/?api=1&query=" + query,
                "https://www.hitta.se/sök?vad=" + query,
            ])
    with QUALITY.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Adress", "Kommun", "Arbetstagare senaste", "Precision", "Kalla", "Matchad plats", "Status"])
        for place, muni in sorted(address_list, key=lambda x: (-priority.get(x[0] + "|" + x[1], 0), x[0])):
            result = cache.get(place + "|" + muni)
            if not result:
                continue
            precision = result.get("precision", "unknown")
            if precision == "exact" and result.get("verified"):
                continue
            status = "Exakt adress behöver oberoende kontroll" if precision == "exact" else "Granska lägesnoggrannhet"
            if place == "Stålverket 20 96140 Boden" and muni == "Boden":
                status = "PRIORITET: Ratsit och Hitta stöder nuvarande adressreferens; TIC visar avvikande fastighetsposition. Ej verifierad arbetsplatsposition."
            if place == "Svartövägen 22 97437 Luleå" and muni == "Luleå":
                status = "PRIORITET: endast gatuposition, husnummer 22 inte verifierat"
            writer.writerow([place, muni, int(priority.get(place + "|" + muni, 0)),
                             precision, result.get("source", ""), result.get("matched_name", ""), status])
    print("Position quality review:", QUALITY)
    print(f"Manual verified coordinates: {len(manual)}")
    print("Review queue:", REVIEW)
    print(f"Coordinates cached: {len(cache)}; checked this run: {tries}")

if __name__ == "__main__":
    main()
