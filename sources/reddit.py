"""
Reddit source module.
Searches relevant subreddits for app ideas with revenue data.
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone

import praw

logger = logging.getLogger(__name__)

SUBREDDITS = ["SideProject", "EntrepreneurRideAlong", "indiehackers", "SaaSy"]
SEARCH_QUERY = (
    '(revenue OR MRR OR "per month") AND (app OR tool OR saas) '
    'AND ("$20" OR "$30" OR "$40" OR "$50")'
)
MIN_REVENUE = 15_000
MAX_REVENUE = 120_000

CATEGORY_KEYWORDS = {
    "Finance": ["finance", "fintech", "payment", "banking", "invest", "budget", "money"],
    "Health": ["health", "fitness", "medical", "wellness", "mental", "therapy"],
    "Productivity": ["productivity", "task", "project management", "workflow", "automation"],
    "Education": ["education", "learn", "course", "tutor", "study", "school"],
    "Lifestyle": ["lifestyle", "travel", "food", "recipe", "dating", "social"],
    "Business": ["saas", "b2b", "crm", "analytics", "marketing", "sales", "startup"],
}


def _extract_revenue(text: str) -> int:
    """Extract monthly revenue figure from text."""
    # Match patterns like $20K, $30k, $50K
    k_matches = re.findall(r"\$(\d+)[Kk]", text)
    for m in k_matches:
        val = int(m) * 1000
        if MIN_REVENUE <= val <= MAX_REVENUE:
            return val

    # Match patterns like $20,000 or $50000
    num_matches = re.findall(r"\$(\d{1,3}(?:,\d{3})*)", text)
    for m in num_matches:
        val = int(m.replace(",", ""))
        if MIN_REVENUE <= val <= MAX_REVENUE:
            return val

    # Match plain 4-6 digit numbers preceded by $
    plain_matches = re.findall(r"\$(\d{4,6})", text)
    for m in plain_matches:
        val = int(m)
        if MIN_REVENUE <= val <= MAX_REVENUE:
            return val

    return 0


def _guess_category(text: str) -> str:
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return category
    return "Other"


def _guess_business_model(text: str) -> str:
    text_lower = text.lower()
    if "subscription" in text_lower or "mrr" in text_lower or "recurring" in text_lower:
        return "Subscription"
    if "freemium" in text_lower:
        return "Freemium"
    if "one-time" in text_lower or "one time" in text_lower or "lifetime" in text_lower:
        return "One-time Purchase"
    if "ad" in text_lower and ("revenue" in text_lower or "supported" in text_lower):
        return "Ad-supported"
    if "b2b" in text_lower or "enterprise" in text_lower:
        return "B2B"
    return "Unknown"


def fetch() -> list[dict]:
    """Fetch app ideas from Reddit using PRAW."""
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "AppIdeaFeeder/1.0")

    if not client_id or not client_secret:
        logger.error("Reddit API credentials not configured. Skipping Reddit source.")
        return []

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )

    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    for sub_name in SUBREDDITS:
        try:
            subreddit = reddit.subreddit(sub_name)
            results = subreddit.search(SEARCH_QUERY, sort="new", time_filter="week", limit=50)

            for post in results:
                try:
                    post_time = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
                    if post_time < cutoff:
                        continue

                    full_text = f"{post.title} {post.selftext}"
                    revenue = _extract_revenue(full_text)

                    if revenue < MIN_REVENUE or revenue > MAX_REVENUE:
                        continue

                    # Try to extract app name from title
                    # Common patterns: "I built [AppName]" or "[AppName] - description"
                    name_match = re.search(
                        r"(?:I (?:built|made|created|launched)\s+)([A-Z][\w\s.]+?)(?:\s*[-–—,:]|\s+and\b|\s+that\b|\s+to\b)",
                        post.title,
                    )
                    name = name_match.group(1).strip() if name_match else post.title[:80]

                    description = post.selftext[:1000] if post.selftext else post.title

                    items.append({
                        "name": name,
                        "source": "Reddit",
                        "source_url": f"https://reddit.com{post.permalink}",
                        "category": _guess_category(full_text),
                        "monthly_revenue": revenue,
                        "business_model": _guess_business_model(full_text),
                        "description": description,
                    })
                except Exception as e:
                    logger.error("Error parsing Reddit post in r/%s: %s", sub_name, e)
                    continue

            logger.info("Reddit r/%s: processed search results", sub_name)

        except Exception as e:
            logger.error("Reddit r/%s search failed: %s", sub_name, e)
            continue

    logger.info("Reddit: fetched %d total items", len(items))
    return items
