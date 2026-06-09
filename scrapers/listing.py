import time
import re
import os
from datetime import datetime, date
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from twocaptcha import TwoCaptcha

load_dotenv()

IN_CI = os.environ.get("GITHUB_ACTIONS") == "true"

BASE_URL = "https://tendersodisha.gov.in"
LISTING_URL = f"{BASE_URL}/nicgep/app?page=FrontEndLatestActiveTenders&service=page"
NEXT_URL    = f"{BASE_URL}/nicgep/app?component=loadNext&page=FrontEndLatestActiveTenders&service=direct&session=T"
USER_AGENT  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
MAX_CAPTCHA_RETRIES = 3


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def _solve_captcha(solver, page):
    """Extract inline base64 captcha image and solve via 2captcha. Returns text or None."""
    img_el = page.query_selector("img#captchaImage")
    if not img_el:
        print(f"[{_ts()}] ❌ Captcha image element not found")
        return None

    src = img_el.get_attribute("src") or ""
    b64 = re.sub(r"^data:image/[^;]+;base64,", "", src)
    if not b64:
        print(f"[{_ts()}] ❌ Captcha src has no base64 data")
        return None

    print(f"[{_ts()}] Sending captcha to 2captcha (~15s)...")
    try:
        result = solver.normal(b64, caseSensitive=1, minLen=4, maxLen=8)
        text = result.get("code", "").strip()
        print(f"[{_ts()}] 2captcha solved: \"{text}\"")
        return text
    except Exception as e:
        print(f"[{_ts()}] ❌ 2captcha error: {e}")
        return None


def _submit_form(page, captcha_text):
    """Fill captcha and submit the search form. Returns True if navigation happened."""
    page.evaluate("document.querySelector('input[name=\"size\"][value=\"0\"]').click()")
    page.fill("input#captchaText", captcha_text)
    try:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=20000):
            page.click("input#Submit")
        return True
    except PlaywrightTimeoutError:
        print(f"[{_ts()}] ❌ Form submit navigation timed out")
        return False


def _extract_rows(page):
    """
    Return list of (published_date_str, full_url) for every tender row on the
    current results page. published_date_str is like '09-Jun-2026 05:00 PM'.
    """
    rows = page.query_selector_all("tr[id^='informal_']")
    items = []
    for row in rows:
        tds = row.query_selector_all("td")
        if len(tds) < 5:
            continue
        pub_date_text = tds[1].inner_text().strip()     # column 2 = Published Date
        link_el = tds[4].query_selector("a[href*='%24DirectLink']")
        if not link_el:
            continue
        href = link_el.get_attribute("href") or ""
        full_url = href if href.startswith("http") else BASE_URL + href
        items.append((pub_date_text, full_url))
    return items


def _is_today(date_text, target_date):
    """Return True if date_text ('09-Jun-2026 05:00 PM') matches target_date (date obj)."""
    try:
        dt = datetime.strptime(date_text.strip(), "%d-%b-%Y %I:%M %p")
        return dt.date() == target_date
    except ValueError:
        return False


def run_listing_scraper(target_date=None):
    """
    Scrape all tenders published on target_date (defaults to today).
    Paginates automatically — no extra CAPTCHA needed for Next pages.
    Returns list of (url, html) tuples.
    """
    if target_date is None:
        target_date = date.today()

    api_key = os.getenv("CAPTCHA_API_KEY")
    if not api_key:
        raise ValueError("Missing CAPTCHA_API_KEY in .env")

    solver  = TwoCaptcha(api_key)
    results = []

    playwright = sync_playwright().start()
    try:
        # In CI use system Chrome (avoids playwright install-deps issues on Ubuntu 24.04)
        launch_opts = {"headless": True}
        if IN_CI:
            launch_opts["channel"] = "chrome"
        browser = playwright.chromium.launch(**launch_opts)
        # browser = playwright.chromium.launch(headless=False)  # debug
        context = browser.new_context(user_agent=USER_AGENT)
        page    = context.new_page()

        print(f"[{_ts()}] Target date: {target_date.strftime('%d-%b-%Y')}")
        print(f"[{_ts()}] Opening listing page...")
        try:
            page.goto(LISTING_URL, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeoutError:
            print(f"[{_ts()}] ❌ Timeout loading listing page")
            return []

        # ── Solve CAPTCHA (one time only) ──────────────────────────────────
        today_urls = []
        for attempt in range(1, MAX_CAPTCHA_RETRIES + 1):
            print(f"[{_ts()}] --- Captcha attempt {attempt}/{MAX_CAPTCHA_RETRIES} ---")

            captcha_text = _solve_captcha(solver, page)
            if not captcha_text:
                page.goto(LISTING_URL, wait_until="networkidle", timeout=30000)
                continue

            if not _submit_form(page, captcha_text):
                page.goto(LISTING_URL, wait_until="networkidle", timeout=30000)
                continue

            error_el = page.query_selector("span.error b, td.error b")
            if error_el:
                print(f"[{_ts()}] Server error: \"{error_el.inner_text().strip()}\"")
                page.goto(LISTING_URL, wait_until="networkidle", timeout=30000)
                continue

            # First page loaded — start collecting
            page_num = 1
            while True:
                rows = _extract_rows(page)
                if not rows:
                    print(f"[{_ts()}] No rows on page {page_num} — stopping")
                    break

                matched = [(d, u) for d, u in rows if _is_today(d, target_date)]
                print(f"[{_ts()}] Page {page_num}: {len(rows)} rows, {len(matched)} from {target_date}")
                today_urls.extend(u for _, u in matched)

                # If fewer rows matched than total, we've passed today's tenders
                if len(matched) < len(rows):
                    print(f"[{_ts()}] Hit tenders from earlier date — done paginating")
                    break

                # Check if a Next button exists
                next_el = page.query_selector("a[href*='loadNext']")
                if not next_el:
                    print(f"[{_ts()}] No Next button — end of results")
                    break

                # Click Next (no CAPTCHA required)
                print(f"[{_ts()}] Clicking Next → page {page_num + 1}...")
                try:
                    with page.expect_navigation(wait_until="domcontentloaded", timeout=20000):
                        next_el.click()
                    page_num += 1
                except PlaywrightTimeoutError:
                    print(f"[{_ts()}] ❌ Next page navigation timed out")
                    break

            break  # captcha succeeded, exit retry loop

        if not today_urls:
            print(f"[{_ts()}] ❌ No tenders found for {target_date}")
            return []

        print(f"[{_ts()}] ✅ {len(today_urls)} tenders from {target_date} — fetching detail pages...")

        # ── Fetch detail pages in the same session ─────────────────────────
        for i, url in enumerate(today_urls, 1):
            print(f"[{_ts()}] [{i}/{len(today_urls)}] Fetching detail page...")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                html = page.content()
                if len(html) < 1000:
                    print(f"[{_ts()}]    ⚠️  HTML too short ({len(html)} chars) — skipping")
                    results.append((url, None))
                else:
                    print(f"[{_ts()}]    Preview: {html[:120]}...")
                    results.append((url, html))
            except Exception as e:
                print(f"[{_ts()}]    ❌ {e}")
                results.append((url, None))

    finally:
        try:
            context.close()
            browser.close()
        except Exception:
            pass
        playwright.stop()

    return results


if __name__ == "__main__":
    results = run_listing_scraper()
    successful = [r for r in results if r[1]]
    print(f"\nTotal detail pages fetched: {len(successful)}/{len(results)}")
