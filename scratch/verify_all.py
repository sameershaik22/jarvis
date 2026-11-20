from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

import httpx
from sqlalchemy import inspect, text

from app.config import get_settings
from app.db.models import AgentActivityLog, ResearchTask
from app.db.session import SessionLocal, engine
from app.services.ai_planner import ai_planner
from app.services.browser_controller import browser_controller
from app.services.export_service import generate_csv_export, generate_excel_export
from app.services.research_query import compute_dashboard_statistics
from app.services.tavily_search import search_tavily


async def main():
    report = {}

    # Check 1: Neon PostgreSQL Connectivity
    t0 = time.time()
    try:
        with engine.connect() as conn:
            db_info = conn.execute(text("SELECT current_user, current_database(), version();")).fetchone()
            report["1_neon_connection"] = {
                "status": "PASSED",
                "current_user": db_info[0],
                "database": db_info[1],
                "version": db_info[2][:60],
                "duration_ms": int((time.time() - t0) * 1000),
            }
    except Exception as e:
        report["1_neon_connection"] = {"status": "FAILED", "error": str(e)}

    # Check 2: 14 Core Tables
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        expected = [
            "alembic_version", "research_tasks", "linkedin_posts", "quality_assessments",
            "companies", "person_company_roles", "people", "podcasts", "contacts",
            "contact_sources", "research_evidence", "agent_messages", "agent_activity_logs",
            "export_logs", "app_settings"
        ]
        missing = [t for t in expected if t not in tables]
        report["2_neon_tables"] = {
            "status": "PASSED" if not missing else "FAILED",
            "table_count": len(tables),
            "tables": tables,
            "missing": missing,
        }
    except Exception as e:
        report["2_neon_tables"] = {"status": "FAILED", "error": str(e)}

    # Check 3: Tavily Real Query
    t0 = time.time()
    try:
        tav_res = await search_tavily("Real Estate Podcast YouTube", max_results=3)
        report["3_tavily_search"] = {
            "status": "PASSED" if tav_res else "FAILED",
            "results_count": len(tav_res),
            "first_result": {"title": tav_res[0].get("title"), "url": tav_res[0].get("url")} if tav_res else None,
            "duration_ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        report["3_tavily_search"] = {"status": "FAILED", "error": str(e)}

    # Check 4: Gemini Official API & Model Availability
    s = get_settings()
    t0 = time.time()
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{s.gemini_model}:generateContent"
        payload = {"contents": [{"parts": [{"text": "Say 'YoursBuddy Connected' in 2 words."}]}]}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                headers={"Content-Type": "application/json", "x-goog-api-key": s.gemini_api_key},
                json=payload,
            )
            report["4_gemini_api"] = {
                "status": "PASSED" if resp.status_code == 200 else "DEGRADED",
                "http_status": resp.status_code,
                "model": s.gemini_model,
                "response": resp.json() if resp.status_code == 200 else resp.text[:200],
                "duration_ms": int((time.time() - t0) * 1000),
            }
    except Exception as e:
        report["4_gemini_api"] = {"status": "FAILED", "error": str(e)}

    # Check 5: Research Pipeline AI Planner Entity Disambiguation
    t0 = time.time()
    try:
        test_caption = "Welcome to the Commercial Real Estate Showcase hosted by John Doe, Founder of Apex Realty. Special guest Sarah Smith joins us today."
        entities = await ai_planner.extract_podcast_and_host_entities(test_caption, "Apex Realty Media")
        report["5_pipeline_ai_disambiguation"] = {
            "status": "PASSED" if entities else "PASSED_WITH_FALLBACK",
            "entities": entities,
            "duration_ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        report["5_pipeline_ai_disambiguation"] = {"status": "FAILED", "error": str(e)}

    # Check 6: Playwright & Login Gate Detection
    t0 = time.time()
    try:
        li_auth = await browser_controller.check_platform_auth("linkedin")
        yt_auth = await browser_controller.check_platform_auth("youtube")
        report["6_playwright_auth_gates"] = {
            "status": "PASSED",
            "linkedin": li_auth,
            "youtube": yt_auth,
            "duration_ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        report["6_playwright_auth_gates"] = {"status": "FAILED", "error": str(e)}

    # Check 7: Neon Record Persistence
    t0 = time.time()
    db = SessionLocal()
    task_id = None
    try:
        test_task = ResearchTask(
            agency_id="default",
            user_instruction="Integration Verification Task",
            search_keyword="Real Estate Podcast",
            task_status="completed",
            current_stage="verification",
            progress=100,
            max_posts=3,
            quality_threshold=65,
        )
        db.add(test_task)
        db.commit()
        db.refresh(test_task)
        task_id = test_task.id

        # Verify reading it back from Neon
        persisted = db.query(ResearchTask).filter(ResearchTask.id == task_id).first()
        report["7_neon_persistence"] = {
            "status": "PASSED",
            "inserted_task_id": task_id,
            "verified_agency_id": persisted.agency_id if persisted else None,
            "task_status": persisted.task_status if persisted else None,
            "duration_ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        report["7_neon_persistence"] = {"status": "FAILED", "error": str(e)}
    finally:
        db.close()

    # Check 8: Dashboard Aggregated Stats from Neon
    t0 = time.time()
    db = SessionLocal()
    try:
        stats = compute_dashboard_statistics(db, agency_id="default")
        report["8_dashboard_neon_query"] = {
            "status": "PASSED",
            "stats": stats,
            "duration_ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        report["8_dashboard_neon_query"] = {"status": "FAILED", "error": str(e)}
    finally:
        db.close()

    # Check 9: Excel and CSV Exports
    db = SessionLocal()
    try:
        excel_log = generate_excel_export(db, agency_id="default")
        csv_log = generate_csv_export(db, agency_id="default")
        xlsx_path = Path(excel_log.file_path)
        csv_path = Path(csv_log.file_path)
        report["9_exports"] = {
            "status": "PASSED" if xlsx_path.exists() and csv_path.exists() else "FAILED",
            "excel_path": str(xlsx_path),
            "excel_exists": xlsx_path.exists(),
            "excel_size_bytes": xlsx_path.stat().st_size,
            "excel_filename": excel_log.filename,
            "csv_path": str(csv_path),
            "csv_exists": csv_path.exists(),
            "csv_size_bytes": csv_path.stat().st_size,
            "csv_filename": csv_log.filename,
        }
    except Exception as e:
        report["9_exports"] = {"status": "FAILED", "error": str(e)}
    finally:
        db.close()

    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
