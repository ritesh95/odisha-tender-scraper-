"""
backfill_district.py — recompute the `district` column for existing tenders.

The district was previously derived from the pincode prefix alone, which
misclassified rows (e.g. 769xxx -> "Jharsuguda" instead of "Sundargarh").
This one-off script recomputes district using the corrected logic in
scrapers/detail.py (location text first, pincode prefix as fallback) and
updates only the rows whose district actually changed.

Run:
  python scripts/backfill_district.py            # apply changes
  python scripts/backfill_district.py --dry-run  # report only, no writes
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scrapers.detail import _derive_district
from db.supabase_client import supabase
from utils.logger import get_logger

log = get_logger()

PAGE_SIZE = 1000


def recompute_district(location, pincode):
    """Same precedence as scrapers.detail.derive_fields: pincode map, then location."""
    return _derive_district(pincode, location)


def fetch_all_rows():
    """Page through every tender row, returning id/location/pincode/district."""
    rows = []
    start = 0
    while True:
        resp = (
            supabase.table("tenders")
            .select("tender_id, location, pincode, district")
            .range(start, start + PAGE_SIZE - 1)
            .execute()
        )
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return rows


def main():
    dry_run = "--dry-run" in sys.argv

    log.info("=" * 60)
    log.info("District backfill — %s", "DRY RUN (no writes)" if dry_run else "APPLYING changes")
    log.info("=" * 60)

    rows = fetch_all_rows()
    log.info("Fetched %d tender rows", len(rows))

    changed = 0
    cleared = 0
    failed = 0

    for r in rows:
        tid = r.get("tender_id")
        old = r.get("district")
        new = recompute_district(r.get("location"), r.get("pincode"))

        if new == old:
            continue

        log.info("  %s: %r -> %r  (location=%r, pincode=%r)",
                 tid, old, new, r.get("location"), r.get("pincode"))

        if new is None:
            cleared += 1
        changed += 1

        if dry_run:
            continue

        try:
            supabase.table("tenders").update({"district": new}).eq("tender_id", tid).execute()
        except Exception as e:
            log.error("  update failed for %s: %s", tid, e)
            failed += 1

    log.info("-" * 60)
    log.info("Rows scanned:  %d", len(rows))
    log.info("Would change:  %d%s", changed, "" if dry_run else " (applied)")
    log.info("Set to NULL:   %d", cleared)
    if not dry_run:
        log.info("Update errors: %d", failed)
    log.info("Done.")


if __name__ == "__main__":
    main()
