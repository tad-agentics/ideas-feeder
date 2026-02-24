"""
Flippa source module.
Uses Playwright to scrape app listings from Flippa marketplace.
"""

import logging
import time

logger = logging.getLogger(__name__)

FLIPPA_URL = (
    "https://flippa.com/search?"
    "filter[listing_type][]=classified&"
    "filter[property_type][]=app&"
    "filter[monthly_revenue_min]=15000&"
    "filter[monthly_revenue_max]=120000"
)
MAX_RESULTS = 20
PAGE_DELAY = 3

CATEGORY_KEYWORDS = {
    "Finance": ["finance", "fintech", "payment", "banking", "invest", "budget"],
    "Health": ["health", "fitness", "medical", "wellness", "mental"],
    "Productivity": ["productivity", "task", "project", "workflow", "automation"],
    "Education": ["education", "learn", "course", "tutor", "study"],
    "Lifestyle": ["lifestyle", "travel", "food", "recipe", "dating", "social"],
    "Business": ["saas", "b2b", "crm", "analytics", "marketing", "sales"],
}


def _guess_category(text: str) -> str:
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return category
    return "Other"


def _parse_revenue(text: str) -> int:
    """Parse revenue strings like '$25,000' or '$25K'."""
    import re
    text = text.replace(",", "").replace(" ", "")
    match = re.search(r"\$?(\d+)[Kk]", text)
    if match:
        return int(match.group(1)) * 1000
    match = re.search(r"\$?(\d{4,6})", text)
    if match:
        return int(match.group(1))
    return 0


def fetch() -> list[dict]:
    """Fetch app listings from Flippa using Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright not installed. Run: pip install playwright && playwright install")
        return []

    items = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()

            logger.info("Flippa: navigating to search page")
            page.goto(FLIPPA_URL, wait_until="networkidle", timeout=30000)
            time.sleep(PAGE_DELAY)

            # Wait for listing cards to appear
            page.wait_for_selector(
                "[class*='listing'], [class*='card'], [class*='search-result']",
                timeout=15000,
            )

            # Try multiple selectors for Flippa's listing cards
            listings = page.query_selector_all(
                "[class*='ListingCard'], [class*='listing-card'], "
                "[class*='search-result'], .listing-item"
            )

            if not listings:
                # Fallback: try broader selectors
                listings = page.query_selector_all("a[href*='/listing/'], a[href*='/app/']")

            for listing in listings[:MAX_RESULTS]:
                try:
                    # Extract name
                    name_el = listing.query_selector(
                        "h2, h3, [class*='title'], [class*='name']"
                    )
                    name = name_el.inner_text().strip() if name_el else None
                    if not name:
                        name_text = listing.inner_text().strip()
                        name = name_text.split("\n")[0][:100] if name_text else "Unknown"

                    # Extract URL
                    link = listing.get_attribute("href")
                    if not link:
                        link_el = listing.query_selector("a[href]")
                        link = link_el.get_attribute("href") if link_el else ""
                    if link and not link.startswith("http"):
                        link = f"https://flippa.com{link}"

                    # Extract revenue
                    revenue_el = listing.query_selector(
                        "[class*='revenue'], [class*='profit'], [class*='income']"
                    )
                    revenue_text = revenue_el.inner_text().strip() if revenue_el else ""
                    monthly_revenue = _parse_revenue(revenue_text)

                    # Extract description
                    desc_el = listing.query_selector(
                        "[class*='description'], [class*='summary'], p"
                    )
                    description = desc_el.inner_text().strip()[:1000] if desc_el else ""

                    full_text = f"{name} {description}"

                    items.append({
                        "name": name,
                        "source": "Flippa",
                        "source_url": link or FLIPPA_URL,
                        "category": _guess_category(full_text),
                        "monthly_revenue": monthly_revenue,
                        "business_model": "Unknown",
                        "description": description,
                    })

                    time.sleep(0.5)
                except Exception as e:
                    logger.error("Error parsing Flippa listing: %s", e)
                    continue

            browser.close()

    except Exception as e:
        logger.error("Flippa scraping failed: %s", e)

    logger.info("Flippa: fetched %d total items", len(items))
    return items
