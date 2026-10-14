# Statistik-utstationering

Daglig hämtning av pågående utstationeringar från Arbetsmiljöverket för:

- Luleå
- Boden
- samtliga branscher som finns i sökformuläret vid körningstillfället

## Varför formulärstyrning i stället för den gamla parameter-URL:en?

Arbetsmiljöverkets söksida har flyttats/ändrats och den äldre URL-strukturen med bland annat `SelectedCounties` och `Expertises` är därför mindre robust. Skriptet öppnar den aktuella söksidan, väljer kommun och alla branscher direkt i formuläret och hämtar samtliga resultatsidor.

## Filer

- `scrape_utstationering.py` – scraper
- `.github/workflows/daily-utstationering.yml` – daglig GitHub Actions-körning
- `data/latest.csv` – senaste snapshot
- `data/daily/utstationering_YYYY-MM-DD.csv` – en separat fil per dag
- `data/history.csv` – alla snapshots staplade över tid

CSV-filer skrivs med semikolon och UTF-8 med BOM för att fungera bra i svensk Excel/Power BI.

## Kolumner

- `SnapshotDate`
- `SnapshotTime`
- `Arbetsgivare`
- `Plats`
- `Arbetstagare`
- `Kommun`
- `DetailURL`
- `PageNumber`
- `RawText`

`RawText` finns med som skydd om Arbetsmiljöverket ändrar etiketter/HTML. Det gör det lättare att reparera parsningen utan att historiska snapshots går förlorade.

## Daglig körning

Workflowen kör automatiskt 04:15 UTC varje dag och kan också startas manuellt från **Actions → Daglig utstationering → Run workflow**.

GitHub Actions använder UTC. 04:15 UTC motsvarar 06:15 svensk sommartid och 05:15 svensk vintertid.

## Viktig felsäkring

Skriptet skriver inte en tom dagsfil om sidan ändras eller parsningen misslyckas. I stället misslyckas workflowen och sparar screenshot + HTML som ett debug-artifact i GitHub Actions.

## Manuell kontroll av adresser som saknar koordinater

Efter geokodningskörningen finns `data/geocoding_review.csv` med adresser som saknar position samt länkar för manuell kontroll.

Spara manuellt verifierade positioner i **`data/manual_coordinates.csv`** (semikolonseparerad UTF-8) med kolumnerna:

```csv
Adress;Kommun;Latitud;Longitud;Precision;Kalla;Kontrollerad_datum
```

- **Adress**: kopiera exakt från granskningsfilen (inklusive postnummer och ort).
- **Kommun**: `Luleå` eller `Boden`.
- **Latitud/Longitud**: decimalgrader i **EPSG:4326**, använd punkt som decimaltecken i CSV. Förväxla inte med SWEREF 99 TM (EPSG:3006) eller Lantmäteriets kartvisning.
- **Precision**: `exact` (kontrollerat husnummer), `street` (gatans ungefärliga position), `approximate` (annan osäker position). Ange aldrig `exact` utan kontroll.
- **Kalla**: namn/URL till den källa som faktiskt ger rätt att använda och lagra koordinaten.
- **Kontrollerad_datum**: exempelvis `2026-10-14`.

Rader utan verifierad källa eller koordinater ska **inte** läggas i den manuella filen. Länkar till Google Maps och Hitta i granskningsfilen är endast för kontroll; deras koordinater ska inte kopieras till den publika filen utan att användningsvillkoren tillåter det.

När filen ändras startar GitHub Actions automatiskt en ny geokodningskörning. Manuell data valideras och ges företräde över tidigare automatiska koordinater. Originalvärden och manuellt angivna uppgifter skrivs inte över i `manual_coordinates.csv`. Om format, precision eller koordinatintervall är fel avbryts körningen i stället för att publicera felaktiga positioner.
