from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_agency_id
from app.db.models import ExportLog
from app.db.session import get_db
from app.schemas.export import ExportFilterParams, ExportLogOut
from app.services.export_service import generate_csv_export, generate_excel_export

router = APIRouter(prefix="/export", tags=["export"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _build_filters_dict(
    preset: str = "all",
    qualification_status: str | None = None,
    identity_verification_status: str | None = None,
    contact_verification_status: str | None = None,
    has_email: bool | None = None,
    company: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_quality_score: int | None = None,
    research_task_id: int | None = None,
    selected_ids: str | None = None,
) -> dict:
    parsed_ids = None
    if selected_ids:
        parsed_ids = [int(x.strip()) for x in selected_ids.split(",") if x.strip().isdigit()]
    return {
        "preset": preset,
        "qualification_status": qualification_status,
        "identity_verification_status": identity_verification_status,
        "contact_verification_status": contact_verification_status,
        "has_email": has_email,
        "company": company,
        "date_from": date_from,
        "date_to": date_to,
        "min_quality_score": min_quality_score,
        "research_task_id": research_task_id,
        "selected_ids": parsed_ids,
    }


@router.get("/excel")
def export_excel_get(
    preset: str = Query(default="all"),
    qualification_status: str | None = Query(default=None),
    identity_verification_status: str | None = Query(default=None),
    contact_verification_status: str | None = Query(default=None),
    has_email: bool | None = Query(default=None),
    company: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    min_quality_score: int | None = Query(default=None),
    research_task_id: int | None = Query(default=None),
    selected_ids: str | None = Query(default=None),
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> FileResponse:
    filters = _build_filters_dict(
        preset,
        qualification_status,
        identity_verification_status,
        contact_verification_status,
        has_email,
        company,
        date_from,
        date_to,
        min_quality_score,
        research_task_id,
        selected_ids,
    )
    log = generate_excel_export(db, filters, agency_id=agency_id)
    return FileResponse(
        path=log.file_path,
        media_type=XLSX_MEDIA_TYPE,
        filename=log.filename,
        headers={"X-Export-Record-Count": str(log.record_count), "X-Export-Id": str(log.id)},
    )


@router.post("/excel")
def export_excel_post(
    payload: ExportFilterParams,
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> FileResponse:
    log = generate_excel_export(db, payload.model_dump(), agency_id=agency_id)
    return FileResponse(
        path=log.file_path,
        media_type=XLSX_MEDIA_TYPE,
        filename=log.filename,
        headers={"X-Export-Record-Count": str(log.record_count), "X-Export-Id": str(log.id)},
    )


@router.get("/csv")
def export_csv_get(
    preset: str = Query(default="all"),
    qualification_status: str | None = Query(default=None),
    identity_verification_status: str | None = Query(default=None),
    contact_verification_status: str | None = Query(default=None),
    has_email: bool | None = Query(default=None),
    company: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    min_quality_score: int | None = Query(default=None),
    research_task_id: int | None = Query(default=None),
    selected_ids: str | None = Query(default=None),
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> FileResponse:
    filters = _build_filters_dict(
        preset,
        qualification_status,
        identity_verification_status,
        contact_verification_status,
        has_email,
        company,
        date_from,
        date_to,
        min_quality_score,
        research_task_id,
        selected_ids,
    )
    log = generate_csv_export(db, filters, agency_id=agency_id)
    return FileResponse(
        path=log.file_path,
        media_type="text/csv; charset=utf-8",
        filename=log.filename,
        headers={"X-Export-Record-Count": str(log.record_count), "X-Export-Id": str(log.id)},
    )


@router.post("/csv")
def export_csv_post(
    payload: ExportFilterParams,
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> FileResponse:
    log = generate_csv_export(db, payload.model_dump(), agency_id=agency_id)
    return FileResponse(
        path=log.file_path,
        media_type="text/csv; charset=utf-8",
        filename=log.filename,
        headers={"X-Export-Record-Count": str(log.record_count), "X-Export-Id": str(log.id)},
    )


@router.get("/history", response_model=list[ExportLogOut])
def export_history(
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> list[ExportLogOut]:
    logs = (
        db.query(ExportLog)
        .filter(ExportLog.agency_id == agency_id)
        .order_by(ExportLog.id.desc())
        .limit(50)
        .all()
    )
    return [
        ExportLogOut(
            id=l.id,
            export_format=l.export_format,
            filename=l.filename,
            filter_preset=l.filter_preset,
            filters_json=l.filters_json,
            record_count=l.record_count,
            status=l.status,
            download_url=f"/api/v1/export/download/{l.id}",
            created_at=l.created_at,
        )
        for l in logs
    ]


@router.get("/download/{export_id}")
def download_export(
    export_id: int,
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> FileResponse:
    log = db.query(ExportLog).filter(ExportLog.id == export_id, ExportLog.agency_id == agency_id).first()
    if not log or not Path(log.file_path).exists():
        raise HTTPException(status_code=404, detail="Export file not found")
    media_type = XLSX_MEDIA_TYPE if log.export_format == "xlsx" else "text/csv; charset=utf-8"
    return FileResponse(
        path=log.file_path,
        media_type=media_type,
        filename=log.filename,
        headers={"X-Export-Record-Count": str(log.record_count)},
    )
