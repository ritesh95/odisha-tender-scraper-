import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Field label → schema column mapping
# ---------------------------------------------------------------------------
LABEL_MAP = {
    "Organisation Chain":                  "org_chain",
    "Tender Reference Number":             "ref_number",
    "Tender ID":                           "tender_id",
    "Tender Type":                         "tender_type",
    "Tender Category":                     "tender_category",
    "Form Of Contract":                    "form_of_contract",
    "Tender Value in ₹":                   "tender_value",
    "Product Category":                    "product_category",
    "Location":                            "location",
    "Pincode":                             "pincode",
    "Bid Validity(Days)":                  "bid_validity_days",
    "Period Of Work(Days)":                "period_of_work_days",
    "Published Date":                      "published_date",
    "Bid Opening Date":                    "bid_opening_date",
    "Bid Submission End Date":             "bid_submission_end",
    "Document Download / Sale End Date":   "doc_download_end",
    "EMD Amount in ₹":                     "emd_amount",
    "EMD Exemption Allowed":               "emd_exemption",
    "Tender Fee in ₹":                     "tender_fee",
    "Name":                                "tender_inviting_auth",
    "Title":                               "title",
    "Work Description":                    "work_description",
}

NUMERIC_FIELDS  = {"tender_value", "emd_amount", "tender_fee"}
BOOLEAN_FIELDS  = {"emd_exemption"}
INTEGER_FIELDS  = {"bid_validity_days", "period_of_work_days"}
DATE_FIELDS     = {"published_date", "bid_opening_date", "bid_submission_end", "doc_download_end"}

# ---------------------------------------------------------------------------
# Odisha districts — district is derived primarily from the scraped `location`
# text (authoritative), and only falls back to the pincode-prefix map below.
# ---------------------------------------------------------------------------
ODISHA_DISTRICTS = [
    "Angul", "Balangir", "Balasore", "Bargarh", "Bhadrak", "Boudh",
    "Cuttack", "Deogarh", "Dhenkanal", "Gajapati", "Ganjam",
    "Jagatsinghpur", "Jajpur", "Jharsuguda", "Kalahandi", "Kandhamal",
    "Kendrapara", "Keonjhar", "Khordha", "Koraput", "Malkangiri",
    "Mayurbhanj", "Nabarangpur", "Nayagarh", "Nuapada", "Puri",
    "Rayagada", "Sambalpur", "Subarnapur", "Sundargarh",
]

# Common spelling variants / alternate names / major cities → canonical district.
# Keys are lowercase; matching is case-insensitive and whole-word.
DISTRICT_ALIASES = {
    "sundergarh": "Sundargarh", "sundergad": "Sundargarh", "rourkela": "Sundargarh",
    "rajgangpur": "Sundargarh", "bonai": "Sundargarh",
    "baleswar": "Balasore", "baleshwar": "Balasore",
    "kendujhar": "Keonjhar",
    "jajapur": "Jajpur",
    "baudh": "Boudh",
    "subarnapur": "Subarnapur", "sonepur": "Subarnapur", "sonpur": "Subarnapur",
    "bolangir": "Balangir",
    "nabarangapur": "Nabarangpur",
    "anugul": "Angul",
    "khorda": "Khordha", "khurda": "Khordha", "bhubaneswar": "Khordha", "bhubaneshwar": "Khordha",
    "berhampur": "Ganjam", "brahmapur": "Ganjam",
    "jeypore": "Koraput",
}

# Pincode prefix → district. APPROXIMATE fallback only: a single 3-digit prefix
# in Odisha can span multiple districts, so this is used only when `location`
# yields no match.
PINCODE_DISTRICT = {
    "751": "Khordha",
    "752": "Puri",
    "753": "Cuttack",
    "754": "Cuttack",
    "755": "Jajpur",
    "756": "Balasore",
    "757": "Mayurbhanj",
    "758": "Keonjhar",
    "759": "Dhenkanal",
    "760": "Ganjam",
    "761": "Ganjam",
    "762": "Kandhamal",
    "763": "Koraput",
    "764": "Nabarangpur",
    "765": "Rayagada",
    "766": "Kalahandi",
    "767": "Balangir",
    "768": "Sambalpur",
    "769": "Sundargarh",
    "770": "Sundargarh",
}


def _district_from_location(location):
    """Match a scraped location string to a canonical Odisha district.

    Tries exact district names first, then known aliases / city names.
    Matching is case-insensitive and word-boundary based so 'Sundergarh'
    or 'Rourkela, Sundargarh' both resolve to 'Sundargarh'.
    Returns the canonical district name or None.
    """
    if not location:
        return None
    text = location.lower()

    # Canonical district names (longest first to avoid partial shadowing).
    for district in sorted(ODISHA_DISTRICTS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(district.lower())}\b", text):
            return district

    # Aliases / alternate spellings / major cities.
    for alias, district in DISTRICT_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return district

    return None


# ---------------------------------------------------------------------------
# Field cleaners
# ---------------------------------------------------------------------------

def _clean_numeric(text):
    """'₹ 49,90,000' → 4990000  (int). Returns None if unparseable."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", text)
    if not cleaned:
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def _clean_bool(text):
    """'Yes' → True, 'No' → False, anything else → None."""
    if not text:
        return None
    t = text.strip().lower()
    if t == "yes":
        return True
    if t == "no":
        return False
    return None


def _clean_int(text):
    """'90' or '90 days' → 90. Returns None if unparseable."""
    if not text:
        return None
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def _clean_date(text):
    """'09-Jun-2026 09:00 AM' → '2026-06-09T09:00:00'. Returns None if unparseable."""
    if not text or text.strip().upper() in ("NA", "NIL", "N/A", ""):
        return None
    for fmt in ("%d-%b-%Y %I:%M %p", "%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).isoformat()
        except ValueError:
            continue
    return None


def _clean_text(text):
    """Return stripped text or None if empty / NA."""
    if not text:
        return None
    t = text.strip()
    return None if t.upper() in ("NA", "NIL", "N/A", "") else t


# ---------------------------------------------------------------------------
# HTML extraction helpers
# ---------------------------------------------------------------------------

def _extract_label_values(soup):
    """
    Collect all td.td_caption → td.td_field pairs in document order.
    Returns a list of (label, value) so duplicate labels are preserved.
    """
    pairs = []
    for caption in soup.find_all("td", class_="td_caption"):
        label = caption.get_text(separator=" ", strip=True)
        nxt = caption.find_next_sibling("td")
        if nxt and "td_field" in (nxt.get("class") or []):
            value = nxt.get_text(separator=" ", strip=True)
            pairs.append((label, value))
    return pairs


def _extract_nit_documents(soup):
    """
    Parse table#table for NIT documents.
    Returns list of {"name": str, "size_kb": float}.
    """
    docs = []
    table = soup.find("table", id="table")
    if not table:
        return docs
    for row in table.find_all("tr"):
        tds = row.find_all("td")
        # Expected columns: S.No | Document Name | Description | Size (KB)
        if len(tds) < 4:
            continue
        name = tds[1].get_text(strip=True)
        size_text = tds[3].get_text(strip=True)
        if not name or name.lower() in ("document name", "s.no"):
            continue
        try:
            size_kb = float(re.sub(r"[^\d.]", "", size_text)) if size_text else None
        except ValueError:
            size_kb = None
        if name:
            docs.append({"name": name, "size_kb": size_kb})
    return docs


def _extract_boq_documents(soup):
    """
    Parse table#workItemDocumenttable for BOQ/work-item documents.
    Returns list of {"type": str, "name": str, "size_kb": float}.
    """
    docs = []
    table = soup.find("table", id="workItemDocumenttable")
    if not table:
        return docs
    for row in table.find_all("tr"):
        tds = row.find_all("td")
        # Expected columns: S.No | Document Type | Document Name | Description | Size (KB)
        if len(tds) < 5:
            continue
        doc_type = tds[1].get_text(strip=True)
        name     = tds[2].get_text(strip=True)
        size_text = tds[4].get_text(strip=True)
        if not name or name.lower() in ("document name",):
            continue
        try:
            size_kb = float(re.sub(r"[^\d.]", "", size_text)) if size_text else None
        except ValueError:
            size_kb = None
        if name:
            docs.append({"type": doc_type or None, "name": name, "size_kb": size_kb})
    return docs


# ---------------------------------------------------------------------------
# Main parse function
# ---------------------------------------------------------------------------

def parse_tender_html(html, source_url=""):
    """
    Parse a tender detail page HTML string.
    Returns a cleaned dict ready for Supabase upsert, or None if tender_id missing.
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:
        print(f"  ❌ BeautifulSoup parse error: {e}")
        return None

    pairs = _extract_label_values(soup)

    # Build raw dict — later labels for the same key overwrite earlier ones,
    # EXCEPT for "Title" and "Name" which appear multiple times and we want
    # the last occurrence (inside Work Item Details / Tender Inviting Authority).
    raw = {}
    for label, value in pairs:
        if label in LABEL_MAP:
            raw[LABEL_MAP[label]] = value

    data = {}

    # Text fields
    for col in ("tender_id", "ref_number", "org_chain", "tender_type",
                "tender_category", "form_of_contract", "product_category",
                "location", "pincode", "title", "work_description",
                "tender_inviting_auth"):
        try:
            data[col] = _clean_text(raw.get(col))
        except Exception:
            data[col] = None

    # Numeric → int
    for col in NUMERIC_FIELDS:
        try:
            data[col] = _clean_numeric(raw.get(col))
        except Exception:
            data[col] = None

    # Integer fields
    for col in INTEGER_FIELDS:
        try:
            data[col] = _clean_int(raw.get(col))
        except Exception:
            data[col] = None

    # Boolean fields
    for col in BOOLEAN_FIELDS:
        try:
            data[col] = _clean_bool(raw.get(col))
        except Exception:
            data[col] = None

    # Date fields
    for col in DATE_FIELDS:
        try:
            data[col] = _clean_date(raw.get(col))
        except Exception:
            data[col] = None

    # Documents
    try:
        data["nit_documents"] = _extract_nit_documents(soup)
    except Exception:
        data["nit_documents"] = []

    try:
        data["boq_documents"] = _extract_boq_documents(soup)
    except Exception:
        data["boq_documents"] = []

    # Placeholders for derived fields (filled by derive_fields)
    data["dept_short"]       = None
    data["work_type"]        = None
    data["district"]         = None
    data["value_band"]       = None
    data["contractor_class"] = None

    # Metadata
    data["corrigendum_count"] = 0
    data["is_active"]         = True
    data["source_url"]        = source_url or None
    data["scraped_at"]        = datetime.utcnow().isoformat()

    if not data.get("tender_id"):
        return None

    return data


# ---------------------------------------------------------------------------
# Derived / computed fields
# ---------------------------------------------------------------------------

def derive_fields(data):
    """Add dept_short, work_type, district, value_band computed fields."""
    if not data:
        return data

    # dept_short from org_chain
    org = data.get("org_chain") or ""
    org_u = org.upper()
    if org_u.startswith("CE RW"):
        dept = "RW"
    elif org_u.startswith("MUNICIPAL BODIES") or "ORULB" in org_u:
        dept = "ULB"
    elif "CE-BM" in org_u or "BASIN" in org_u:
        dept = "BM"
    elif org_u.startswith("EIC-CIVIL") or "EIC" in org_u:
        dept = "CIVIL"
    elif "MINOR IRRIGATION" in org_u:
        dept = "MI"
    elif "GROUND WATER" in org_u:
        dept = "GWSI"
    elif "DEVELOPMENT AUTHORITY" in org_u or "BDA" in org_u:
        dept = "BDA"
    elif "PHEO" in org_u:
        dept = "PHEO"
    elif "BRIDGE AND CONSTRUCTION" in org_u or "OBCC" in org_u:
        dept = "OBCC"
    elif "CONSTRUCTION CORPORATION" in org_u:
        dept = "OCC"
    elif "OPEPA" in org_u or "SAMAGRA SHIKSHA" in org_u:
        dept = "OPEPA"
    elif "OPHWC" in org_u:
        dept = "OPHWC"
    elif "WATER RESOURCES" in org_u:
        dept = "WR"
    elif "FOREST" in org_u:
        dept = "FOREST"
    elif "HEALTH" in org_u or "MEDICAL" in org_u:
        dept = "HEALTH"
    else:
        dept = "OTHER"
    data["dept_short"] = dept

    # work_type from title
    title = (data.get("title") or "").upper()
    if any(k in title for k in ("ROAD", "PAVEMENT", "PAVER")):
        wt = "Road"
    elif any(k in title for k in ("BUILDING", "SCHOOL", "OFFICE", "HOSTEL", "HOSPITAL")):
        wt = "Building"
    elif any(k in title for k in ("BRIDGE", "CULVERT")):
        wt = "Bridge"
    elif any(k in title for k in ("ELECTRICAL", "ELECTRIFICATION")):
        wt = "Electrical"
    elif any(k in title for k in ("WATER", "PIPELINE", "BOREHOLE", "TUBE WELL")):
        wt = "Water"
    elif any(k in title for k in ("DRAIN", "DRAINAGE", "SEWER")):
        wt = "Drainage"
    else:
        wt = "Other"
    data["work_type"] = wt

    # district: prefer the scraped location text (authoritative), then fall
    # back to the approximate pincode-prefix map.
    district = _district_from_location(data.get("location"))
    if not district:
        pincode = data.get("pincode") or ""
        district = PINCODE_DISTRICT.get(pincode[:3]) if len(pincode) >= 3 else None
    data["district"] = district

    # value_band from tender_value
    val = data.get("tender_value")
    if val is None:
        band = None
    elif val < 500_000:
        band = "Under 5L"
    elif val < 5_000_000:
        band = "5L-50L"
    elif val < 50_000_000:
        band = "50L-5Cr"
    else:
        band = "Above 5Cr"
    data["value_band"] = band

    return data


# ---------------------------------------------------------------------------
# Supabase upsert
# ---------------------------------------------------------------------------

SCHEMA_COLUMNS = {
    "tender_id", "ref_number", "org_chain", "dept_short", "title",
    "work_description", "tender_type", "tender_category", "tender_value",
    "value_band", "product_category", "location", "district", "pincode",
    "contractor_class", "work_type", "emd_amount", "emd_exemption",
    "tender_fee", "bid_validity_days", "period_of_work_days",
    "published_date", "bid_submission_end", "bid_opening_date",
    "doc_download_end", "tender_inviting_auth", "nit_documents",
    "boq_documents", "corrigendum_count", "is_active", "source_url",
    "scraped_at",
}


def upsert_tender(data):
    """
    Upsert a single tender record.
    Returns 'new' if inserted for the first time, 'updated' if it already existed,
    or False on error.
    """
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from db.supabase_client import supabase

        tid = data["tender_id"]
        row = {k: v for k, v in data.items() if k in SCHEMA_COLUMNS}

        # Check if already exists
        existing = supabase.table("tenders").select("tender_id").eq("tender_id", tid).execute()
        is_new = len(existing.data) == 0

        supabase.table("tenders").upsert(row, on_conflict="tender_id").execute()
        status = "new" if is_new else "updated"
        print(f"  ✅ {status}: {tid}")
        return status
    except Exception as e:
        print(f"  ❌ upsert failed for {data.get('tender_id')}: {e}")
        return False


# ---------------------------------------------------------------------------
# Top-level pipeline step
# ---------------------------------------------------------------------------

def process_tender(html, source_url=""):
    """Parse → derive → upsert one tender. Returns True on success."""
    data = parse_tender_html(html, source_url)
    if not data:
        print("  ⚠️  skipped — no tender_id found")
        return False

    data = derive_fields(data)

    # Summary line
    try:
        if data.get("bid_submission_end"):
            deadline = datetime.fromisoformat(data["bid_submission_end"])
            days_left = (deadline - datetime.utcnow()).days
        else:
            days_left = "?"
        print(
            f"  📄 {data['tender_id']} | {data.get('dept_short')} | "
            f"{data.get('value_band')} | {days_left} days left"
        )
    except Exception:
        pass

    return upsert_tender(data)  # 'new', 'updated', or False


# ---------------------------------------------------------------------------
# Manual test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    with open("test_tender.html", "r", encoding="utf-8") as f:
        html = f.read()

    result = parse_tender_html(html, "https://tendersodisha.gov.in/test")
    if not result:
        print("❌ parse_tender_html returned None — tender_id not found")
        raise SystemExit(1)

    result = derive_fields(result)

    print(json.dumps(result, indent=2, default=str))
    print("\n--- Upserting to Supabase ---")
    success = upsert_tender(result)
    print(f"Upsert result: {success}")
