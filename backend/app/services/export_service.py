from __future__ import annotations

import csv
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import ExportLog
from app.services.research_query import compute_dashboard_statistics, query_research_leads

EXCEL_COLUMNS: list[tuple[str, str]] = [
    ("Lead ID", "lead_id"),
    ("Podcast Name", "podcast_name"),
    ("Episode Title", "episode_title"),
    ("LinkedIn Post URL", "linkedin_post_url"),
    ("Video Posting Date", "video_posting_date"),
    ("YouTube Channel Name", "youtube_channel_name"),
    ("YouTube Channel URL", "youtube_channel_url"),
    ("Original Podcast URL", "original_podcast_url"),
    ("Host Full Name", "host_full_name"),
    ("Host Designation", "host_designation"),
    ("Host LinkedIn URL", "host_linkedin_url"),
    ("Host Company", "host_company"),
    ("Company LinkedIn URL", "company_linkedin_url"),
    ("Company Website", "company_website"),
    ("Company Location", "company_location"),
    ("Business Email", "business_email"),
    ("Email Category", "email_category"),
    ("Phone", "phone"),
    ("Contact Source", "contact_source"),
    ("Contact Source URL", "contact_source_url"),
    ("Video Quality Score", "video_quality_score"),
    ("Video Quality", "video_quality"),
    ("Audio Quality", "audio_quality"),
    ("Lighting", "lighting"),
    ("Podcast Setup", "podcast_setup"),
    ("Content Relevance", "content_relevance"),
    ("Qualification Status", "qualification_status"),
    ("Identity Verification Status", "identity_verification_status"),
    ("Contact Verification Status", "contact_verification_status"),
    ("Confidence Score", "confidence_score"),
    ("Research Date", "research_date"),
    ("Research Notes", "research_notes"),
    ("Search Keyword / Niche", "search_keyword"),
]

URL_FIELDS = {
    "linkedin_post_url",
    "youtube_channel_url",
    "original_podcast_url",
    "host_linkedin_url",
    "company_linkedin_url",
    "company_website",
    "contact_source_url",
}

STATUS_FIELDS = {
    "qualification_status",
    "identity_verification_status",
    "contact_verification_status",
}

STATUS_STYLES: dict[str, tuple[str, str]] = {
    "Verified": ("166534", "DCFCE7"),
    "Qualified": ("166534", "DCFCE7"),
    "Partially Verified": ("854D0E", "FEF9C3"),
    "Possible Match": ("854D0E", "FEF9C3"),
    "Manual Review": ("9A3412", "FFEDD5"),
    "Manual Review Required": ("9A3412", "FFEDD5"),
    "Unverified": ("475569", "F1F5F9"),
    "Rejected": ("991B1B", "FEE2E2"),
}


def sanitize_spreadsheet_cell(value: Any) -> Any:
    """Protect against CSV/Excel formula injection (Section 9E)."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def _is_safe_http_url(val: Any) -> bool:
    if not isinstance(val, str):
        return False
    lower = val.strip().lower()
    return lower.startswith("http://") or lower.startswith("https://")


def _write_leads_worksheet(ws: Any, rows: list[dict[str, Any]]) -> None:
    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    link_font = Font(name="Calibri", size=10, color="1D4ED8", underline="single")
    body_font = Font(name="Calibri", size=10, color="0F172A")

    headers = [col_label for col_label, _ in EXCEL_COLUMNS]
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 24

    for row_idx, rec in enumerate(rows, start=2):
        for col_idx, (_, key) in enumerate(EXCEL_COLUMNS, start=1):
            raw_val = rec.get(key)
            cell = ws.cell(row=row_idx, column=col_idx)

            if key == "research_date" and isinstance(raw_val, datetime):
                cell.value = raw_val.replace(tzinfo=None)
                cell.number_format = "yyyy-mm-dd"
                cell.font = body_font
            elif key in URL_FIELDS and _is_safe_http_url(raw_val):
                safe_url = str(raw_val).strip()
                cell.value = sanitize_spreadsheet_cell(safe_url)
                cell.hyperlink = safe_url
                cell.font = link_font
            else:
                cell.value = sanitize_spreadsheet_cell(raw_val)
                cell.font = body_font

            if key in STATUS_FIELDS and str(raw_val) in STATUS_STYLES:
                fg, bg = STATUS_STYLES[str(raw_val)]
                cell.font = Font(name="Calibri", size=10, bold=True, color=fg)
                cell.fill = PatternFill(start_color=bg, end_color=bg, fill_type="solid")

            cell.alignment = Alignment(vertical="center", wrap_text=(key == "research_notes"))

    ws.freeze_panes = "A2"
    last_col = get_column_letter(len(EXCEL_COLUMNS))
    last_row = max(1, len(rows) + 1)
    ws.auto_filter.ref = f"A1:{last_col}{last_row}"

    for col_idx, (label, key) in enumerate(EXCEL_COLUMNS, start=1):
        max_len = len(label)
        for rec in rows[:200]:
            val = rec.get(key)
            val_len = len(str(val or ""))
            if val_len > max_len:
                max_len = val_len
        width = min(48, max(14, max_len + 4))
        if key == "research_notes":
            width = 45
        ws.column_dimensions[get_column_letter(col_idx)].width = width


def _write_summary_worksheet(ws: Any, stats: dict[str, int], exported_count: int, filter_summary: str) -> None:
    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    label_font = Font(name="Calibri", size=11, bold=True, color="0F172A")
    val_font = Font(name="Calibri", size=11, color="0F172A")

    ws.append(["Jarvis AI — Podcast Host Research Summary", "Value"])
    for col_idx in (1, 2):
        c = ws.cell(row=1, column=col_idx)
        c.fill = header_fill
        c.font = header_font

    summary_rows = [
        ("Export Generated (UTC)", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
        ("Applied Filters / Preset", filter_summary),
        ("Records Included in Export", exported_count),
        ("Total Discovered LinkedIn Posts", stats["linkedin_videos_discovered"]),
        ("Qualified Podcasts", stats["qualified_podcasts"]),
        ("Rejected Videos", stats["rejected_videos"]),
        ("Hosts Identified", stats["hosts_identified"]),
        ("Companies Identified", stats["companies_identified"]),
        ("Emails Discovered", stats["emails_discovered"]),
        ("Verified Contacts", stats["verified_contacts"]),
        ("Pending Manual Reviews", stats["pending_manual_reviews"]),
    ]
    for r_idx, (k, v) in enumerate(summary_rows, start=2):
        c1 = ws.cell(row=r_idx, column=1, value=k)
        c2 = ws.cell(row=r_idx, column=2, value=sanitize_spreadsheet_cell(v))
        c1.font = label_font
        c2.font = val_font

    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 42
    ws.freeze_panes = "A2"


def generate_excel_export(
    db: Session,
    filters: dict[str, Any] | None = None,
    agency_id: str = "default",
) -> ExportLog:
    settings = get_settings()
    settings.exports_dir.mkdir(parents=True, exist_ok=True)
    f = dict(filters or {})
    preset = str(f.get("preset") or "all")

    leads = query_research_leads(
        db=db,
        preset=preset,
        qualification_status=f.get("qualification_status"),
        identity_verification_status=f.get("identity_verification_status"),
        contact_verification_status=f.get("contact_verification_status"),
        has_email=f.get("has_email"),
        company=f.get("company"),
        date_from=f.get("date_from"),
        date_to=f.get("date_to"),
        min_quality_score=f.get("min_quality_score"),
        research_task_id=f.get("research_task_id"),
        selected_ids=f.get("selected_ids"),
        search=f.get("search"),
        agency_id=agency_id,
    )
    stats = compute_dashboard_statistics(db, agency_id=agency_id)

    wb = Workbook()
    ws_all = wb.active
    ws_all.title = "All Leads"
    _write_leads_worksheet(ws_all, leads)

    verified_rows = [
        r
        for r in leads
        if r["identity_verification_status"] == "Verified"
        and r["contact_verification_status"] == "Verified"
    ]
    ws_verified = wb.create_sheet("Verified Leads")
    _write_leads_worksheet(ws_verified, verified_rows)

    email_rows = [r for r in leads if r.get("business_email")]
    ws_email = wb.create_sheet("Email Available")
    _write_leads_worksheet(ws_email, email_rows)

    manual_rows = [
        r
        for r in leads
        if r["manual_review_required"]
        or r["qualification_status"] == "Manual Review"
        or r["identity_verification_status"] in ("Manual Review Required", "Possible Match", "Unverified")
        or r["contact_verification_status"] in ("Manual Review Required", "Possible Match")
    ]
    ws_manual = wb.create_sheet("Manual Review")
    _write_leads_worksheet(ws_manual, manual_rows)

    ws_summary = wb.create_sheet("Research Summary")
    _write_summary_worksheet(ws_summary, stats, len(leads), f"preset={preset}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    uid = uuid.uuid4().hex[:6]

    kw_target = f.get("keyword") or f.get("search")
    if not kw_target and f.get("research_task_id"):
        try:
            from app.db.models import ResearchTask
            t = db.query(ResearchTask).filter(ResearchTask.id == int(f["research_task_id"])).first()
            if t and t.search_keyword:
                kw_target = t.search_keyword
        except Exception:
            pass

    if kw_target and str(kw_target).strip() and str(kw_target).lower() not in ("all", "all leads", "default", "none"):
        clean_kw = "".join(c if c.isalnum() else "_" for c in str(kw_target).strip()).strip("_")[:35]
        clean_kw = "_".join(part for part in clean_kw.split("_") if part)
        filename = f"Jarvis_{clean_kw}_Leads_{today}_{uid}.xlsx"
    else:
        filename = f"Jarvis_Podcast_Host_Research_{today}_{uid}.xlsx"

    target_path = (settings.exports_dir / filename).resolve()
    wb.save(str(target_path))

    log = ExportLog(
        agency_id=agency_id,
        export_format="xlsx",
        filename=filename,
        file_path=str(target_path),
        filter_preset=preset,
        filters_json=f,
        record_count=len(leads),
        status="completed",
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def generate_csv_export(
    db: Session,
    filters: dict[str, Any] | None = None,
    agency_id: str = "default",
) -> ExportLog:
    settings = get_settings()
    settings.exports_dir.mkdir(parents=True, exist_ok=True)
    f = dict(filters or {})
    preset = str(f.get("preset") or "all")

    leads = query_research_leads(
        db=db,
        preset=preset,
        qualification_status=f.get("qualification_status"),
        identity_verification_status=f.get("identity_verification_status"),
        contact_verification_status=f.get("contact_verification_status"),
        has_email=f.get("has_email"),
        company=f.get("company"),
        date_from=f.get("date_from"),
        date_to=f.get("date_to"),
        min_quality_score=f.get("min_quality_score"),
        research_task_id=f.get("research_task_id"),
        selected_ids=f.get("selected_ids"),
        search=f.get("search"),
        agency_id=agency_id,
    )

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    uid = uuid.uuid4().hex[:6]

    kw_target = f.get("keyword") or f.get("search")
    if not kw_target and f.get("research_task_id"):
        try:
            from app.db.models import ResearchTask
            t = db.query(ResearchTask).filter(ResearchTask.id == int(f["research_task_id"])).first()
            if t and t.search_keyword:
                kw_target = t.search_keyword
        except Exception:
            pass

    if kw_target and str(kw_target).strip() and str(kw_target).lower() not in ("all", "all leads", "default", "none"):
        clean_kw = "".join(c if c.isalnum() else "_" for c in str(kw_target).strip()).strip("_")[:35]
        clean_kw = "_".join(part for part in clean_kw.split("_") if part)
        filename = f"Jarvis_{clean_kw}_Leads_{today}_{uid}.csv"
    else:
        filename = f"Jarvis_Podcast_Host_Research_{today}_{uid}.csv"

    target_path = (settings.exports_dir / filename).resolve()

    with Path(target_path).open("w", newline="", encoding="utf-8-sig") as fp:
        writer = csv.writer(fp)
        writer.writerow([label for label, _ in EXCEL_COLUMNS])
        for rec in leads:
            writer.writerow([sanitize_spreadsheet_cell(rec.get(key)) for _, key in EXCEL_COLUMNS])

    log = ExportLog(
        agency_id=agency_id,
        export_format="csv",
        filename=filename,
        file_path=str(target_path),
        filter_preset=preset,
        filters_json=f,
        record_count=len(leads),
        status="completed",
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log

