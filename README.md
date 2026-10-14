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

## Automatisk fallback för nya och svårgeokodade adresser

Flödet startar vid nya data i `data/latest.csv` eller `data/history.csv`, ändringar i granskningsfilerna, manuellt i GitHub Actions samt veckovis som reserv.

1. Återanvänd tidigare cachade koordinater; verifierade koordinater i `data/manual_coordinates.csv` har alltid företräde.
2. Nya adresser skickas till Nominatim med full adress, adress/postnummer och gatusökning. Samma gatunamn och korrekt husnummer krävs för klassningen `exact`. Gatupunkter märks `street`.
3. Misslyckade försök sparas i `data/geocoding_attempts.json`. Automatiska omsökningar sker tidigast efter 1, 2, 4, 8, 16 och därefter högst 30 dagar. Tillfälliga nätverksfel försöks igen nästa dag. Oanvända anrop undviks.
4. Kvarvarande adresser skrivs till `data/geocoding_review.csv`, sorterad efter senast registrerade antal arbetstagare. Där visas nästa försök, antal dokumenterade kandidatkällor och söklänkar till OpenStreetMap, kommunal karta, Lantmäteriet, Google Maps och Hitta.
5. Koordinatkandidater i `data/address_source_candidates.csv` används **bara som granskningsunderlag**, aldrig som automatiskt godkända koordinater. Godkända WGS84-adresspunkter läggs i `data/manual_coordinates.csv` med källa, datum och precision.
6. `data/geocoding_quality_review.csv` granskar även redan geokodade platser med låg eller okänd precision.

Observera att kartwebbplatsernas vanliga sök-URL:er **inte är API:er för automatisk koordinathämtning**. Öppet publicerade kommunala adress-API:er kan senare läggas till som separata automatiska källor när behörighet, licens och adressmatchning är kontrollerade. Gör inte webbsideskrapning av Google Maps eller Hitta för återpublicering.

### Publika adresskällor som alternativ till OpenStreetMap

Inga interna SQL-servrar och ingen tjänst från Lantmäteriets Geotorget används i denna lösning.

**Luleå:** Den öppet åtkomliga kartportalen finns på https://kartportal.lulea.se/portal/ . Kommunens publika `adresskarta/MapServer` finns på https://kartportal.lulea.se/server/rest/services/adresskarta/MapServer . Det är en **bakgrundskarta**, inte ett verifierat API med sökbara adresspunkter och husnummer. Använd därför inte karttjänstens mittpunkt som adresskoordinat.

**Boden:** Publik WebGIS-karta finns på https://gisportal.boden.se/portal/apps/experiencebuilder/experience/?id=8e6928656bba4c108953d59b6fb38523 och kommunens guide på https://boden.se/steg-for-steg-guider/anvand-webgis . Kartan har adressökning, men något öppet adresstjänst-API bakom den är ännu inte verifierat.

**Andra publika källor:** OpenStreetMap Nominatim är fortsatt enda aktiva automatiska geokodaren. Övriga publika adress- och fastighetswebbplatser kan användas för källkontroll, med respekt för användningsvillkor. Ingen automatisk skrapning eller import från Google Maps, Hitta eller Ratsit.

**Förberedd frivillig import:** `prepare_official_address_candidates.py` fungerar för en **valfri behörigt tillgänglig och återanvändbar** adress-CSV med `Adress;Kommun;Latitud;Longitud;Kalla` (WGS84). Det är inget beroende av en särskild dataleverantör och det publicerar aldrig koordinater automatiskt.

```bash
python prepare_official_address_candidates.py /saker/plats/oppna_adresspunkter_wgs84.csv
```

Ett framtida automatiskt ArcGIS-fallbacksteg får aktiveras först när vi kan verifiera en publik `FeatureServer`- eller sökbar `MapServer`-tjänst med korrekt kommun, gatunamn, husnummer, koordinatsystem och tillåtna nyttjandevillkor. Annars fortsätter den befintliga prioriterade granskningskön.

### Automatisk kommunal fallback för Luleå (granskningsläge)

Efter den vanliga OSM-geokodningen körs `fallback_lulea_municipal_addresses.py` automatiskt i samma GitHub Actions-flöde. Det söker endast Luleåadresser som inte redan har koordinater märkta `exact`. Gatunamn och husnummer matchas mot Luleås publika ArcGIS REST-lager `adresskarta/MapServer/86`. Sökningar sker adressvis, kontrollerar exakt matchning, en enda träff och WGS84-koordinater inom regionen. Rapporten `data/municipal_address_candidates.csv` redovisar nya kandidater och sökfel även för framtida adresser. Ingen koordinat i rapporten förs automatiskt över till kartans produktionscache eftersom rätt till lagring och offentlig återpublicering ännu inte verifierats. Boden hanteras fortsatt med OSM och den manuella granskningskön tills ett motsvarande öppet kommunalt adress-API identifierats.

### Bodens publika adresslocator som automatisk fallback (granskningsläge)

Efter OSM-sökningen körs också `fallback_boden_municipal_addresses.py`, som frågar Bodens publika `GaidaLocator_Address/GeocodeServer` för adresser utan `exact`-position. Scriptet jämför **hela gatunamnet och husnumret**, kontrollerar träffens score och WGS84-punkt och skriver `data/boden_municipal_address_candidates.csv`. Det försöker alltså även förbättra redan ungefärligt geokodade adresser.

Observera att den äldre avgränsningen 65,4–66,1 grader nord är för snäv för norra Boden. Bodens granskningssteg accepterar därför 65,4–66,45 och kräver fortfarande exakt adressmatchning. Träffar och koordinatprecision måste kvalitetssäkras, och återanvändningsvillkoren klarläggas, innan några av dessa punkter skrivs till den publika produktionscachen. En API-träff ensam räcker inte för att en adress ska försvinna från tabellen över saknade koordinater.

### Aktiverad import av entydiga Bodenträffar

Efter `fallback_boden_municipal_addresses.py` körs nu `promote_boden_municipal_addresses.py`: kandidater med matchat gatunamn **och husnummer**, minst 70 i locator-score och koordinater inom Boden/Luleå läggs i `data/geocoded_addresses.json` med `precision: exact`, käll-URL och match-score. Manuellt kontrollerade koordinater eller redan exakta matchningar skrivs inte över. Därefter återskapas listan över saknade adresser och en kontroll säkerställer att adresserna finns i antingen kartcachen eller granskningskön. Adresser utan säker API-träff, exempelvis Flarkenvägen 15 och Hydrogränd 2, lämnas kvar för granskning. Även Rödkallen 66 kvarstår utan en användbar Luleåposition. För Bodens norra delar tillåter valideringen latitud till 66,45° N.

**Återanvändningsnotering:** Bodens publika locator är tekniskt åtkomlig. Kommunens särskilda villkor för lagring och återpublicering av dess koordinater i projektets öppna datakälla är ännu inte separat bekräftade. Denna import görs enligt projektägarens önskemål; klarlägg villkoren med kommunen och avpublicera vid behov.

## Berikning av offentliga detaljuppgifter (nytt pipeline-steg)

Efter den ordinarie dagliga inläsningen körs `enrich_posting_details.py` automatiskt i `.github/workflows/daily-utstationering.yml`. Programmet hämtar ett begränsat antal offentliga `DetailURL`-sidor från Arbetsmiljöverkets domän och söker **endast** efter explicita strukturerade fält för etableringsland, bransch/tjänstetyp och planerat start- och slutdatum. Beräknad varaktighet härleds bara från två giltiga datum. Resultatet skrivs i `data/posting_details.csv` och återanvänds vid kommande körningar.

- Högst 30 nya URL:er per körning (miljövariabeln `DETAIL_PAGE_LIMIT`) och 1,25 sekunders paus mellan anropen.
- Inga personnamn, personnummer, telefonnummer, e-postadresser, fria beskrivningar eller rå HTML sparas från detaljsidorna. Fält utan verifierad etikett förblir tomma.
- `Status=ok` betyder att minst ett tillåtet fält hittats. `fields_unavailable` betyder att den offentliga sidan kunde öppnas men inga godkända fält kunde extraheras. `fetch_failed` innebär misslyckat anrop som kan prövas på nytt.
- Det ordinarie CSV-formatet och befintliga diagram har inte ändrats. Berikningen är ett separat förberedande dataset, inte en utlovad källa för alla uppgifter.
- Steget är ett icke-blockerande tillägg så att datainsamlingen fortsätter även om Arbetsmiljöverkets detaljsidor ändras. Den faktiska träffsäkerheten måste valideras mot en fullständig GitHub Actions-körning innan nya webbdiagram byggs.
