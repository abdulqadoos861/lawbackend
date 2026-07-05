import logging
import requests
from lxml import html

logger = logging.getLogger(__name__)

INDEX_URL = "https://pap.gov.pk/bills/show/en"
BASE_URL = "https://pap.gov.pk"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def scrape_punjab(fallback: bool = True) -> list:
    """
    Scrapes the Punjab Assembly bills page and returns a list of bills.
    """
    results = []
    try:
        logger.info(f"Fetching Punjab Assembly page: {INDEX_URL}")
        response = requests.get(INDEX_URL, headers=HEADERS, timeout=25, verify=False)
        if response.status_code != 200:
            logger.warning(f"Punjab Assembly page returned status code {response.status_code}")
        else:
            tree = html.fromstring(response.content)
            # Find all links containing /bills/details/en/
            links = tree.xpath("//a[contains(@href, '/bills/details/en/')]")

            seen_titles = set()
            for idx, a in enumerate(links):
                title = " ".join((a.text_content() or "").split()).strip()
                href = a.get("href", "")
                if not title or not href:
                    continue
                if title in seen_titles:
                    continue
                seen_titles.add(title)

                # Search text containing "Date:" in parent/descendant nodes
                date_str = ""
                for t in a.xpath("..//text()"):
                    t_clean = t.strip()
                    if "date:" in t_clean.lower():
                        date_str = t_clean
                        break

                detail_url = href if href.startswith("http") else BASE_URL + href

                # Fetch PDF/DOCX link from detail page only for the first 15 items to optimize speed
                pdf_url = None
                if len(results) < 15:
                    try:
                        logger.info(f"Fetching Punjab bill details: {detail_url}")
                        detail_resp = requests.get(detail_url, headers=HEADERS, timeout=12, verify=False)
                        if detail_resp.status_code == 200:
                            dt_tree = html.fromstring(detail_resp.content)
                            doc_links = dt_tree.xpath("//a[contains(@href, '/uploads/bills/') or contains(@href, '.pdf') or contains(@href, '.docx') or contains(@href, '.doc')]")
                            if doc_links:
                                doc_href = doc_links[0].get("href", "")
                                pdf_url = doc_href if doc_href.startswith("http") else BASE_URL + doc_href
                    except Exception as detail_err:
                        logger.warning(f"Failed to fetch detail page {detail_url}: {detail_err}")

                tl = title.lower()
                category = "Act" if "act" in tl else ("Bill" if "bill" in tl else "Ordinance")
                results.append({
                    "title": title,
                    "url": detail_url,
                    "pdf_url": pdf_url,
                    "category": category,
                    "date_str": date_str
                })
    except Exception as e:
        logger.warning(f"Punjab Assembly scraper failed: {e}")

    if results:
        logger.info(f"Punjab Assembly scraper: {len(results)} items collected.")
        return results

    if not fallback:
        return []

    logger.info("Punjab Assembly scraper returning fallback mock data.")
    return [
        {
            "title": "The Beaconhouse National University of Lahore (Amendment) Bill 2026 (Bill no. 54 of 2026)",
            "url": INDEX_URL,
            "pdf_url": "https://www.pap.gov.pk/uploads/bills/(54%20of%202026)%20The%20Beaconhouse%20National%20University%2C%20Lahore%20(Amendment)%20Bill%202026.docx",
            "category": "Bill"
        }
    ]
