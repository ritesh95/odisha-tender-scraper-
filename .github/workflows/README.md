# GitHub Actions — Odisha Tender Scraper

## Secrets required

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**

Add these three secrets exactly as named:

| Secret name            | Where to get it                              |
|------------------------|----------------------------------------------|
| `SUPABASE_URL`         | Supabase → Project Settings → API → Project URL |
| `SUPABASE_SERVICE_KEY` | Supabase → Project Settings → API → service_role key |
| `TWOCAPTCHA_API_KEY`   | 2captcha.com → Dashboard → API Key          |

## Workflows

### `daily_scraper.yml`
Runs `python main.py` on a schedule:
- **9:00 AM IST** (03:30 UTC)
- **3:00 PM IST** (09:30 UTC)

### `archive_scraper.yml`
Runs `python scrapers/archive_scraper.py` — **manual only, never scheduled**.

## Trigger a manual run

1. Go to your repo on GitHub
2. Click the **Actions** tab
3. Click **Daily Tender Scraper** (or Archive Scraper) in the left sidebar
4. Click **Run workflow** → **Run workflow**

## Check run logs

1. Go to **Actions** tab
2. Click any run in the list
3. Click the **scrape** job to expand it
4. Click any step to see its output

## View run summaries in Supabase

Query the `scraper_runs` table in your Supabase dashboard to see historical run stats.
