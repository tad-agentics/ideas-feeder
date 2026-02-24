# App Idea Feeder

Automatically scrapes, scores, and pushes app ideas making $20K–$50K/month to Airtable. Each idea is scored by Claude AI for Vietnam market fit.

## Sources

- **IndieHackers** — Product listings filtered by revenue
- **Reddit** — Posts from r/SideProject, r/EntrepreneurRideAlong, r/indiehackers, r/SaaSy
- **YouTube** — Videos discussing app revenue, transcripts parsed by Claude
- **Flippa** — App marketplace listings (Playwright)
- **Acquire.com** — Startup acquisition listings (Playwright)

## Setup

### 1. Install Python dependencies

```bash
python -m venv venv
source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

### 2. Install Playwright browsers

```bash
playwright install chromium
```

### 3. Get API keys

| Key | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/settings/keys |
| `AIRTABLE_API_KEY` | https://airtable.com/create/tokens — create a Personal Access Token with `data.records:read` and `data.records:write` scopes for your base |
| `AIRTABLE_BASE_ID` | Open your Airtable base, copy the ID from the URL: `https://airtable.com/appXXXXXXXXXX/...` |
| `YOUTUBE_API_KEY` | https://console.cloud.google.com/apis/credentials — enable YouTube Data API v3, create an API key |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | https://www.reddit.com/prefs/apps — create a "script" type app |

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in all API keys
```

### 5. Set up Airtable

Create a table called `AppIdeas` in your Airtable base with these fields:

| Field Name | Field Type |
|---|---|
| Name | Single line text |
| Source | Single line text |
| Source URL | URL |
| Category | Single select: Finance, Health, Productivity, Lifestyle, Education, Business, Other |
| Monthly Revenue | Number |
| Revenue Currency | Single line text |
| Business Model | Single select: Freemium, Subscription, One-time Purchase, Ad-supported, B2B, Unknown |
| Description | Long text |
| LLM Score | Number |
| Vietnam Opportunity | Single select: High, Medium, Low |
| Red Flags | Long text |
| Score Reasoning | Long text |
| Status | Single select: New, Reviewed, Validated, Passed |
| Date Added | Date |
| Dedup Hash | Single line text |

## Running

### Run once

```bash
python main.py
```

This runs the pipeline immediately, then enters daemon mode (runs daily at 07:00).

### Run as a background daemon

```bash
nohup python main.py > /dev/null 2>&1 &
```

### Check logs

```bash
tail -f logs/feeder.log
```

## Deploy on a VPS

1. SSH into your VPS
2. Clone or upload the project
3. Install Python 3.11+, then:

```bash
cd app-idea-feeder
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
playwright install-deps   # installs system dependencies for headless browsers
cp .env.example .env
# Edit .env with your API keys
```

4. Run with systemd (recommended):

Create `/etc/systemd/system/idea-feeder.service`:

```ini
[Unit]
Description=App Idea Feeder
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/app-idea-feeder
ExecStart=/path/to/app-idea-feeder/venv/bin/python main.py
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable idea-feeder
sudo systemctl start idea-feeder
sudo journalctl -u idea-feeder -f   # view logs
```

## Project structure

```
app-idea-feeder/
├── .env                  # API keys (not committed)
├── .env.example          # Template
├── requirements.txt
├── main.py               # Orchestrator + scheduler
├── scorer.py             # Claude AI scoring
├── deduper.py            # MD5 hash deduplication
├── airtable_client.py    # Airtable push logic
├── sources/
│   ├── __init__.py
│   ├── indiehackers.py   # IndieHackers scraper
│   ├── reddit.py         # Reddit API (PRAW)
│   ├── youtube.py        # YouTube + transcript parsing
│   ├── flippa.py         # Flippa (Playwright)
│   └── acquire.py        # Acquire.com (Playwright)
└── logs/
    └── feeder.log        # Runtime logs
```

## Scoring

Each idea is scored 1-5 on five criteria (max 25):

1. **Pain point existence** in Vietnam
2. **Willingness to pay** among Vietnamese users
3. **Build feasibility** (MVP in 6 weeks)
4. **Competition level** in Vietnam (5 = no competition)
5. **Localization potential**

Opportunity classification:
- **High**: score >= 18
- **Medium**: score 12-17
- **Low**: score < 12

Only items scoring >= 10 are pushed to Airtable. Items that fail scoring (score = -1) are also pushed for manual review.

## Failed items

If Airtable push fails, items are saved to `logs/failed_YYYY-MM-DD_*.json` for manual retry.
