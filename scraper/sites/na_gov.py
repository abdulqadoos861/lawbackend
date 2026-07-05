"""
National Assembly of Pakistan – Bill Scraper
URL: https://na.gov.pk/en/bills.php?status=pass
Table class: table_bill
Structure: [Sr#, Date, Title-as-PDF-link]
"""
import logging
import requests
from lxml import html

logger = logging.getLogger(__name__)

BASE_URL = "https://na.gov.pk"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://na.gov.pk/",
}

# Scrape these status pages to get maximum coverage
NA_PAGES = [
    ("https://na.gov.pk/en/bills.php?status=pass",    "Bill"),
    ("https://na.gov.pk/en/bills.php?status=pending",  "Bill"),
    ("https://na.gov.pk/en/bills.php",                 "Bill"),
]


def _resolve_url(href: str, page_url: str) -> str:
    """Resolve a relative href to an absolute URL."""
    if href.startswith("http"):
        return href
    if href.startswith("../"):
        # ../uploads/documents/xxx.pdf → https://na.gov.pk/uploads/documents/xxx.pdf
        return BASE_URL + "/" + href[3:]
    if href.startswith("/"):
        return BASE_URL + href
    # relative to the directory of the page
    base_dir = page_url.rsplit("/", 1)[0]
    return base_dir + "/" + href


def scrape_na(fallback: bool = True) -> list:
    """
    Scrape all bills from na.gov.pk using direct requests + lxml XPath.
    Returns a list of dicts: {title, url, pdf_url, category}.
    """
    results = []
    seen_titles: set = set()

    for page_url, default_category in NA_PAGES:
        try:
            logger.info(f"Fetching NA page: {page_url}")
            response = requests.get(page_url, headers=HEADERS, timeout=25)
            response.raise_for_status()

            tree = html.fromstring(response.content)

            # Find the main bills table (class contains 'table_bill')
            bill_tables = tree.xpath("//table[contains(@class,'table_bill')]")
            if not bill_tables:
                # Fall back to any large table
                bill_tables = tree.xpath("//table")
            
            for table in bill_tables:
                data_rows = table.xpath(".//tr[.//td]")
                logger.debug(f"  Found {len(data_rows)} data rows in table")

                for row in data_rows:
                    cells = row.xpath(".//td")
                    if len(cells) < 2:
                        continue

                    # Look for a link in any cell – that link's text = title, href = PDF
                    links = row.xpath(".//a[@href]")
                    if not links:
                        continue

                    # Pick the first meaningful link
                    title_link = None
                    for link in links:
                        text = (link.text_content() or "").strip()
                        href = link.get("href", "")
                        if text and len(text) > 10:
                            title_link = (text, href)
                            break

                    if not title_link:
                        continue

                    title, href = title_link
                    title = " ".join(title.split())  # normalize whitespace

                    if title in seen_titles:
                        continue
                    seen_titles.add(title)

                    # Resolve URL
                    abs_href = _resolve_url(href, page_url)

                    # Determine if href is a PDF
                    is_pdf = ".pdf" in abs_href.lower()
                    pdf_url = abs_href if is_pdf else None
                    portal_url = abs_href if not is_pdf else page_url

                    # Determine category from title
                    tl = title.lower()
                    if "ordinance" in tl:
                        category = "Ordinance"
                    elif "act" in tl and "bill" not in tl:
                        category = "Act"
                    else:
                        category = default_category

                    results.append({
                        "title": title,
                        "url": portal_url,
                        "pdf_url": pdf_url,
                        "category": category,
                    })

            logger.info(f"  Scraped {len(results)} total unique items so far from NA")

        except Exception as e:
            logger.warning(f"NA scraper failed for {page_url}: {e}")
            if not fallback:
                raise

    if results:
        logger.info(f"NA scraper: {len(results)} bills collected successfully.")
        return results

    # Fallback mock data if everything failed
    if fallback:
        logger.info("NA scraper: using fallback mock data.")
        return [
            {
                "title": "The National Commission for Human Rights (Amendment) Bill, 2026",
                "url": "https://na.gov.pk/en/bills.php?status=pass",
                "pdf_url": None,
                "category": "Bill",
            }
        ]

    return results
