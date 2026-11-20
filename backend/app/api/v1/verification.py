from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_agency_id
from app.db.models import Contact, Person, Podcast
from app.db.session import get_db
from app.schemas.verification import (
    ManualReviewActionRequest,
    VerifyContactRequest,
    VerifyHostRequest,
)
from app.services.persistence import add_evidence, upsert_company, upsert_person_company_role
from app.services.research_query import query_research_leads

router = APIRouter(prefix="/verification", tags=["verification"])


@router.post("/verify-host")
def verify_host(
    payload: VerifyHostRequest,
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    host = db.query(Person).filter(Person.id == payload.host_id, Person.agency_id == agency_id).first()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")

    if payload.full_name:
        host.full_name = payload.full_name.strip()
    if payload.linkedin_url is not None:
        host.linkedin_url = payload.linkedin_url.strip() or None
    if payload.designation is not None:
        host.designation = payload.designation.strip() or None
    host.identity_status = payload.identity_status
    host.manual_review_required = payload.manual_review_required
    if payload.identity_status == "Verified":
        host.confidence_score = max(host.confidence_score, 95)
    if payload.notes:
        host.notes = payload.notes

    if payload.company_name:
        comp = upsert_company(
            db,
            company_name=payload.company_name,
            linkedin_url=payload.company_linkedin_url,
            website=payload.company_website,
            location=payload.company_location,
            agency_id=agency_id,
        )
        upsert_person_company_role(
            db,
            person_id=host.id,
            company_id=comp.id,
            designation=host.designation,
            relationship_status="Verified" if payload.identity_status == "Verified" else "Possible Match",
            evidence_url=payload.company_linkedin_url or host.linkedin_url,
            agency_id=agency_id,
        )

    add_evidence(
        db,
        research_task_id=None,
        entity_type="person",
        entity_id=host.id,
        source_url=host.linkedin_url or "manual_human_review",
        source_type="Human Review",
        extracted_information=f"Identity status updated to {host.identity_status}. {payload.notes or ''}",
        agency_id=agency_id,
    )
    db.commit()
    return {"status": "updated", "host_id": host.id, "identity_status": host.identity_status}


@router.post("/verify-contact")
def verify_contact(
    payload: VerifyContactRequest,
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    contact = db.query(Contact).filter(Contact.id == payload.contact_id, Contact.agency_id == agency_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if payload.email is not None:
        contact.email = payload.email.strip().lower() or None
    if payload.email_category is not None:
        contact.email_category = payload.email_category
    if payload.phone is not None:
        contact.phone = payload.phone.strip() or None
    contact.contact_status = payload.contact_status
    contact.verification_status = payload.verification_status
    if payload.verification_status == "Verified":
        contact.confidence_score = max(contact.confidence_score, 95)
    if payload.notes:
        contact.research_notes = payload.notes

    add_evidence(
        db,
        research_task_id=None,
        entity_type="contact",
        entity_id=contact.id,
        source_url=contact.official_website or "manual_human_review",
        source_type="Human Review",
        extracted_information=f"Contact status={contact.contact_status}, verification={contact.verification_status}. {payload.notes or ''}",
        agency_id=agency_id,
    )
    db.commit()
    return {"status": "updated", "contact_id": contact.id, "verification_status": contact.verification_status}


@router.get("/manual-review")
def list_manual_review_items(
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return query_research_leads(db=db, preset="manual_review", agency_id=agency_id)


@router.post("/manual-review")
def submit_manual_review(
    payload: ManualReviewActionRequest,
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if payload.podcast_id:
        podcast = db.query(Podcast).filter(Podcast.id == payload.podcast_id, Podcast.agency_id == agency_id).first()
        if podcast:
            if payload.corrected_youtube_url:
                podcast.youtube_channel_url = payload.corrected_youtube_url.strip()
            if payload.action == "approve":
                podcast.manual_review_required = False
                podcast.confidence_score = max(podcast.confidence_score, 90)
            elif payload.action == "reject":
                podcast.manual_review_required = False
                if podcast.linkedin_post and podcast.linkedin_post.quality_assessment:
                    podcast.linkedin_post.quality_assessment.qualification_status = "Rejected"
            elif payload.action == "request_recheck":
                podcast.manual_review_required = True
            if payload.notes:
                podcast.research_notes = payload.notes

    if payload.host_id:
        host = db.query(Person).filter(Person.id == payload.host_id, Person.agency_id == agency_id).first()
        if host:
            if payload.corrected_host_name:
                host.full_name = payload.corrected_host_name.strip()
            if payload.action == "approve":
                host.identity_status = "Verified"
                host.manual_review_required = False
                host.confidence_score = max(host.confidence_score, 95)
            elif payload.action == "reject":
                host.identity_status = "Unverified"
                host.manual_review_required = False
            elif payload.action == "request_recheck":
                host.identity_status = "Manual Review Required"
                host.manual_review_required = True
            if payload.corrected_company_name:
                comp = upsert_company(db, company_name=payload.corrected_company_name, agency_id=agency_id)
                upsert_person_company_role(
                    db,
                    person_id=host.id,
                    company_id=comp.id,
                    designation=host.designation,
                    relationship_status="Verified" if payload.action == "approve" else "Possible Match",
                    agency_id=agency_id,
                )

    if payload.contact_id:
        contact = db.query(Contact).filter(Contact.id == payload.contact_id, Contact.agency_id == agency_id).first()
        if contact:
            if payload.corrected_email:
                contact.email = payload.corrected_email.strip().lower()
            if payload.action == "approve":
                contact.verification_status = "Verified"
                contact.contact_status = "active"
                contact.confidence_score = max(contact.confidence_score, 95)
            elif payload.action == "reject":
                contact.verification_status = "Unverified"
                contact.contact_status = "rejected"
            elif payload.action == "request_recheck":
                contact.verification_status = "Manual Review Required"
                contact.contact_status = "needs_review"
            if payload.notes:
                contact.research_notes = payload.notes

    db.commit()
    return {"status": "applied", "action": payload.action}
