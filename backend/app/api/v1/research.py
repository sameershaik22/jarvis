from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_agency_id
from app.db.models import (
    Company,
    Contact,
    LinkedinPost,
    Person,
    Podcast,
    ResearchEvidence,
    ResearchTask,
)
from app.db.session import get_db
from app.schemas.research import EvidenceOut, LeadRecordOut
from app.services.research_query import query_research_leads

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/tasks")
def list_tasks(
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    tasks = (
        db.query(ResearchTask)
        .filter(ResearchTask.agency_id == agency_id)
        .order_by(ResearchTask.id.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": t.id,
            "user_instruction": t.user_instruction,
            "search_keyword": t.search_keyword,
            "task_status": t.task_status,
            "current_stage": t.current_stage,
            "current_url": t.current_url,
            "progress": t.progress,
            "max_posts": t.max_posts,
            "quality_threshold": t.quality_threshold,
            "started_at": t.started_at,
            "completed_at": t.completed_at,
            "error_message": t.error_message,
            "created_at": t.created_at,
        }
        for t in tasks
    ]


@router.get("/results", response_model=list[LeadRecordOut])
def list_results(
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
    search: str | None = Query(default=None),
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return query_research_leads(
        db=db,
        preset=preset,
        qualification_status=qualification_status,
        identity_verification_status=identity_verification_status,
        contact_verification_status=contact_verification_status,
        has_email=has_email,
        company=company,
        date_from=date_from,
        date_to=date_to,
        min_quality_score=min_quality_score,
        research_task_id=research_task_id,
        search=search,
        agency_id=agency_id,
    )


@router.get("/videos")
def list_videos(
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    posts = (
        db.query(LinkedinPost)
        .filter(LinkedinPost.agency_id == agency_id)
        .options(joinedload(LinkedinPost.quality_assessment))
        .order_by(LinkedinPost.id.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": p.id,
            "research_task_id": p.research_task_id,
            "post_url": p.post_url,
            "post_caption": p.post_caption,
            "posting_account": p.posting_account,
            "posting_account_url": p.posting_account_url,
            "video_url": p.video_url,
            "published_label": p.published_label,
            "discovered_at": p.discovered_at,
            "quality_score": p.quality_assessment.video_score if p.quality_assessment else None,
            "qualification_status": p.quality_assessment.qualification_status if p.quality_assessment else "Pending",
            "assessment_notes": p.quality_assessment.assessment_notes if p.quality_assessment else None,
        }
        for p in posts
    ]


@router.get("/podcasts")
def list_podcasts(
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    podcasts = (
        db.query(Podcast)
        .filter(Podcast.agency_id == agency_id)
        .options(joinedload(Podcast.host), joinedload(Podcast.linkedin_post).joinedload(LinkedinPost.quality_assessment))
        .order_by(Podcast.id.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": p.id,
            "podcast_name": p.podcast_name,
            "episode_title": p.episode_title,
            "original_podcast_url": p.original_podcast_url,
            "youtube_channel_name": p.youtube_channel_name,
            "youtube_channel_url": p.youtube_channel_url,
            "discovery_method": p.discovery_method,
            "confidence_score": p.confidence_score,
            "manual_review_required": p.manual_review_required,
            "host_name": p.host.full_name if p.host else None,
            "linkedin_post_url": p.linkedin_post.post_url if p.linkedin_post else None,
            "quality_score": p.linkedin_post.quality_assessment.video_score
            if p.linkedin_post and p.linkedin_post.quality_assessment
            else None,
            "qualification_status": p.linkedin_post.quality_assessment.qualification_status
            if p.linkedin_post and p.linkedin_post.quality_assessment
            else None,
            "created_at": p.created_at,
        }
        for p in podcasts
    ]


@router.get("/hosts")
def list_hosts(
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    hosts = (
        db.query(Person)
        .options(joinedload(Person.company_roles), joinedload(Person.podcasts))
        .filter(Person.agency_id == agency_id, Person.role_type == "host")
        .order_by(Person.id.desc())
        .limit(200)
        .all()
    )
    out = []
    for h in hosts:
        comps = []
        for role in h.company_roles:
            if role.company:
                comps.append(
                    {
                        "id": role.company.id,
                        "company_name": role.company.company_name,
                        "linkedin_url": role.company.linkedin_url,
                        "website": role.company.website,
                        "location": role.company.location,
                        "designation": role.designation,
                        "relationship_status": role.relationship_status,
                    }
                )
        out.append(
            {
                "id": h.id,
                "full_name": h.full_name,
                "linkedin_url": h.linkedin_url,
                "designation": h.designation,
                "location": h.location,
                "identity_status": h.identity_status,
                "confidence_score": h.confidence_score,
                "manual_review_required": h.manual_review_required,
                "notes": h.notes,
                "companies": comps,
                "podcasts": [
                    {"id": pod.id, "podcast_name": pod.podcast_name, "youtube_channel_url": pod.youtube_channel_url}
                    for pod in h.podcasts
                ],
            }
        )
    return out


@router.get("/companies")
def list_companies(
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    companies = (
        db.query(Company)
        .filter(Company.agency_id == agency_id)
        .order_by(Company.id.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": c.id,
            "company_name": c.company_name,
            "linkedin_url": c.linkedin_url,
            "website": c.website,
            "location": c.location,
            "industry": c.industry,
            "created_at": c.created_at,
        }
        for c in companies
    ]


@router.get("/contacts")
def list_contacts(
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    contacts = (
        db.query(Contact)
        .filter(Contact.agency_id == agency_id)
        .options(joinedload(Contact.person), joinedload(Contact.podcast), joinedload(Contact.sources))
        .order_by(Contact.id.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": c.id,
            "person_id": c.person_id,
            "host_name": c.person.full_name if c.person else None,
            "podcast_id": c.podcast_id,
            "podcast_name": c.podcast.podcast_name if c.podcast else None,
            "email": c.email,
            "email_category": c.email_category,
            "phone": c.phone,
            "official_website": c.official_website,
            "contact_page": c.contact_page,
            "contact_status": c.contact_status,
            "verification_status": c.verification_status,
            "confidence_score": c.confidence_score,
            "research_notes": c.research_notes,
            "sources": [
                {
                    "id": s.id,
                    "source_type": s.source_type,
                    "source_url": s.source_url,
                    "discovery_method": s.discovery_method,
                    "collected_at": s.collected_at,
                }
                for s in c.sources
            ],
        }
        for c in contacts
    ]


@router.get("/evidence", response_model=list[EvidenceOut])
def list_evidence(
    entity_type: str | None = Query(default=None),
    entity_id: int | None = Query(default=None),
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> list[ResearchEvidence]:
    q = db.query(ResearchEvidence).filter(ResearchEvidence.agency_id == agency_id)
    if entity_type:
        q = q.filter(ResearchEvidence.entity_type == entity_type)
    if entity_id is not None:
        q = q.filter(ResearchEvidence.entity_id == entity_id)
    return q.order_by(ResearchEvidence.id.desc()).limit(250).all()
