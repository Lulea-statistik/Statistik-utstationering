"""Fetch public posting details with a strict, non-personal field allowlist.

This optional enrichment step never writes names of people, telephone numbers,
email addresses, free text or page HTML to the public repository.
"""
from __future__ import annotations

import csv
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

ROOT = Path("data")
SOURCE = ROOT / "latest.csv"
OUT = ROOT / "posting_details.csv"
FIELDS = ["DetailURL", "Arbetsgivarland", "Bransch", "Startdatum",
          "Slutdatum", "Varaktighet_dagar", "Status", "Hamtningsdatum"]
LABELS = {
    "Arbetsgivarland": ("arbetsgivarens etableringsland", "etableringsland", "land där arbetsgivaren är etablerad", "arbetsgivarens land"),
    "Bransch": ("bransch", "typ av tjänst", "verksamhetsområde", "sni-kod"),
    "Startdatum": ("startdatum", "utstationeringens startdatum", "påbörjas", "start för utstationeringen"),
    "Slutdatum": ("slutdatum", "utstationeringens slutdatum", "avslutas", "slut för utstationeringen"),
}
def clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()

def permitted(url: str) -> bool:
    u = urlparse(url)
    return (u.scheme == "https" and u.hostname == "www.av.se"
            and u.path.rstrip("/") == "/arbetsmiljoarbete-och-inspektioner/e-tjanster-och-blanketter/sok-utstationering"
            and bool(parse_qs(u.query).get("id")))

def safe_value(field: str, value: str) -> str:
    value = clean(value)
    if not value or len(value) > 100 or "@" in value or re.search(r"(?:\+\d{6,}|\b\d{8,}\b)", value):
        return ""
    if field in ("Startdatum", "Slutdatum"):
        for pattern, fmt in (("%Y-%m-%d", "%Y-%m-%d"), ("%Y-%m-%d", "%Y-%m-%d"), ("%d/%m/%Y", "%d/%m/%Y"), ("%d-%m-%Y", "%d-%m-%Y")):
            try:
                return datetime.strptime(value, fmt).date().isoformat()
            except ValueError:
                pass
        return ""
    # Short, label-bound categorical attributes only; never infer from page text.
    if len(value.split()) > 10:
        return ""
    return value

def extract(page) -> dict:
    # Only explicit field/value pairs, not unrestricted page text or HTML.
    pairs = page.locator("main dt, main dd, main th, main td").evaluate_all(
        """els => els.map(e => ({tag:e.tagName.toLowerCase(), text:(e.innerText||'').trim()}))"""
    )
    found = {}
    for idx, item in enumerate(pairs[:-1]):
        if item["tag"] not in ("dt", "th"):
            continue
        next_item = pairs[idx + 1]
        if next_item["tag"] not in ("dd", "td"):
            continue
        label = clean(item["text"]).casefold().strip(":")
        for field, names in LABELS.items():
            if label in names and field not in found:
                value = safe_value(field, next_item["text"])
                if value:
                    found[field] = value
    return found

def read_csv(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))

def main():
    previous = {r["DetailURL"]: r for r in read_csv(OUT) if permitted(r.get("DetailURL", ""))}
    urls = list(dict.fromkeys(r.get("DetailURL", "") for r in read_csv(SOURCE) if permitted(r.get("DetailURL", ""))))
    today = datetime.now(timezone.utc).date().isoformat()
    pending = [u for u in urls if u not in previous or previous[u].get("Status") not in ("ok", "fields_unavailable")]
    # Limit requests to be respectful of the source and GitHub runtime.
    pending = pending[:int(__import__("os").environ.get("DETAIL_PAGE_LIMIT", "30"))]
    if pending:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(locale="sv-SE", viewport={"width": 1100, "height": 850})
            for url in pending:
                record = {k: "" for k in FIELDS}
                record["DetailURL"] = url
                record["Hamtningsdatum"] = today
                try:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    if response is None or response.status >= 400:
                        raise RuntimeError("Detail page unavailable")
                    fields = extract(page)
                    record.update(fields)
                    if fields.get("Startdatum") and fields.get("Slutdatum"):
                        from datetime import date
                        start, end = date.fromisoformat(fields["Startdatum"]), date.fromisoformat(fields["Slutdatum"])
                        if 0 <= (end - start).days <= 3650:
                            record["Varaktighet_dagar"] = str((end - start).days)
                    record["Status"] = "ok" if fields else "fields_unavailable"
                except Exception:
                    record["Status"] = "fetch_failed"
                previous[url] = record
                time.sleep(1.25)
            browser.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, delimiter=";", fieldnames=FIELDS)
        writer.writeheader()
        for url in sorted(previous):
            writer.writerow({k: previous[url].get(k, "") for k in FIELDS})
    print(f"Detail enrichment: {len(pending)} fetched, {len(previous)} cached, no personal fields collected")

if __name__ == "__main__":
    main()
