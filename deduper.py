"""
Deduplication module.
Generates hashes for items and checks against existing Airtable records.
"""

import hashlib
import logging
import os

from pyairtable import Api

logger = logging.getLogger(__name__)


def _generate_hash(item: dict) -> str:
    """Generate MD5 hash from name + source_url for deduplication."""
    name = item.get("name", "").lower().strip()
    source_url = item.get("source_url", "").strip()
    raw = f"{name}{source_url}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _fetch_existing_hashes() -> set[str]:
    """Fetch all existing Dedup Hash values from Airtable."""
    api_key = os.getenv("AIRTABLE_API_KEY")
    base_id = os.getenv("AIRTABLE_BASE_ID")
    table_name = os.getenv("AIRTABLE_TABLE_NAME", "AppIdeas")

    if not api_key or not base_id:
        logger.warning(
            "Airtable credentials not set. Cannot check for duplicates. "
            "All items will be treated as new."
        )
        return set()

    try:
        api = Api(api_key)
        table = api.table(base_id, table_name)

        existing = set()
        for record in table.all(fields=["Dedup Hash"]):
            hash_val = record.get("fields", {}).get("Dedup Hash")
            if hash_val:
                existing.add(hash_val)

        logger.info("Deduper: fetched %d existing hashes from Airtable", len(existing))
        return existing

    except Exception as e:
        logger.error("Failed to fetch existing hashes from Airtable: %s", e)
        return set()


def filter_duplicates(items: list[dict]) -> list[dict]:
    """Filter out items that already exist in Airtable.

    Adds 'dedup_hash' field to each item that passes the filter.
    """
    existing_hashes = _fetch_existing_hashes()
    new_items = []

    for item in items:
        item_hash = _generate_hash(item)
        if item_hash in existing_hashes:
            logger.debug("Skipping duplicate: %s", item.get("name"))
            continue
        # Also check within current batch to avoid intra-batch dupes
        if item_hash in {i.get("dedup_hash") for i in new_items}:
            logger.debug("Skipping intra-batch duplicate: %s", item.get("name"))
            continue

        item["dedup_hash"] = item_hash
        new_items.append(item)

    logger.info(
        "Deduper: %d items in → %d new items out (%d duplicates removed)",
        len(items), len(new_items), len(items) - len(new_items),
    )
    return new_items
