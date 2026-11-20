from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from openpyxl import load_workbook
from PIL import Image

from app.db.models import ResearchTask
from app.db.session import SessionLocal
from app.services.contact_discovery import discover_host_contacts
from app.services.export_service import EXCEL_COLUMNS, sanitize_spreadsheet_cell
from app.services.research_workflow import workflow_manager


def _create_sample_frame(path: Path, brightness: int = 135) -> str:
    img = Image.new("RGB", (1280, 720), color=(brightness, brightness, brightness))
    for x in range(200, 600):
        for y in range(100, 500):
            img.putpixel((x, y), (30, 50, 90))
    img.save(path, format="PNG")
    return str(path)


@pytest.mark.asyncio
async def test_full_podcast_host_pipeline_dedup_review_and_exports(async_client, test_workspace: Path):
    # 1. Empty results & missing export handling (#22)
    empty_xlsx = await async_client.get("/api/v1/export/excel")
    assert empty_xlsx.status_code == 200
    assert empty_xlsx.headers.get("X-Export-Record-Count") == "0"

    empty_csv = await async_client.get("/api/v1/export/csv")
    assert empty_csv.status_code == 200
    assert empty_csv.headers.get("X-Export-Record-Count") == "0"

    missing_dl = await async_client.get("/api/v1/export/download/999999")
    assert missing_dl.status_code == 404

    # 2. Run pipeline on qualified podcast post & non-podcast rejected post (#4, #5, #6, #7, #11, #12)
    frame_ok = _create_sample_frame(test_workspace / "data" / "screenshots" / "good_frame.png", 145)
    frame_bad = _create_sample_frame(test_workspace / "data" / "screenshots" / "bad_frame.png", 20)

    db = SessionLocal()
    try:
        task = ResearchTask(
            user_instruction="Find real estate podcasts on LinkedIn",
            search_keyword="Real Estate Podcast",
            task_status="running",
            progress=50,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        qualified_post = {
            "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:9001?utm_source=share",
            "post_caption": (
                "Episode 12 of the Capital Property Podcast! Hosted by Marcus Vance, "
                "Founder at Vance Commercial Advisors. Today we welcome special guest Sarah Jenkins. "
                "Watch on YouTube: https://www.youtube.com/@CapitalPropertyPodcast "
                "Company site: https://vancecommercial.example "
                "Business inquiries: marcus@vancecommercial.example"
            ),
            "posting_account": "Marcus Vance",
            "posting_account_url": "https://www.linkedin.com/in/marcus-vance-re?trk=feed",
            "video_url": "https://cdn.linkedin.example/video1.mp4",
            "published_label": "1d",
            "keywords_matched": ["real", "estate", "podcast"],
            "external_urls": [
                "https://www.youtube.com/@CapitalPropertyPodcast",
                "https://vancecommercial.example",
            ],
            "comments": [],
        }
        res1 = await workflow_manager.process_single_post(
            db=db,
            task_id=task.id,
            post_data=qualified_post,
            quality_threshold=65,
            frame_paths=[frame_ok],
            video_meta={"found": True, "videoWidth": 1280, "videoHeight": 720},
            audio_accessible=False,  # Audio not accessible -> MUST be 'Unknown'
            allow_live_browser=False,
        )
        assert res1["status"] == "Qualified"
        assert res1["host_name"] == "Marcus Vance"
        assert res1["host_name"] != "Sarah Jenkins"
        assert res1["email"] == "marcus@vancecommercial.example"

        # Duplicate detection check (same URL with different tracking param)
        dup_post = dict(qualified_post)
        dup_post["post_url"] = "https://www.linkedin.com/feed/update/urn:li:activity:9001?utm_medium=copy"
        res_dup = await workflow_manager.process_single_post(
            db=db,
            task_id=task.id,
            post_data=dup_post,
            quality_threshold=65,
            frame_paths=[frame_ok],
            video_meta={"found": True, "videoWidth": 1280, "videoHeight": 720},
            audio_accessible=False,
            allow_live_browser=False,
        )
        assert res_dup["post_id"] == res1["post_id"]

        # Non-podcast rejected post (and formula-injection string)
        rejected_post = {
            "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:9002",
            "post_caption": "=CMD('calc') Just checking out a new property listing tour today.",
            "posting_account": "Random Listing Page",
            "posting_account_url": "https://www.linkedin.com/company/random-listing",
            "video_url": None,
            "published_label": "3d",
            "keywords_matched": ["property"],
            "external_urls": [],
            "comments": [],
        }
        res2 = await workflow_manager.process_single_post(
            db=db,
            task_id=task.id,
            post_data=rejected_post,
            quality_threshold=65,
            frame_paths=[frame_bad],
            video_meta={"found": False, "videoWidth": 320, "videoHeight": 240},
            audio_accessible=False,
            allow_live_browser=False,
        )
        assert res2["status"] == "Rejected"

        task.task_status = "completed"
        task.progress = 100
        db.commit()
    finally:
        db.close()

    # 3. Verify audio_quality == "Unknown" and host/guest separation
    results_resp = await async_client.get("/api/v1/research/results")
    assert results_resp.status_code == 200
    rows = results_resp.json()
    assert len(rows) == 2

    qualified_row = next(r for r in rows if r["qualification_status"] == "Qualified")
    assert qualified_row["audio_quality"] == "Unknown"
    assert qualified_row["host_full_name"] == "Marcus Vance"
    assert qualified_row["host_company"] == "Vance Commercial Advisors"
    assert qualified_row["business_email"] == "marcus@vancecommercial.example"
    assert qualified_row["email_category"] == "host_direct_business"

    # 4. Dashboard statistics
    stats_resp = await async_client.get("/api/v1/dashboard/statistics")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["linkedin_videos_discovered"] == 2
    assert stats["qualified_podcasts"] == 1
    assert stats["rejected_videos"] == 1
    assert stats["hosts_identified"] == 1
    assert stats["emails_discovered"] == 1

    # 5. Human verification & manual review (#14)
    verify_host_resp = await async_client.post(
        "/api/v1/verification/verify-host",
        json={
            "host_id": qualified_row["host_id"],
            "identity_status": "Verified",
            "manual_review_required": False,
            "notes": "Confirmed host on LinkedIn and website",
        },
    )
    assert verify_host_resp.status_code == 200
    verify_contact_resp = await async_client.post(
        "/api/v1/verification/verify-contact",
        json={
            "contact_id": qualified_row["contact_id"],
            "verification_status": "Verified",
            "contact_status": "active",
            "notes": "Verified domain match",
        },
    )
    assert verify_contact_resp.status_code == 200

    # 6. Excel Workbook structure, 32 columns, hyperlinks, verified sheet (#15, #19, #20, #21)
    xlsx_resp = await async_client.get("/api/v1/export/excel")
    assert xlsx_resp.status_code == 200
    assert xlsx_resp.headers["X-Export-Record-Count"] == "2"
    wb = load_workbook(BytesIO(xlsx_resp.content))
    assert wb.sheetnames == [
        "All Leads",
        "Verified Leads",
        "Email Available",
        "Manual Review",
        "Research Summary",
    ]
    ws_all = wb["All Leads"]
    assert ws_all.max_row == 3
    actual_headers = [ws_all.cell(row=1, column=i + 1).value for i in range(len(EXCEL_COLUMNS))]
    assert actual_headers == [label for label, _ in EXCEL_COLUMNS]
    assert ws_all["D2"].hyperlink is not None

    ws_verified = wb["Verified Leads"]
    assert ws_verified.max_row == 2

    ws_email = wb["Email Available"]
    assert ws_email.max_row == 2

    # 7. Selected-row & filtered exports (#16, #17, #18)
    sel_resp = await async_client.post(
        "/api/v1/export/excel",
        json={"preset": "all", "selected_ids": [qualified_row["lead_id"]]},
    )
    assert sel_resp.status_code == 200
    assert sel_resp.headers["X-Export-Record-Count"] == "1"

    filtered_resp = await async_client.post(
        "/api/v1/export/excel",
        json={"company": "Vance Commercial", "min_quality_score": 65},
    )
    assert filtered_resp.status_code == 200
    assert filtered_resp.headers["X-Export-Record-Count"] == "1"

    csv_resp = await async_client.get("/api/v1/export/csv?preset=email_available")
    assert csv_resp.status_code == 200
    assert csv_resp.headers["X-Export-Record-Count"] == "1"
    assert "marcus@vancecommercial.example" in csv_resp.text

    # 8. Formula-injection protection
    assert sanitize_spreadsheet_cell("=HYPERLINK(\"http://evil\")").startswith("'=")
    assert sanitize_spreadsheet_cell("+1234").startswith("'+")

    # 9. Settings endpoint never leaks secrets
    settings_resp = await async_client.get("/api/v1/settings")
    assert settings_resp.status_code == 200
    s_data = settings_resp.json()
    assert "openai_api_key" not in s_data
    assert "database_url" not in s_data

    # 10. Jarvis command router (scope check + summary + export)
    oos_resp = await async_client.post(
        "/api/v1/agent/command",
        json={"command": "Find marketing employees at guest companies"},
    )
    assert oos_resp.status_code == 200
    assert oos_resp.json()["intent"] == "out_of_scope"

    sum_resp = await async_client.post(
        "/api/v1/agent/command",
        json={"command": "Show me the research completed so far"},
    )
    assert sum_resp.status_code == 200
    assert sum_resp.json()["intent"] == "show_research_summary"

    exp_cmd_resp = await async_client.post(
        "/api/v1/agent/command",
        json={"command": "Export all verified podcast leads to Excel"},
    )
    assert exp_cmd_resp.status_code == 200
    dl_url = exp_cmd_resp.json()["export_download_url"]
    assert dl_url.startswith("/api/v1/export/download/")
    dl_file = await async_client.get(dl_url)
    assert dl_file.status_code == 200

    # 11. Export history
    hist_resp = await async_client.get("/api/v1/export/history")
    assert hist_resp.status_code == 200
    assert len(hist_resp.json()) >= 6


@pytest.mark.asyncio
async def test_apollo_fallback_discovery():
    """Verify Priority 3 Apollo fallback runs only when Priority 1 & 2 find nothing (#9)."""
    fake_apollo = {
        "email": "elena@apexcre.example",
        "email_status": "verified",
        "name": "Elena Rostova",
        "title": "Managing Partner & Podcast Host",
        "linkedin_url": "https://www.linkedin.com/in/elena-rostova-cre",
        "organization": "Apex CRE Partners",
    }
    with patch(
        "app.services.contact_discovery._apollo_person_enrich",
        new=AsyncMock(return_value=fake_apollo),
    ), patch(
        "app.services.contact_discovery.search_tavily",
        new=AsyncMock(return_value=[]),
    ):
        contacts = await discover_host_contacts(
            post_data={"post_caption": "New episode out now!", "post_url": "https://www.linkedin.com/posts/1"},
            host_name="Elena Rostova",
            host_linkedin_url="https://www.linkedin.com/in/elena-rostova-cre",
            company_name="Apex CRE Partners",
            official_website="https://apexcre.example",
            youtube_channel_url=None,
            browser=None,
            allow_live_browser=False,
        )
        assert len(contacts) == 1
        assert contacts[0].email == "elena@apexcre.example"
        assert contacts[0].source_type == "Apollo"
        assert contacts[0].verification_status == "Partially Verified"


def test_alembic_upgrade_head_on_fresh_database(tmp_path: Path):
    """Verify Alembic initial migration applies cleanly to a fresh database."""
    import os
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    alembic_db = tmp_path / "alembic_verify.sqlite3"
    db_url = f"sqlite:///{alembic_db.as_posix()}"
    prev_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = db_url
    from app.config import get_settings

    try:
        get_settings.cache_clear()
        cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
        command.upgrade(cfg, "head")

        eng = create_engine(db_url)
        tables = set(inspect(eng).get_table_names())
    finally:
        if prev_url is not None:
            os.environ["DATABASE_URL"] = prev_url
        else:
            os.environ.pop("DATABASE_URL", None)
        get_settings.cache_clear()
    expected = {
        "research_tasks",
        "linkedin_posts",
        "quality_assessments",
        "podcasts",
        "people",
        "companies",
        "person_company_roles",
        "contacts",
        "contact_sources",
        "research_evidence",
        "export_logs",
    }
    assert expected.issubset(tables)


@pytest.mark.asyncio
async def test_agency_tenant_isolation_and_manual_review_actions(async_client):
    """Verify multi-agency isolation via X-Agency-Id and manual review corrections."""
    from app.db.models import ResearchTask
    from app.services.persistence import upsert_linkedin_post, upsert_podcast, upsert_host_person

    db = SessionLocal()
    try:
        t_alpha = ResearchTask(
            agency_id="agency-alpha",
            user_instruction="Alpha podcast search",
            search_keyword="Real Estate Podcast",
            task_status="completed",
        )
        t_beta = ResearchTask(
            agency_id="agency-beta",
            user_instruction="Beta podcast search",
            search_keyword="Real Estate Podcast",
            task_status="completed",
        )
        db.add_all([t_alpha, t_beta])
        db.commit()
        db.refresh(t_alpha)
        db.refresh(t_beta)

        # Same LinkedIn URL saved independently in two agencies without collision
        shared_post = {
            "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:55555",
            "post_caption": "Real Estate Capital Show",
            "posting_account": "Capital Show",
        }
        p_alpha, created_a = upsert_linkedin_post(db, t_alpha.id, shared_post, agency_id="agency-alpha")
        p_beta, created_b = upsert_linkedin_post(db, t_beta.id, shared_post, agency_id="agency-beta")
        assert created_a and created_b and p_alpha.id != p_beta.id

        host_a = upsert_host_person(
            db,
            full_name="Unknown Host Candidate",
            identity_status="Manual Review Required",
            manual_review_required=True,
            agency_id="agency-alpha",
        )
        pod_a = upsert_podcast(
            db,
            linkedin_post_id=p_alpha.id,
            host_id=host_a.id,
            podcast_name="Real Estate Capital Show",
            manual_review_required=True,
            agency_id="agency-alpha",
        )
        db.commit()
    finally:
        db.close()

    # Alpha sees only Alpha's records; Beta sees only Beta's
    alpha_res = await async_client.get("/api/v1/research/results", headers={"X-Agency-Id": "agency-alpha"})
    beta_res = await async_client.get("/api/v1/research/results", headers={"X-Agency-Id": "agency-beta"})
    assert alpha_res.status_code == 200 and len(alpha_res.json()) == 1
    assert beta_res.status_code == 200 and len(beta_res.json()) == 1

    # Manual review approval & correction for Alpha
    mr_list = await async_client.get("/api/v1/verification/manual-review", headers={"X-Agency-Id": "agency-alpha"})
    assert len(mr_list.json()) == 1

    mr_approve = await async_client.post(
        "/api/v1/verification/manual-review",
        headers={"X-Agency-Id": "agency-alpha"},
        json={
            "podcast_id": pod_a.id,
            "host_id": host_a.id,
            "action": "approve",
            "corrected_host_name": "Jordan Mercer",
            "corrected_company_name": "Mercer CRE Group",
            "notes": "Confirmed host via podcast episode page",
        },
    )
    assert mr_approve.status_code == 200

    alpha_after = await async_client.get("/api/v1/research/results", headers={"X-Agency-Id": "agency-alpha"})
    row = alpha_after.json()[0]
    assert row["host_full_name"] == "Jordan Mercer"
    assert row["host_company"] == "Mercer CRE Group"
    assert row["identity_verification_status"] == "Verified"


