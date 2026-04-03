# NOCTURN — Nightlife Party Finder

A Flask web app that scrapes Instagram profiles for party/event posts,
processes them with **Gemini AI**, and displays structured event info
(price, date, time, location, phone, dress code, etc.) in a slick dark-purple UI.

---

## Project Structure

```
nightlife_app/
├── app.py                  ← Flask app factory & entry point
├── database.py             ← SQLAlchemy db instance
├── models.py               ← Event, ScrapedProfile models
├── requirements.txt
├── .env.example            ← Copy to .env and fill in keys
│
├── routes/
│   ├── __init__.py
│   ├── home.py             ← / and /home
│   ├── events.py           ← /events, /events/scrape, /events/<id>
│   └── admin.py            ← /admin panel
│
├── services/
│   ├── __init__.py
│   ├── scraper_service.py  ← Instagram scraping (Apify / RapidAPI)
│   └── ai_service.py       ← Gemini AI event extraction
│
├── static/
│   ├── css/style.css       ← Dark purple nightlife theme
│   └── js/main.js          ← Animations, mobile nav, toast
│
├── templates/
│   ├── base.html           ← Navbar, footer, flash messages
│   ├── home.html           ← Landing page with stats & features
│   ├── events.html         ← Events grid with filter & search
│   ├── event_detail.html   ← Single event detail view
│   ├── admin.html          ← Admin dashboard
│   └── admin_login.html    ← Admin login
│
└── utils/
    ├── __init__.py
    ├── logger.py           ← Rotating file + console logger
    ├── decorators.py       ← @login_required, @admin_required, @api_key_required
    └── helpers.py          ← Hashing, token gen, parsing helpers
```

---

## Setup

### 1. Install dependencies
```bash
cd nightlife_app
pip install -r requirements.txt
```

### 2. Configure API keys
```bash
cp .env.example .env
# Edit .env with your keys
```

**You need at least one scraping API:**

| API | URL | Notes |
|-----|-----|-------|
| Apify | https://apify.com | Best quality, use `apify~instagram-post-scraper` |
| RapidAPI | https://rapidapi.com/search/instagram | Search "Instagram Scraper API2" |

**And Gemini AI:**
- Get a free key at https://aistudio.google.com/app/apikey

### 3. Run
```bash
python app.py
```

Visit `http://localhost:5000`

---

## Usage

### Admin Panel
1. Go to `/admin` → password: `nightlife2025` (change in `routes/admin.py`)
2. Add Instagram profile usernames (e.g., `clubnoir_skopje`, `vertigo_mk`)
3. Click **"Scrape All Now"** → app fetches posts → Gemini extracts event info → saved to DB

### Events Page
- `/events` — browse all events
- Filter by music genre
- Search by name, venue, location
- Click an event for full detail (price, phone, address, time, etc.)

### Without API Keys
The app works in **demo mode** with sample events if no API keys are set.

---

## Changing Admin Password
Edit `routes/admin.py`:
```python
ADMIN_PASSWORD = "your-new-password"
```

---

## Adding More Scraping Sources
Extend `services/scraper_service.py` — add a new function following the same interface:
```python
def scrape_profile(username: str, max_posts: int = 10) -> list[dict]:
    # Returns list of {caption, image_url, post_url, timestamp, username}
```
