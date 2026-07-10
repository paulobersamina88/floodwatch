# FloodWatch Metro Manila Auto MVP

This version removes manual CSV import.

## Features

- Automatically fetches flood-related reports from Google News RSS search
- Optional Facebook Graph API integration for approved public Page access
- Detects flood-related text
- Estimates approximate flood depth
- Maps results in Metro Manila
- Exports detected reports

## Run

```bash
pip install -r requirements.txt
streamlit run app4.py
```

Or double-click:

```bash
run.bat
```

## Facebook setup

This app does NOT scrape private Facebook content.

For Facebook public Page data, you need:
1. A Meta developer app
2. A valid access token
3. Approved Page/Public Content permission where required
4. Public Page IDs/usernames entered in the sidebar

You may also set your token as an environment variable:

```bash
set FB_ACCESS_TOKEN=your_token_here
streamlit run app4.py
```

## Recommended public sources

Start with:
- MMDA
- PAGASA
- LGU public information pages
- Barangay public pages
- News pages
- Traffic advisory pages

## Important

Flood depth is estimated from text phrases such as:
- ankle / bukong
- gutter / curb
- knee / tuhod
- waist / bewang
- impassable / hindi madaanan

This is not a hydraulic model yet. The next upgrade should add:
- PAGASA rainfall
- tide/backwater risk
- river/creek level
- Sentinel-1 SAR flood extent
- user-submitted reports
