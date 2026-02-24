"""
IndieHackers source module.
Scrapes products from IndieHackers filtered by revenue range.
"""

import logging
import time

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.indiehackers.com/products"
PARAMS = {
    "revenue": "20000-100000",
    "sorting": "revenue",
}
MAX_PAGES = 3
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

CATEGORY_MAP = {
    "saas": "Business",
    "software": "Business",
    "finance": "Finance",
    "health": "Health",
    "productivity": "Productivity",
    "education": "Education",
    "lifestyle": "Lifestyle",
}


def _guess_category(text: str) -> str:
    text_lower = text.lower()
    for keyword, category in CATEGORY_MAP.items():
        if keyword in text_lower:
            return category
    return "Other"


def _parse_revenue(text: str) -> int:
    """Parse revenue string like '$25K/mo' or '$25,000/mo' into integer."""
    import re
    text = text.replace(",", "").replace(" ", "")
    match = re.search(r"\$(\d+)[Kk]", text)
    if match:
        return int(match.group(1)) * 1000
    match = re.search(r"\$(\d{4,6})", text)
    if match:
        return int(match.group(1))
    return 0


def fetch() -> list[dict]:
    """Fetch product listings from IndieHackers."""
    items = []

    for page in range(1, MAX_PAGES + 1):
        try:
            params = {**PARAMS, "page": page}
            resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")

            # IndieHackers uses various class patterns for product cards.
            # Try multiple selectors to find product listings.
            product_cards = soup.select(
                ".products-list__product, .product-card, "
                "[class*='product'], .feed-item"
            )

            if not product_cards:
                logger.warning(
                    "No product cards found on page %d. "
                    "Site structure may have changed.", page
                )
                break

            for card in product_cards:
                try:
                    name_el = card.select_one(
                        ".product__name, .product-card__name, h2, h3, a[href*='/product/']"
                    )
                    name = name_el.get_text(strip=True) if name_el else None
                    if not name:
                        continue

                    link_el = card.select_one("a[href]")
                    href = link_el["href"] if link_el else ""
                    if href and not href.startswith("http"):
                        href = f"https://www.indiehackers.com{href}"

                    revenue_el = card.select_one(
                        ".product__revenue, [class*='revenue'], "
                        "[class*='mrr'], .product-card__revenue"
                    )
                    revenue_text = revenue_el.get_text(strip=True) if revenue_el else ""
                    monthly_revenue = _parse_revenue(revenue_text)

                    desc_el = card.select_one(
                        ".product__description, .product-card__description, "
                        "p, [class*='tagline']"
                    )
                    description = desc_el.get_text(strip=True) if desc_el else ""
                    description = description[:1000]

                    category = _guess_category(f"{name} {description}")

                    items.append({
                        "name": name,
                        "source": "IndieHackers",
                        "source_url": href or BASE_URL,
                        "category": category,
                        "monthly_revenue": monthly_revenue,
                        "business_model": "Unknown",
                        "description": description,
                    })
                except Exception as e:
                    logger.error("Error parsing IndieHackers card: %s", e)
                    continue

            logger.info("IndieHackers page %d: found %d products", page, len(product_cards))
            time.sleep(2)

        except requests.RequestException as e:
            logger.error("IndieHackers page %d request failed: %s", page, e)
            break

    logger.info("IndieHackers: fetched %d total items", len(items))
    return items
