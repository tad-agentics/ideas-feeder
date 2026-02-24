"""
App Idea Feeder - Main Orchestrator

Scrapes app ideas from multiple sources, scores them for Vietnam market fit,
deduplicates, and pushes results to Airtable. Runs on a daily schedule.
"""

import logging
import os
import sys
import time
from datetime import datetime

import schedule
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "feeder.log")),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")

# Import modules after dotenv so env vars are available
from sources import indiehackers, reddit, youtube, flippa, acquire
import scorer
import deduper
import airtable_client


def run_pipeline():
    """Execute the full scrape → score → dedup → push pipeline."""
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("Pipeline run started at %s", start_time.isoformat())
    logger.info("=" * 60)

    all_items = []

    # 1. Collect from all sources
    source_modules = [
        ("IndieHackers", indiehackers.fetch),
        ("Reddit", reddit.fetch),
        ("YouTube", youtube.fetch),
        ("Flippa", flippa.fetch),
        ("Acquire", acquire.fetch),
    ]

    for name, fetch_fn in source_modules:
        try:
            logger.info("Fetching from %s...", name)
            items = fetch_fn()
            all_items.extend(items)
            logger.info("%s: returned %d items", name, len(items))
        except Exception as e:
            logger.error("%s: fetch failed with error: %s", name, e, exc_info=True)

    logger.info("Total items fetched: %d", len(all_items))

    if not all_items:
        logger.warning("No items fetched from any source. Ending pipeline run.")
        return

    # 2. Score all items
    logger.info("Scoring %d items...", len(all_items))
    scored_items = scorer.score_batch(all_items)

    scored_count = sum(1 for i in scored_items if i.get("llm_score", 0) > 0)
    failed_count = sum(1 for i in scored_items if i.get("llm_score", 0) == -1)
    logger.info("Scoring complete: %d scored, %d failed", scored_count, failed_count)

    # 3. Deduplicate
    logger.info("Deduplicating...")
    new_items = deduper.filter_duplicates(scored_items)

    # 4. Push to Airtable
    logger.info("Pushing %d new items to Airtable...", len(new_items))
    airtable_client.push(new_items)

    # 5. Summary
    elapsed = datetime.now() - start_time
    logger.info("=" * 60)
    logger.info(
        "Pipeline complete: %d fetched → %d scored → %d new → pushed to Airtable",
        len(all_items), len(scored_items), len(new_items),
    )
    logger.info("Elapsed time: %s", str(elapsed).split(".")[0])
    logger.info("=" * 60)


def main():
    """Entry point. Runs pipeline immediately, then schedules daily at 7AM."""
    logger.info("App Idea Feeder starting up")

    # Run immediately on start
    run_pipeline()

    # Schedule daily run
    schedule.every().day.at("07:00").do(run_pipeline)
    logger.info("Scheduled daily run at 07:00. Waiting...")

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
