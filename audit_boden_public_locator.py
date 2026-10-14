"""Discover Boden public ArcGIS locator URLs using public portal metadata only."""
import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://gisportal.boden.se/portal"
OUT = Path("data/boden_public_locator_audit.csv")
HEADERS = {"User-Agent": "LuleaStatistikLocatorAudit/1.0 (https://github.com/Lulea-statistik/Statistik-utstationering)"}
def load(url, params=None):
    url += ("?" + urllib.parse.urlencode(params)) if params else ""
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=25) as handle:
        value = json.load(handle)
    if value.get("error"):
        raise ValueError(str(value["error"])[:180])
    return value
def add(rows, origin, title, url, note):
    rows.append([origin, title, url, note])
def main():
    rows = []
    try:
        portal = load(BASE + "/sharing/portals/self", {"f": "json"})
        for loc in portal.get("helperServices", {}).get("geocode", []) or []:
            add(rows,"portal helperServices.geocode",loc.get("name",""),loc.get("url",""),
                "Locator annonserad i publik portalmetadata; adressmatchning och nyttjanderätt ej verifierade")
        add(rows,"portal self",portal.get("name","Boden"),BASE+"/sharing/portals/self",
            "Portalmetadata åtkomlig")
    except (OSError, ValueError, TypeError) as exc:
        add(rows,"portal self","","","Metadatafel: "+str(exc)[:160])
    try:
        query = load(BASE + "/sharing/rest/search", {"f":"json","q":"(adress OR address OR locator) AND (type:Geocoding Service OR type:Feature Service OR type:Map Service)","num":25})
        for item in query.get("results") or []:
            add(rows,"portal search",item.get("title",""),item.get("url",""),
                "Publikt indexerad tjänst; inte verifierat som öppet adress-API")
        if not query.get("results"):
            add(rows,"portal search","","","Inga relevanta publikt indexerade tjänster")
    except (OSError, ValueError, TypeError) as exc:
        add(rows,"portal search","","","Metadatafel: "+str(exc)[:160])
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open("w",encoding="utf-8-sig",newline="") as handle:
        writer=csv.writer(handle,delimiter=";")
        writer.writerow(["Ursprung","Namn","URL","Status"])
        writer.writerows(rows)
    print("Boden public locator metadata:", len(rows), "records")
if __name__ == "__main__":
    main()
