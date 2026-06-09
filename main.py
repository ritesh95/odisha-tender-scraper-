"""
main.py — Odisha Tender Scraper Pipeline
Run:  python main.py
"""
import os
import sys
import time
from datetime import datetime, timezone, timedelta

from scrapers.listing import run_listing_scraper
from scrapers.detail import process_tender
from utils.logger import get_logger

log = get_logger()

IN_CI = os.environ.get("GITHUB_ACTIONS") == "true"
IST   = timezone(timedelta(hours=5, minutes=30))


def _log_run_to_supabase(summary: dict):
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from db.supabase_client import supabase
        supabase.table("scraper_runs").insert(summary).execute()
    except Exception as e:
        log.warning(f"Could not log run to Supabase scraper_runs: {e}")


def run():
    start     = time.time()
    start_ist = datetime.now(IST)

    log.info("=" * 60)
    log.info("Odisha Tender Scraper — run started")
    if IN_CI:
        log.info("Environment: GitHub Actions (headless)")
    log.info("=" * 60)

    # ── Step 1: listing scraper ────────────────────────────────────
    log.info("Fetching listing page and detail pages...")
    captcha_solved = False
    try:
        pages = run_listing_scraper()
        captcha_solved = True
    except Exception as e:
        log.error(f"Listing scraper failed: {e}")
        if IN_CI:
            sys.exit(1)
        return

    if not pages:
        log.warning("No pages returned — listing scraper returned empty list")
        return

    log.info(f"Listing scraper returned {len(pages)} detail pages")

    # ── Step 2: parse + upsert each tender ────────────────────────
    total   = len(pages)
    new     = 0
    updated = 0
    skipped = 0
    failed  = 0

    for i, (url, html) in enumerate(pages, 1):
        log.info(f"[{i}/{total}] Processing...")
        if not html:
            log.warning(f"  No HTML for URL: {url[:80]}")
            skipped += 1
            continue

        try:
            result = process_tender(html, url)
            if result == "new":
                new += 1
            elif result == "updated":
                updated += 1
            elif result:
                # backward compat: process_tender returns True
                updated += 1
            else:
                failed += 1
        except Exception as e:
            log.error(f"  Unexpected error: {e}")
            failed += 1

    # ── Summary ───────────────────────────────────────────────────
    elapsed_s = round(time.time() - start)
    mins, secs = divmod(elapsed_s, 60)
    runtime_str = f"{mins}m {secs:02d}s"
    time_ist    = start_ist.strftime("%Y-%m-%d %H:%M:%S IST")

    summary_lines = [
        "========= RUN SUMMARY =========",
        f"Time:             {time_ist}",
        f"Tenders found:    {total}",
        f"New added:        {new}",
        f"Updated:          {updated}",
        f"Skipped:          {skipped}",
        f"Errors:           {failed}",
        f"Captcha solved:   {'Yes' if captcha_solved else 'No'}",
        f"Runtime:          {runtime_str}",
        "================================",
    ]
    for line in summary_lines:
        log.info(line)

    # ── Log to Supabase scraper_runs ──────────────────────────────
    _log_run_to_supabase({
        "run_at":         start_ist.isoformat(),
        "tenders_found":  total,
        "new_added":      new,
        "updated":        updated,
        "skipped":        skipped,
        "errors":         failed,
        "captcha_solved": captcha_solved,
        "runtime_s":      elapsed_s,
        "environment":    "github_actions" if IN_CI else "local",
    })

    if failed > 0 and IN_CI:
        sys.exit(1)


if __name__ == "__main__":
    run()
