"""
YouTube source module.
Searches YouTube for app revenue videos and extracts structured data from transcripts.
"""

import json
import logging
import os
import time

import anthropic
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger(__name__)

SEARCH_QUERY = '"app" "revenue" "per month" "$20k" OR "$30k" OR "$50k"'
MAX_RESULTS = 20

TRANSCRIPT_PARSE_PROMPT = """Extract app/product information from this YouTube video transcript.
The video discusses apps or products making significant monthly revenue.

Video title: {title}
Transcript (first 3000 chars):
{transcript}

Extract ALL apps/products mentioned that have revenue data. For each app, provide:
- name: The app or product name
- monthly_revenue: Monthly revenue in USD (integer, 0 if unclear)
- category: One of Finance, Health, Productivity, Lifestyle, Education, Business, Other
- business_model: One of Freemium, Subscription, One-time Purchase, Ad-supported, B2B, Unknown
- description: Brief description (max 200 chars)

Respond ONLY with valid JSON array, no markdown, no explanation:
[{{"name": "...", "monthly_revenue": 0, "category": "...", "business_model": "...", "description": "..."}}]

If no relevant apps found, respond with: []
"""


def _get_transcript(video_id: str) -> str:
    """Fetch transcript for a YouTube video."""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        full_text = " ".join(entry["text"] for entry in transcript_list)
        return full_text[:3000]
    except Exception as e:
        logger.warning("Could not fetch transcript for %s: %s", video_id, e)
        return ""


def _parse_transcript_with_claude(title: str, transcript: str) -> list[dict]:
    """Use Claude Haiku to extract structured app data from transcript."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set. Cannot parse transcript.")
        return []

    client = anthropic.Anthropic(api_key=api_key)

    prompt = TRANSCRIPT_PARSE_PROMPT.format(title=title, transcript=transcript)

    try:
        message = client.messages.create(
            model="claude-haiku-3-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text.strip()
        parsed = json.loads(response_text)
        if isinstance(parsed, list):
            return parsed
        return []
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Claude response as JSON: %s", e)
        return []
    except anthropic.APIError as e:
        logger.error("Claude API error during transcript parsing: %s", e)
        return []


def fetch() -> list[dict]:
    """Fetch app ideas from YouTube videos."""
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        logger.error("YOUTUBE_API_KEY not set. Skipping YouTube source.")
        return []

    youtube = build("youtube", "v3", developerKey=api_key)

    try:
        search_response = youtube.search().list(
            q=SEARCH_QUERY,
            part="snippet",
            type="video",
            order="relevance",
            publishedAfter=_get_30_days_ago(),
            maxResults=MAX_RESULTS,
        ).execute()
    except Exception as e:
        logger.error("YouTube search API failed: %s", e)
        return []

    items = []

    for result in search_response.get("items", []):
        video_id = result["id"]["videoId"]
        title = result["snippet"]["title"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        transcript = _get_transcript(video_id)
        if not transcript:
            continue

        parsed_apps = _parse_transcript_with_claude(title, transcript)
        time.sleep(1)  # Rate limit Claude API calls

        for app in parsed_apps:
            revenue = app.get("monthly_revenue", 0)
            if not isinstance(revenue, int):
                try:
                    revenue = int(revenue)
                except (ValueError, TypeError):
                    revenue = 0

            items.append({
                "name": app.get("name", "Unknown App"),
                "source": "YouTube",
                "source_url": video_url,
                "category": app.get("category", "Other"),
                "monthly_revenue": revenue,
                "business_model": app.get("business_model", "Unknown"),
                "description": app.get("description", "")[:1000],
            })

    logger.info("YouTube: fetched %d total items", len(items))
    return items


def _get_30_days_ago() -> str:
    """Return ISO 8601 timestamp for 30 days ago."""
    from datetime import datetime, timedelta, timezone
    dt = datetime.now(timezone.utc) - timedelta(days=30)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
