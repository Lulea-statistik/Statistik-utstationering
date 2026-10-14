"""Validate committed geocoding artifacts before deployment."""
import csv
import json
import math
from pathlib import Path

DATA = Path("data")
def load_json(name):
    path = DATA / name
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)

def read_csv(name):
    with (DATA / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))

def main():
    points = load_json("geocoded_addresses.json")
    attempts = load_json("geocoding_attempts.json")
    assert isinstance(points, dict) and isinstance(attempts, dict)
    active = {
        (r["Plats"].strip() + "|" + r["Kommun"].strip())
        for name in ("latest.csv", "history.csv")
        for r in read_csv(name)
        if r.get("Plats") and r.get("Kommun")
    }
    missing = active - points.keys()
    queue = read_csv("geocoding_review.csv")
    queued = {r["Adress"].strip() + "|" + r["Kommun"].strip() for r in queue}
    assert queued == missing, f"Review queue mismatch: missing {sorted(missing - queued)}, extra {sorted(queued - missing)}"
    assert len(queued) == len(queue), "Duplicate review queue entries"
    for key, loc in points.items():
        assert isinstance(loc, dict), key
        lat = float(loc["lat"])
        lon = float(loc["lon"])
        assert math.isfinite(lat) and math.isfinite(lon) and 65.4 <= lat <= 66.45 and 21.0 <= lon <= 23.3, key
    for key, item in attempts.items():
        assert isinstance(item, dict) and item.get("next_retry"), key
    quality = read_csv("geocoding_quality_review.csv")
    assert all(r["Adress"].strip() + "|" + r["Kommun"].strip() in points for r in quality)
    print(f"VALID: {len(points)} coordinates, {len(missing)} unresolved addresses, "
          f"{len(attempts)} scheduled retries, {len(quality)} quality-review rows.")

if __name__ == "__main__":
    main()
