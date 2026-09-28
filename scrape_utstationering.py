from __future__ import annotations

import csv
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode

from playwright.sync_api import Page, Locator, sync_playwright

BASE_URL = (
    "https://www.av.se/arbetsmiljoarbete-och-inspektioner/"
    "e-tjanster-och-blanketter/sok-utstationering/"
)

MUNICIPALITIES = ["Luleå", "Boden"]
OUT_DIR = Path("data")
DAILY_DIR = OUT_DIR / "daily"
DEBUG_DIR = Path("debug")


@dataclass
class Row:
    SnapshotDate: str
    SnapshotTime: str
    Arbetsgivare: str
    Plats: str
    Arbetstagare: str
    Kommun: str
    DetailURL: str
    PageNumber: int
    RawText: str


def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def find_select(page: Page, label_regex: str) -> Locator:
    rx = re.compile(label_regex, re.I)

    # 1) Properly associated <label>
    loc = page.get_by_label(rx)
    if loc.count():
        return loc.first

    # 2) Nearby text followed by a select
    labels = page.locator("label")
    for i in range(labels.count()):
        lab = labels.nth(i)
        txt = clean(lab.inner_text())
        if rx.search(txt):
            target = lab.locator("select")
            if target.count():
                return target.first
            fid = lab.get_attribute("for")
            if fid:
                target = page.locator(f"#{fid}")
                if target.count():
                    return target.first

    # 3) Search containers containing the visible label text
    candidates = page.locator("select")
    for i in range(candidates.count()):
        sel = candidates.nth(i)
        try:
            parent_text = clean(sel.locator("xpath=..").inner_text())
        except Exception:
            parent_text = ""
        if rx.search(parent_text):
            return sel

    raise RuntimeError(f"Kunde inte hitta select-fält som matchar: {label_regex}")


def select_municipality(page: Page, municipality: str) -> None:
    sel = page.locator("select#C")
    if not sel.count():
        raise RuntimeError("Kommunfältet select#C hittades inte")

    municipality_values = {
        "Luleå": "2580",
        "Boden": "2582",
    }
    value = municipality_values.get(municipality)
    if not value:
        raise RuntimeError(f"Okänd kommun: {municipality}")

    sel.select_option(value=value)
    print(f"Vald kommun: {municipality} ({value})")


def select_all_industries(page: Page) -> None:
    sel = page.locator("select#E")
    if not sel.count():
        raise RuntimeError("Branschfältet select#E hittades inte")

    options = sel.locator("option")
    values: list[str] = []
    for i in range(options.count()):
        opt = options.nth(i)
        value = (opt.get_attribute("value") or "").strip()
        if not value:
            continue
        values.append(value)

    if not values:
        raise RuntimeError("Inga branschvärden hittades")

    sel.select_option(values)
    print(f"Valde {len(values)} branscher")


def click_search(page: Page) -> None:
    btn = page.get_by_role("button", name=re.compile(r"^sök$", re.I))
    if not btn.count():
        btn = page.locator("button, input[type=submit]").filter(has_text=re.compile(r"sök", re.I))
    if not btn.count():
        raise RuntimeError("Sök-knappen hittades inte")
    btn.first.click()
    page.wait_for_load_state("networkidle")


def set_max_hits_per_page(page: Page) -> None:
    sel = page.locator("select#SelectedHitsPerPage")
    if not sel.count():
        return

    options = sel.locator("option")
    numeric: list[int] = []
    for i in range(options.count()):
        opt = options.nth(i)
        value = (opt.get_attribute("value") or "").strip()
        if value.isdigit():
            numeric.append(int(value))

    if numeric:
        max_value = str(max(numeric))
        sel.select_option(value=max_value)
        page.wait_for_load_state("networkidle")
        print(f"Resultat per sida: {max_value}")


def text_after_label(text: str, labels: Iterable[str]) -> str:
    for label in labels:
        m = re.search(rf"{re.escape(label)}\s*[:\-]?\s*([^|;\n]+)", text, re.I)
        if m:
            return clean(m.group(1))
    return ""


def candidate_blocks(page: Page) -> list[Locator]:
    # Prefer semantic result containers. The site has changed markup before,
    # so several generic fallbacks are intentionally supported.
    selectors = [
        "main article",
        "main .search-result",
        "main .search-result-item",
        "main [class*='search-result']",
        "main [class*='result-item']",
        "main ol > li",
        "main ul > li",
    ]
    for selector in selectors:
        loc = page.locator(selector)
        blocks = []
        for i in range(loc.count()):
            item = loc.nth(i)
            txt = clean(item.inner_text())
            if len(txt) < 15:
                continue
            # Result records normally mention workers/location/employer.
            if re.search(r"arbetstag|arbetsgiv|plats|utstation", txt, re.I):
                blocks.append(item)
        if blocks:
            return blocks
    return []


def rows_from_table(page: Page, snapshot_date: str, snapshot_time: str, municipality: str, page_no: int) -> list[Row]:
    rows: list[Row] = []
    tables = page.locator("main table")
    for ti in range(tables.count()):
        table = tables.nth(ti)
        headers = [clean(x) for x in table.locator("thead th").all_inner_texts()]
        trs = table.locator("tbody tr")
        for i in range(trs.count()):
            tr = trs.nth(i)
            cells = [clean(x) for x in tr.locator("td").all_inner_texts()]
            if not cells:
                continue
            data = dict(zip(headers, cells)) if headers else {}
            raw = " | ".join(cells)
            link = tr.locator("a[href]")
            href = link.first.get_attribute("href") if link.count() else ""
            if href and href.startswith("/"):
                href = "https://www.av.se" + href
            employer = next((v for k, v in data.items() if re.search(r"arbetsgiv|företag", k, re.I)), "")
            place = next((v for k, v in data.items() if re.search(r"plats|ort|adress", k, re.I)), "")
            workers = next((v for k, v in data.items() if re.search(r"arbetstag|antal", k, re.I)), "")
            if not employer and cells:
                employer = cells[0]
            rows.append(Row(snapshot_date, snapshot_time, employer, place, workers, municipality, href or "", page_no, raw))
    return rows


def rows_from_blocks(page: Page, snapshot_date: str, snapshot_time: str, municipality: str, page_no: int) -> list[Row]:
    out: list[Row] = []
    for block in candidate_blocks(page):
        raw = clean(block.inner_text())
        if not raw:
            continue
        link = block.locator("a[href]")
        href = link.first.get_attribute("href") if link.count() else ""
        if href and href.startswith("/"):
            href = "https://www.av.se" + href

        heading = block.locator("h2,h3,h4,strong")
        employer = clean(heading.first.inner_text()) if heading.count() else ""
        if not employer:
            employer = text_after_label(raw, ["Arbetsgivare", "Företag"])
        place = text_after_label(raw, ["Plats", "Arbetsplats", "Ort", "Adress"])
        workers = text_after_label(raw, ["Arbetstagare", "Antal arbetstagare", "Antal"])

        # Avoid obvious navigation/menu items accidentally caught by generic selectors.
        if not re.search(r"arbetstag|arbetsgiv|utstation|plats", raw, re.I):
            continue
        out.append(Row(snapshot_date, snapshot_time, employer, place, workers, municipality, href or "", page_no, raw))
    return out


def scrape_current_page(page: Page, snapshot_date: str, snapshot_time: str, municipality: str, page_no: int) -> list[Row]:
    table_rows = rows_from_table(page, snapshot_date, snapshot_time, municipality, page_no)
    if table_rows:
        return table_rows
    return rows_from_blocks(page, snapshot_date, snapshot_time, municipality, page_no)


def click_next(page: Page) -> bool:
    selectors = [
        "a[rel='next']",
        "button[aria-label*='Nästa' i]",
        "a[aria-label*='Nästa' i]",
    ]
    for selector in selectors:
        loc = page.locator(selector)
        if loc.count() and loc.first.is_visible() and loc.first.is_enabled():
            loc.first.click()
            page.wait_for_load_state("networkidle")
            return True

    nxt = page.get_by_role("link", name=re.compile(r"nästa", re.I))
    if nxt.count() and nxt.first.is_visible():
        nxt.first.click()
        page.wait_for_load_state("networkidle")
        return True
    nxt_btn = page.get_by_role("button", name=re.compile(r"nästa", re.I))
    if nxt_btn.count() and nxt_btn.first.is_visible() and nxt_btn.first.is_enabled():
        nxt_btn.first.click()
        page.wait_for_load_state("networkidle")
        return True
    return False


def scrape_municipality(page: Page, municipality: str, snapshot_date: str, snapshot_time: str, max_pages: int = 100) -> list[Row]:
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_load_state("networkidle")

    municipality_values = {
        "Luleå": "2580",
        "Boden": "2582",
    }
    municipality_code = municipality_values[municipality]

    # Read the current industry codes from the live form.
    industry_options = page.locator("select#E option")
    industry_codes: list[str] = []
    for i in range(industry_options.count()):
        value = (industry_options.nth(i).get_attribute("value") or "").strip()
        if value and value != "0":
            industry_codes.append(value)

    if not industry_codes:
        raise RuntimeError("Inga branschkoder hittades i select#E")

    # IMPORTANT: the search form is POST. GET query parameters are displayed
    # back in the page but are not treated as active filter selections.
    page.locator("#SelectedCounties").evaluate(
        "(el, value) => { el.value = value; }",
        municipality_code,
    )
    page.locator("#Expertises").evaluate(
        "(el, value) => { el.value = value; }",
        " ".join(industry_codes),
    )

    # C and E are helper dropdowns used to add one filter at a time. Keep them
    # at their neutral value so they do not add an unrelated county/industry.
    page.locator("select#C").select_option(value="0")
    page.locator("select#E").select_option(value="0")
    page.locator("#ContractorName").fill("")
    page.locator("#SelectedHitsPerPage").select_option(value="50")

    print(
        f"POST-sökning {municipality}: kommun={municipality_code}, "
        f"branscher={len(industry_codes)}"
    )

    with page.expect_navigation(wait_until="domcontentloaded", timeout=60000):
        page.locator("#posting-search-form").evaluate("(form) => form.submit()")
    page.wait_for_load_state("networkidle")

    debug_name = municipality.lower().replace("å", "a").replace("ä", "a").replace("ö", "o")
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(
        path=str(DEBUG_DIR / f"{debug_name}_{snapshot_date}.png"),
        full_page=True,
    )
    (DEBUG_DIR / f"{debug_name}_{snapshot_date}.html").write_text(
        page.content(),
        encoding="utf-8",
    )

    result_text = clean(page.locator("#posting-results").inner_text()) if page.locator("#posting-results").count() else ""
    print(f"Resultat-URL {municipality}: {page.url}")
    print(f"Resultattext {municipality}: {result_text[:500]}")
    print(
        f"DOM {municipality}: "
        f"tables={page.locator('main table').count()}, "
        f"articles={page.locator('main article').count()}, "
        f"result_children={page.locator('#posting-results > *').count()}, "
        f"links={page.locator('#posting-results a[href]').count()}"
    )

    all_rows: list[Row] = []
    seen_page_signatures: set[tuple[str, ...]] = set()

    for page_no in range(1, max_pages + 1):
        rows = scrape_current_page(page, snapshot_date, snapshot_time, municipality, page_no)

        # Diagnostic signature: use the first few detail URLs from the current
        # result page. This lets us see whether "Nästa" actually reaches a new page.
        result_links = page.locator("#posting-results a[href*='id=']")
        signature = tuple(
            (result_links.nth(i).get_attribute("href") or "")
            for i in range(min(3, result_links.count()))
        )
        print(
            f"PAGE {municipality} #{page_no}: rows={len(rows)}, "
            f"detail_links={result_links.count()}, signature={signature}"
        )

        if signature and signature in seen_page_signatures:
            print(f"REPEAT {municipality} #{page_no}: samma resultatsida har redan setts")
            break
        if signature:
            seen_page_signatures.add(signature)

        all_rows.extend(rows)

        # Log the visible next controls before clicking.
        next_candidates = page.locator(
            "a[rel='next'], a[aria-label*='Nästa' i], "
            "button[aria-label*='Nästa' i], a:has-text('Nästa'), button:has-text('Nästa')"
        )
        next_info: list[str] = []
        for i in range(min(5, next_candidates.count())):
            item = next_candidates.nth(i)
            if item.is_visible():
                next_info.append(
                    f"text={clean(item.inner_text())!r}, "
                    f"href={item.get_attribute('href')!r}, "
                    f"aria={item.get_attribute('aria-label')!r}"
                )
        print(f"NEXT {municipality} #{page_no}: {next_info}")

        if not click_next(page):
            print(f"STOP {municipality} #{page_no}: ingen Nästa-kontroll")
            break
    return all_rows


def dedupe(rows: list[Row]) -> list[Row]:
    seen = set()
    out = []
    for r in rows:
        key = (r.Kommun, r.Arbetsgivare, r.Plats, r.Arbetstagare, r.DetailURL, r.RawText)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def write_csv(path: Path, rows: list[Row], append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(rows[0]).keys()) if rows else [
        "SnapshotDate", "SnapshotTime", "Arbetsgivare", "Plats", "Arbetstagare",
        "Kommun", "DetailURL", "PageNumber", "RawText"
    ]
    mode = "a" if append else "w"
    exists = path.exists() and path.stat().st_size > 0
    with path.open(mode, newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        if not append or not exists:
            w.writeheader()
        for r in rows:
            w.writerow(asdict(r))


def main() -> None:
    now = datetime.now().astimezone()
    snapshot_date = now.strftime("%Y-%m-%d")
    snapshot_time = now.strftime("%H:%M:%S%z")
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    all_rows: list[Row] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="sv-SE", viewport={"width": 1440, "height": 1400})
        page.set_default_timeout(20000)
        try:
            for municipality in MUNICIPALITIES:
                rows = scrape_municipality(page, municipality, snapshot_date, snapshot_time)
                print(f"{municipality}: {len(rows)} råa rader")
                all_rows.extend(rows)
        except Exception:
            DEBUG_DIR.mkdir(exist_ok=True)
            page.screenshot(path=str(DEBUG_DIR / f"failure_{snapshot_date}.png"), full_page=True)
            (DEBUG_DIR / f"failure_{snapshot_date}.html").write_text(page.content(), encoding="utf-8")
            raise
        finally:
            browser.close()

    all_rows = dedupe(all_rows)
    if not all_rows:
        raise RuntimeError("0 resultat hittades. Ingen tom snapshot skrivs; kontrollera debug-filerna.")

    daily_path = DAILY_DIR / f"utstationering_{snapshot_date}.csv"
    write_csv(daily_path, all_rows, append=False)
    write_csv(OUT_DIR / "latest.csv", all_rows, append=False)

    # Append only once per snapshot date to history.csv.
    history = OUT_DIR / "history.csv"
    existing_dates = set()
    if history.exists():
        with history.open("r", newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f, delimiter=";"):
                if row.get("SnapshotDate"):
                    existing_dates.add(row["SnapshotDate"])
    if snapshot_date not in existing_dates:
        write_csv(history, all_rows, append=True)

    print(f"Klart: {len(all_rows)} unika rader")
    print(f"Daglig fil: {daily_path}")


if __name__ == "__main__":
    main()
