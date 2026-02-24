"""
Airtable client module.
Pushes scored and deduplicated app ideas to Airtable.
"""

import json
import logging
import os
from datetime import date, datetime

from pyairtable import Api

logger = logging.getLogger(__name__)

BATCH_SIZE = 10
MIN_SCORE = 10


def _map_to_airtable_fields(item: dict) -> dict:
    """Map an internal item dict to Airtable field names."""
    return {
        "Name": item.get("name", "Unknown")[:100],
        "Source": item.get("source", "Unknown"),
        "Source URL": item.get("source_url", ""),
        "Category": item.get("category", "Other"),
        "Monthly Revenue": item.get("monthly_revenue", 0),
        "Revenue Currency": "USD",
        "Business Model": item.get("business_model", "Unknown"),
        "Description": item.get("description", "")[:5000],
        "LLM Score": item.get("llm_score", 0),
        "Vietnam Opportunity": item.get("vietnam_opportunity", "Low"),
        "Red Flags": item.get("red_flags", ""),
        "Score Reasoning": item.get("score_reasoning", ""),
        "Status": "New",
        "Date Added": date.today().isoformat(),
        "Dedup Hash": item.get("dedup_hash", ""),
    }


def push(items: list[dict]) -> None:
    """Push items to Airtable. Filters by minimum score and batches requests."""
    api_key = os.getenv("AIRTABLE_API_KEY")
    base_id = os.getenv("AIRTABLE_BASE_ID")
    table_name = os.getenv("AIRTABLE_TABLE_NAME", "AppIdeas")

    if not api_key or not base_id:
        logger.error("Airtable credentials not set. Cannot push items.")
        _save_failed(items, "missing_credentials")
        return

    # Filter by minimum score, but always include items with score -1 (failed scoring)
    eligible = [
        item for item in items
        if item.get("llm_score", 0) >= MIN_SCORE or item.get("llm_score", 0) == -1
    ]

    if not eligible:
        logger.info("Airtable: no items met the minimum score threshold of %d", MIN_SCORE)
        return

    logger.info(
        "Airtable: pushing %d items (filtered from %d, min score=%d)",
        len(eligible), len(items), MIN_SCORE,
    )

    api = Api(api_key)
    table = api.table(base_id, table_name)

    failed_items = []

    for i in range(0, len(eligible), BATCH_SIZE):
        batch = eligible[i : i + BATCH_SIZE]
        records = [_map_to_airtable_fields(item) for item in batch]

        try:
            table.batch_create(records)
            logger.info(
                "Airtable: batch %d-%d pushed successfully (%d records)",
                i + 1, min(i + BATCH_SIZE, len(eligible)), len(batch),
            )
        except Exception as e:
            logger.error(
                "Airtable: batch %d-%d failed: %s",
                i + 1, min(i + BATCH_SIZE, len(eligible)), e,
            )
            failed_items.extend(batch)

    if failed_items:
        _save_failed(failed_items, "push_error")


def _save_failed(items: list[dict], reason: str) -> None:
    """Save failed items to a JSON file for manual retry."""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)

    filename = f"failed_{date.today().isoformat()}_{reason}.json"
    filepath = os.path.join(log_dir, filename)

    # Make items JSON-serializable
    serializable = []
    for item in items:
        clean = {}
        for k, v in item.items():
            if isinstance(v, (datetime, date)):
                clean[k] = v.isoformat()
            else:
                clean[k] = v
        serializable.append(clean)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
        logger.info("Saved %d failed items to %s", len(items), filepath)
    except Exception as e:
        logger.error("Failed to save failed items: %s", e)
