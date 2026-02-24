"""
Scoring module.
Uses Claude API to evaluate each app idea for Vietnam market fit.
"""

import json
import logging
import os
import time

import anthropic

logger = logging.getLogger(__name__)

SCORING_PROMPT = """You are an app market analyst evaluating opportunities for a Vietnamese app studio.

App information:
- Name: {name}
- Category: {category}
- Monthly Revenue: ${monthly_revenue} USD
- Business Model: {business_model}
- Description: {description}

Score this app opportunity for the Vietnamese market on 5 criteria (1-5 each):

1. Pain point existence in Vietnam: Does this pain point exist for Vietnamese users?
2. Vietnamese willingness to pay: Will Vietnamese users pay for this type of app?
3. Build feasibility: Can an MVP be built in 6 weeks with a small team?
4. Competition level in Vietnam: How low is the existing competition in Vietnam? (5=no competition, 1=very competitive)
5. Localization potential: Can this be localized for Vietnam without losing core value?

Respond ONLY with valid JSON, no markdown, no explanation:
{{
  "scores": {{
    "pain_point": <1-5>,
    "willingness_to_pay": <1-5>,
    "build_feasibility": <1-5>,
    "competition": <1-5>,
    "localization": <1-5>
  }},
  "total_score": <sum of above, max 25>,
  "vietnam_opportunity": "<High|Medium|Low>",
  "red_flags": ["<flag1>", "<flag2>"],
  "reasoning": "<2-3 sentences max>"
}}"""

MODEL = "claude-haiku-3-5-20251001"
MAX_RETRIES = 1
SLEEP_BETWEEN_CALLS = 1


def _create_client() -> anthropic.Anthropic | None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set. Scoring disabled.")
        return None
    return anthropic.Anthropic(api_key=api_key)


def score(item: dict) -> dict:
    """Score a single app idea using Claude API.

    Returns the item dict with added scoring fields:
    - llm_score (int): total score out of 25
    - vietnam_opportunity (str): High/Medium/Low
    - red_flags (str): comma-separated flags
    - score_reasoning (str): reasoning text
    """
    client = _create_client()
    if not client:
        item["llm_score"] = -1
        item["vietnam_opportunity"] = "Low"
        item["red_flags"] = "Scoring unavailable - API key missing"
        item["score_reasoning"] = ""
        return item

    prompt = SCORING_PROMPT.format(
        name=item.get("name", "Unknown"),
        category=item.get("category", "Other"),
        monthly_revenue=item.get("monthly_revenue", 0),
        business_model=item.get("business_model", "Unknown"),
        description=item.get("description", "No description"),
    )

    for attempt in range(MAX_RETRIES + 1):
        try:
            message = client.messages.create(
                model=MODEL,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = message.content[0].text.strip()
            result = json.loads(response_text)

            total = result.get("total_score", 0)
            if not isinstance(total, (int, float)):
                total = 0

            # Enforce opportunity logic based on total score
            if total >= 18:
                opportunity = "High"
            elif total >= 12:
                opportunity = "Medium"
            else:
                opportunity = "Low"

            item["llm_score"] = int(total)
            item["vietnam_opportunity"] = opportunity
            item["red_flags"] = ", ".join(result.get("red_flags", []))
            item["score_reasoning"] = result.get("reasoning", "")

            time.sleep(SLEEP_BETWEEN_CALLS)
            return item

        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse scoring response for '%s' (attempt %d): %s",
                item.get("name"), attempt + 1, e,
            )
        except anthropic.APIError as e:
            logger.error(
                "Claude API error scoring '%s' (attempt %d): %s",
                item.get("name"), attempt + 1, e,
            )

        if attempt < MAX_RETRIES:
            time.sleep(2)

    # All retries exhausted
    item["llm_score"] = -1
    item["vietnam_opportunity"] = "Low"
    item["red_flags"] = "Scoring failed after retries"
    item["score_reasoning"] = ""
    return item


def score_batch(items: list[dict]) -> list[dict]:
    """Score a list of items. Convenience wrapper with progress logging."""
    total = len(items)
    scored = []
    for i, item in enumerate(items, 1):
        logger.info("Scoring item %d/%d: %s", i, total, item.get("name", "Unknown"))
        scored.append(score(item))
    return scored
