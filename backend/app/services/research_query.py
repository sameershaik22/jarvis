from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.db.models import (
    Company,
    Contact,
    LinkedinPost,
    Person,
    PersonCompanyRole,
    Podcast,
    QualityAssessment,
    ResearchTask,
)


def _parse_date(date_str: str | None, end_of_day: bool = False) -> datetime | None:
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if end_of_day and len(date_str.strip()) <= 10:
            dt = dt + timedelta(days=1) - timedelta(seconds=1)
        return dt
    except ValueError:
        return None


def _build_lead_dict(
    podcast: Podcast | None,
    post: LinkedinPost | None,
    qa: QualityAssessment | None,
    host: Person | None,
    company: Company | None,
    contact: Contact | None,
) -> dict[str, Any]:
    source_type = None
    source_url = None
    if contact and contact.sources:
        source_type = contact.sources[0].source_type
        source_url = contact.sources[0].source_url

    lead_id = podcast.id if podcast else (post.id if post else 0)
    research_dt = (
        (podcast.updated_at if podcast else None)
        or (post.discovered_at if post else None)
    )
    confidence = max(
        (podcast.confidence_score if podcast else 0),
        (host.confidence_score if host else 0),
        (contact.confidence_score if contact else 0),
    )
    manual_review = bool(
        (podcast.manual_review_required if podcast else False)
        or (host.manual_review_required if host else False)
        or (qa and qa.qualification_status == "Manual Review")
        or (contact and contact.verification_status == "Manual Review Required")
    )

    notes_parts = []
    if qa and qa.assessment_notes:
        notes_parts.append(qa.assessment_notes)
    if podcast and podcast.research_notes:
        notes_parts.append(podcast.research_notes)
    if contact and contact.research_notes:
        notes_parts.append(contact.research_notes)

    return {
        "lead_id": lead_id,
        "linkedin_post_id": post.id if post else None,
        "podcast_id": podcast.id if podcast else None,
        "host_id": host.id if host else None,
        "company_id": company.id if company else None,
        "contact_id": contact.id if contact else None,
        "research_task_id": post.research_task_id if post else None,
        "podcast_name": podcast.podcast_name if podcast else (post.posting_account if post else "Unresolved Podcast"),
        "episode_title": podcast.episode_title if podcast else None,
        "linkedin_post_url": post.post_url if post else None,
        "video_posting_date": (
            post.published_at.strftime("%Y-%m-%d")
            if post and post.published_at
            else (post.published_label if post else None)
        ),
        "youtube_channel_name": podcast.youtube_channel_name if podcast else None,
        "youtube_channel_url": podcast.youtube_channel_url if podcast else None,
        "original_podcast_url": podcast.original_podcast_url if podcast else None,
        "host_full_name": host.full_name if host else None,
        "host_designation": host.designation if host else None,
        "host_linkedin_url": host.linkedin_url if host else None,
        "host_company": company.company_name if company else None,
        "company_linkedin_url": company.linkedin_url if company else None,
        "company_website": company.website if company else (contact.official_website if contact else None),
        "company_location": company.location if company else None,
        "business_email": contact.email if contact else None,
        "email_category": contact.email_category if contact and contact.email else None,
        "phone": contact.phone if contact else None,
        "contact_source": source_type,
        "contact_source_url": source_url,
        "video_quality_score": qa.video_score if qa else None,
        "video_quality": qa.video_quality if qa else None,
        "audio_quality": qa.audio_quality if qa else None,
        "lighting": qa.lighting if qa else None,
        "podcast_setup": qa.setup_quality if qa else None,
        "content_relevance": qa.content_relevance if qa else None,
        "qualification_status": qa.qualification_status if qa else "Pending",
        "identity_verification_status": host.identity_status if host else "Unverified",
        "contact_verification_status": contact.verification_status if contact else "Unverified",
        "confidence_score": confidence,
        "manual_review_required": manual_review,
        "research_date": research_dt,
        "research_notes": " | ".join(notes_parts)[:1500] if notes_parts else None,
    }


def query_research_leads(
    db: Session,
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
    selected_ids: list[int] | None = None,
    search: str | None = None,
    agency_id: str = "default",
) -> list[dict[str, Any]]:
    """Query joined research lead records directly from PostgreSQL/SQLAlchemy."""
    posts = (
        db.query(LinkedinPost)
        .filter(LinkedinPost.agency_id == agency_id)
        .options(
            joinedload(LinkedinPost.quality_assessment),
            joinedload(LinkedinPost.podcast)
            .joinedload(Podcast.host)
            .joinedload(Person.company_roles)
            .joinedload(PersonCompanyRole.company),
            joinedload(LinkedinPost.podcast)
            .joinedload(Podcast.contacts)
            .joinedload(Contact.sources),
        )
        .order_by(LinkedinPost.discovered_at.desc(), LinkedinPost.id.desc())
        .all()
    )

    records: list[dict[str, Any]] = []
    seen_podcast_ids: set[int] = set()

    for post in posts:
        podcast = post.podcast
        if podcast:
            seen_podcast_ids.add(podcast.id)
        qa = post.quality_assessment
        host = podcast.host if podcast else None
        comp = None
        if host and host.company_roles:
            current_roles = [r for r in host.company_roles if r.is_current] or host.company_roles
            comp = current_roles[0].company
        contact = None
        if podcast and podcast.contacts:
            with_email = [c for c in podcast.contacts if c.email]
            contact = with_email[0] if with_email else podcast.contacts[0]
        elif host and host.contacts:
            with_email = [c for c in host.contacts if c.email]
            contact = with_email[0] if with_email else host.contacts[0]

        records.append(_build_lead_dict(podcast, post, qa, host, comp, contact))

    # Also include standalone podcasts that weren't attached to a LinkedinPost (if any)
    standalone_podcasts = (
        db.query(Podcast)
        .filter(Podcast.agency_id == agency_id, Podcast.linkedin_post_id.is_(None))
        .options(
            joinedload(Podcast.host).joinedload(Person.company_roles).joinedload(PersonCompanyRole.company),
            joinedload(Podcast.contacts).joinedload(Contact.sources),
        )
        .all()
    )
    for podcast in standalone_podcasts:
        if podcast.id in seen_podcast_ids:
            continue
        host = podcast.host
        comp = host.company_roles[0].company if host and host.company_roles else None
        contact = podcast.contacts[0] if podcast.contacts else None
        records.append(_build_lead_dict(podcast, None, None, host, comp, contact))

    # Apply filters
    dt_from = _parse_date(date_from, end_of_day=False)
    dt_to = _parse_date(date_to, end_of_day=True)
    selected_set = set(selected_ids) if selected_ids else None

    filtered: list[dict[str, Any]] = []
    for r in records:
        if selected_set is not None and r["lead_id"] not in selected_set:
            continue
        if research_task_id is not None and r["research_task_id"] != research_task_id:
            continue
        if preset == "qualified" and r["qualification_status"] != "Qualified":
            continue
        if preset == "verified" and not (
            r["identity_verification_status"] == "Verified"
            and r["contact_verification_status"] == "Verified"
        ):
            continue
        if preset == "email_available" and not r["business_email"]:
            continue
        if preset == "manual_review" and not (
            r["manual_review_required"]
            or r["qualification_status"] == "Manual Review"
            or r["identity_verification_status"] in ("Manual Review Required", "Possible Match")
            or r["contact_verification_status"] in ("Manual Review Required", "Possible Match")
        ):
            continue

        if qualification_status and r["qualification_status"] != qualification_status:
            continue
        if identity_verification_status and r["identity_verification_status"] != identity_verification_status:
            continue
        if contact_verification_status and r["contact_verification_status"] != contact_verification_status:
            continue
        if has_email is True and not r["business_email"]:
            continue
        if has_email is False and r["business_email"]:
            continue
        if company and company.lower() not in (r["host_company"] or "").lower():
            continue
        if min_quality_score is not None and (r["video_quality_score"] or 0) < min_quality_score:
            continue
        if dt_from and r["research_date"]:
            rd = r["research_date"]
            if rd.tzinfo is None:
                rd = rd.replace(tzinfo=timezone.utc)
            if rd < dt_from:
                continue
        if dt_to and r["research_date"]:
            rd = r["research_date"]
            if rd.tzinfo is None:
                rd = rd.replace(tzinfo=timezone.utc)
            if rd > dt_to:
                continue
        if search:
            q = search.lower()
            hay = " ".join(
                str(r.get(k) or "")
                for k in ("podcast_name", "episode_title", "host_full_name", "host_company", "business_email")
            ).lower()
            if q not in hay:
                continue

        filtered.append(r)

    return filtered


def compute_dashboard_statistics(db: Session, agency_id: str = "default") -> dict[str, int]:
    from sqlalchemy import text

    stmt = text(
        """
        SELECT
            (SELECT count(*) FROM research_tasks WHERE agency_id = :aid) AS total_tasks,
            (SELECT count(*) FROM linkedin_posts WHERE agency_id = :aid) AS linkedin_videos,
            (SELECT count(*) FROM quality_assessments WHERE agency_id = :aid AND qualification_status = 'Qualified') AS qualified,
            (SELECT count(*) FROM quality_assessments WHERE agency_id = :aid AND qualification_status = 'Rejected') AS rejected,
            (SELECT count(*) FROM people WHERE agency_id = :aid AND role_type = 'host') AS hosts_identified,
            (SELECT count(*) FROM companies WHERE agency_id = :aid) AS companies_identified,
            (SELECT count(*) FROM contacts WHERE agency_id = :aid AND email IS NOT NULL AND email != '') AS emails_discovered,
            (SELECT count(*) FROM contacts WHERE agency_id = :aid AND verification_status = 'Verified') AS verified_contacts,
            (SELECT count(*) FROM quality_assessments WHERE agency_id = :aid AND qualification_status = 'Manual Review') AS manual_qa,
            (SELECT count(*) FROM people WHERE agency_id = :aid AND manual_review_required = TRUE) AS manual_people,
            (SELECT count(*) FROM podcasts WHERE agency_id = :aid AND manual_review_required = TRUE) AS manual_podcasts
        """
    )
    row = db.execute(stmt, {"aid": agency_id}).fetchone()
    if row:
        m = row._mapping
        return {
            "total_research_tasks": int(m["total_tasks"] or 0),
            "linkedin_videos_discovered": int(m["linkedin_videos"] or 0),
            "qualified_podcasts": int(m["qualified"] or 0),
            "rejected_videos": int(m["rejected"] or 0),
            "hosts_identified": int(m["hosts_identified"] or 0),
            "companies_identified": int(m["companies_identified"] or 0),
            "emails_discovered": int(m["emails_discovered"] or 0),
            "verified_contacts": int(m["verified_contacts"] or 0),
            "pending_manual_reviews": max(
                int(m["manual_qa"] or 0), int(m["manual_people"] or 0), int(m["manual_podcasts"] or 0)
            ),
        }

    return {
        "total_research_tasks": 0,
        "linkedin_videos_discovered": 0,
        "qualified_podcasts": 0,
        "rejected_videos": 0,
        "hosts_identified": 0,
        "companies_identified": 0,
        "emails_discovered": 0,
        "verified_contacts": 0,
        "pending_manual_reviews": 0,
    }

