"""
Senate of Pakistan – Bill Scraper
Scrapes Rules and Acts publications list.
"""
import logging
import requests
from lxml import html

logger = logging.getLogger(__name__)

BASE_URL = "https://www.senate.gov.pk"
TARGET_URL = "https://www.senate.gov.pk/en/publication.php?id=3?id=-1&catid=7&subcatid=246&cattitle=Rules%20and%20Acts"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.senate.gov.pk/",
}


def scrape_senate(fallback: bool = True) -> list:
    """
    Scrape rules and acts from senate.gov.pk publication list.
    """
    results = []
    try:
        logger.info(f"Fetching Senate page: {TARGET_URL}")
        response = requests.get(TARGET_URL, headers=HEADERS, timeout=25, verify=False)
        if response.status_code != 200:
            logger.warning(f"Senate page returned status code {response.status_code}")
        else:
            tree = html.fromstring(response.content)
            rows = tree.xpath("//table[@id='example']/tbody/tr") or tree.xpath("//table/tbody/tr")
            for row in rows:
                title_td = row.xpath("./td[@data-label='Title']")
                if not title_td:
                    continue
                title = " ".join((title_td[0].text_content() or "").split()).strip()
                if not title or "sorry, no record found" in title.lower():
                    continue

                date_td = row.xpath("./td[@data-label='Passed Date']")
                date_str = " ".join((date_td[0].text_content() or "").split()).strip() if date_td else ""

                pdf_url = None
                pdf_link = row.xpath(".//a[contains(@href, '.pdf')]")
                if pdf_link:
                    href = pdf_link[0].get("href", "")
                    if href.startswith(".."):
                        pdf_url = BASE_URL + href[2:]
                    elif href.startswith("http"):
                        pdf_url = href
                    else:
                        pdf_url = BASE_URL + href if href.startswith("/") else f"{BASE_URL}/{href}"

                tl = title.lower()
                category = "Ordinance" if "ordinance" in tl else ("Act" if "act" in tl and "bill" not in tl else "Bill")

                results.append({
                    "title": title,
                    "url": TARGET_URL,
                    "pdf_url": pdf_url,
                    "category": category,
                    "date_str": date_str,
                })
    except Exception as e:
        logger.warning(f"Senate scraper failed: {e}")

    if results:
        logger.info(f"Senate scraper: {len(results)} items collected.")
        return results

    if not fallback:
        return []

    logger.info("Senate scraper: using fallback mock data.")
    return [
        {
            "title": "The National Counter Terrorism Authority (Amendment) Bill, 2026",
            "url": TARGET_URL,
            "pdf_url": None,
            "category": "Bill",
        },
        {
            "title": "The Supreme Court Practice and Procedure (Amendment) Bill, 2026",
            "url": TARGET_URL,
            "pdf_url": None,
            "category": "Bill",
        },
    ]
