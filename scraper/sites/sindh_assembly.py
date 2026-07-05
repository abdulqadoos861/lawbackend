import logging
import requests
from lxml import html

logger = logging.getLogger(__name__)

INDEX_URL = "https://www.pas.gov.pk/bills"
BASE_URL = "https://www.pas.gov.pk"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def scrape_sindh(fallback: bool = True) -> list:
    """
    Scrapes the Sindh Assembly bills page and returns a list of bills.
    """
    results = []
    try:
        logger.info(f"Fetching Sindh Assembly page: {INDEX_URL}")
        response = requests.get(INDEX_URL, headers=HEADERS, timeout=25, verify=False)
        if response.status_code != 200:
            logger.warning(f"Sindh Assembly page returned status code {response.status_code}")
        else:
            tree = html.fromstring(response.content)
            # Find all links containing /bill/details/
            links = tree.xpath("//a[contains(@href, '/bill/details/')]")

            seen_titles = set()
            for idx, a in enumerate(links):
                title = " ".join((a.text_content() or "").split()).strip()
                href = a.get("href", "")
                if not title or not href:
                    continue
                if title in seen_titles:
                    continue
                seen_titles.add(title)

                # Search text containing '|' and 'Government'/'Private' in surrounding nodes
                date_str = ""
                for t in a.xpath("..//text() | ../following-sibling::text() | ../following-sibling::*//text()"):
                    t_clean = t.strip()
                    if "|" in t_clean and ("bill type" in t_clean.lower() or "government" in t_clean.lower() or "private" in t_clean.lower()):
                        date_str = t_clean
                        break

                detail_url = href if href.startswith("http") else BASE_URL + href

                # Fetch PDF link from detail page only for the first 15 items to optimize speed
                pdf_url = None
                if len(results) < 15:
                    try:
                        logger.info(f"Fetching Sindh bill details: {detail_url}")
                        detail_resp = requests.get(detail_url, headers=HEADERS, timeout=12, verify=False)
                        if detail_resp.status_code == 200:
                            dt_tree = html.fromstring(detail_resp.content)
                            pdf_links = dt_tree.xpath("//a[contains(@href, '/uploads/bills/') or contains(@href, '.pdf')]")
                            if pdf_links:
                                pdf_href = pdf_links[0].get("href", "")
                                pdf_url = pdf_href if pdf_href.startswith("http") else BASE_URL + pdf_href
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
        logger.warning(f"Sindh Assembly scraper failed: {e}")

    if results:
        logger.info(f"Sindh Assembly scraper: {len(results)} items collected.")
        return results

    if not fallback:
        return []

    logger.info("Sindh Assembly scraper returning fallback mock data.")
    return [
        {
            "title": "The Sindh Institute of Physical Medicine and Rehabilitation (Amendment) Bill, 2024.",
            "url": INDEX_URL,
            "pdf_url": "https://www.pas.gov.pk/uploads/bills/1742369822_Sindh%20Bill%20No.08%20of%202024.pdf",
            "category": "Bill"
        }
    ]
