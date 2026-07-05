import logging
import datetime
import re
from sqlalchemy.orm import Session
from db.models import Source, LawUpdate
from scraper.sites.na_gov import scrape_na
from scraper.sites.senate_gov import scrape_senate
from scraper.sites.molaw_gov import scrape_molaw
from scraper.sites.punjab_assembly import scrape_punjab
from scraper.sites.sindh_assembly import scrape_sindh
from notifier.notify import send_alert

logger = logging.getLogger(__name__)


def _run_generic_scraper(source: Source) -> list:
    """
    Fallback parser for custom sources added via the admin API.
    Uses trafilatura to fetch + lxml to scan all tables for title/PDF links.
    """
    import trafilatura
    from lxml import html as lxml_html

    url = source.url
    results = []
    raw = trafilatura.fetch_url(url)
    if not raw:
        logger.warning(f"Generic scraper: empty response for {url}")
        return results

    tree = lxml_html.fromstring(raw)
    rows = tree.cssselect("table tr") or tree.cssselect("tr")
    for row in rows:
        cells = row.findall("td")
        if len(cells) < 2:
            continue
        # Best-effort title extraction
        title = None
        for cell in cells[:3]:
            text = (cell.text_content() or "").strip()
            if text and len(text) > 15:
                title = text
                break
        if not title:
            continue
        # PDF link
        pdf_url = None
        for cell in cells:
            for a in cell.findall(".//a"):
                href = a.get("href", "")
                if ".pdf" in href.lower():
                    base = url.rstrip("/")
                    pdf_url = href if href.startswith("http") else f"{base}/{href.lstrip('/')}"
                    break
            if pdf_url:
                break
        # Heuristic category
        tl = title.lower()
        category = "Act" if "act" in tl else ("Bill" if "bill" in tl else "Ordinance")
        results.append({"title": title, "url": url, "pdf_url": pdf_url, "category": category})

    return results


# Map scraper_type → callable
_SCRAPER_MAP = {
    "na":      lambda source, fallback: scrape_na(fallback=fallback),
    "senate":  lambda source, fallback: scrape_senate(fallback=fallback),
    "molaw":   lambda source, fallback: scrape_molaw(fallback=fallback),
    "punjab":  lambda source, fallback: scrape_punjab(fallback=fallback),
    "sindh":   lambda source, fallback: scrape_sindh(fallback=fallback),
    "generic": lambda source, fallback: _run_generic_scraper(source),
}


MONTHS_MAP = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12
}

def parse_date(date_str: str) -> datetime.date | None:
    if not date_str:
        return None
    # Normalize string
    clean_str = date_str.lower().strip()
    # Remove ordinal suffixes from days (e.g., 27th -> 27, 1st -> 1, 2nd -> 2, 3rd -> 3)
    clean_str = re.sub(r'\b(\d+)(st|nd|rd|th)\b', r'\1', clean_str)
    
    # Match pattern: day month year (e.g., 30 june 2026 or 20 september 2024)
    m = re.search(r'\b(\d{1,2})\s+([a-z]+)\s+(\d{4})\b', clean_str)
    if m:
        day = int(m.group(1))
        month_name = m.group(2)
        year = int(m.group(3))
        month = MONTHS_MAP.get(month_name, 1)
        try:
            return datetime.date(year, month, day)
        except ValueError:
            pass
    
    # Match pattern: day month,year (e.g., 27 march,2017)
    m = re.search(r'\b(\d{1,2})\s+([a-z]+)\s*,\s*(\d{4})\b', clean_str)
    if m:
        day = int(m.group(1))
        month_name = m.group(2)
        year = int(m.group(3))
        month = MONTHS_MAP.get(month_name, 1)
        try:
            return datetime.date(year, month, day)
        except ValueError:
            pass

    # Match pattern: month day, year (e.g., june 30, 2026)
    m = re.search(r'\b([a-z]+)\s+(\d{1,2})\s*,\s*(\d{4})\b', clean_str)
    if m:
        month_name = m.group(1)
        day = int(m.group(2))
        year = int(m.group(3))
        month = MONTHS_MAP.get(month_name, 1)
        try:
            return datetime.date(year, month, day)
        except ValueError:
            pass

    return None


def crawl_site(source: Source, db: Session, fallback: bool = True, until_date: datetime.date = None):
    logger.info(f"Starting crawl for: {source.name} ({source.url}) [type={source.scraper_type}]")

    scraped_items = []
    scraper_fn = _SCRAPER_MAP.get(source.scraper_type, _SCRAPER_MAP["generic"])

    try:
        scraped_items = scraper_fn(source, fallback)
    except Exception as e:
        logger.error(f"Parser failed for {source.name}: {e}")
        return []

    new_items_found = []

    for item in scraped_items:
        # Date and Year filtering
        if until_date:
            date_str = item.get("date_str", "")
            item_date = parse_date(date_str)
            if item_date:
                if item_date < until_date:
                    logger.info(f"Skipping '{item['title']}' – passed date {item_date} before cutoff {until_date}")
                    continue
            else:
                # Fallback to year heuristic if no exact date is found
                year_match = re.search(r'\b(20\d{2})\b', item["title"])
                if year_match and int(year_match.group(1)) < until_date.year:
                    logger.info(f"Skipping '{item['title']}' – year {year_match.group(1)} before cutoff year {until_date.year}")
                    continue

        # Duplicate check – match on title only.
        # URLs are often the same generic listing page for many items, so using
        # them in an OR causes false-positive duplicate matches that block new entries.
        exists = db.query(LawUpdate).filter(
            LawUpdate.source_id == source.id,
            LawUpdate.title == item["title"],
        ).first()

        if exists:
            logger.debug(f"Skipping duplicate: '{item['title']}'")
            continue

        new_update = LawUpdate(
            source_id=source.id,
            title=item["title"],
            url=item["url"],
            pdf_url=item["pdf_url"],
            category=item["category"],
            date_found=datetime.datetime.utcnow(),
            is_notified=False,
        )
        db.add(new_update)
        new_items_found.append(item["title"])
        logger.info(f"New update detected: {item['title']}")


    # Update last crawled timestamp
    source.last_crawled = datetime.datetime.utcnow()
    db.commit()

    if new_items_found:
        logger.info(f"Dispatching alerts for {len(new_items_found)} new items from {source.name}")
        send_alert(source.name, new_items_found, db)

    return new_items_found


def crawl_all_sources(db: Session, fallback: bool = True, until_date: datetime.date = None):
    """Crawl every ACTIVE source; skips disabled ones."""
    sources = db.query(Source).filter(Source.is_active == True).all()
    active_count = len(sources)
    all_count = db.query(Source).count()
    skipped = all_count - active_count
    if skipped:
        logger.info(f"Skipping {skipped} disabled source(s).")

    all_new_updates = {}
    for source in sources:
        try:
            new_updates = crawl_site(source, db, fallback=fallback, until_date=until_date)
            if new_updates:
                all_new_updates[source.name] = new_updates
        except Exception as e:
            logger.error(f"Failed to crawl source {source.name}: {e}")

    return all_new_updates
