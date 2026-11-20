from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import (
    Company,
    Contact,
    ContactSource,
    LinkedinPost,
    Person,
    PersonCompanyRole,
    Podcast,
    QualityAssessment,
    ResearchEvidence,
)
from app.services.page_extractor import canonicalize_url


def add_evidence(
    db: Session,
    research_task_id: int | None,
    entity_type: str,
    entity_id: int,
    source_url: str,
    source_type: str,
    extracted_information: str,
    agency_id: str = "default",
) -> ResearchEvidence:
    """Append supporting evidence without deleting historical evidence."""
    norm_url = canonicalize_url(source_url) or source_url
    existing = (
        db.query(ResearchEvidence)
        .filter(
            ResearchEvidence.agency_id == agency_id,
            ResearchEvidence.entity_type == entity_type,
            ResearchEvidence.entity_id == entity_id,
            ResearchEvidence.source_url == norm_url,
            ResearchEvidence.source_type == source_type,
        )
        .first()
    )
    if existing:
        if extracted_information and extracted_information not in existing.extracted_information:
            existing.extracted_information = f"{existing.extracted_information}\n{extracted_information}"
        return existing

    ev = ResearchEvidence(
        agency_id=agency_id,
        research_task_id=research_task_id,
        entity_type=entity_type,
        entity_id=entity_id,
        source_url=norm_url,
        source_type=source_type,
        extracted_information=extracted_information,
    )
    db.add(ev)
    db.flush()
    return ev


def upsert_linkedin_post(
    db: Session,
    research_task_id: int,
    post_data: dict[str, Any],
    agency_id: str = "default",
) -> tuple[LinkedinPost, bool]:
    """Deduplicate LinkedIn posts by (agency_id, canonical post_url) while updating task metadata."""
    post_url = canonicalize_url(post_data["post_url"]) or post_data["post_url"]
    existing = (
        db.query(LinkedinPost)
        .filter(LinkedinPost.agency_id == agency_id, LinkedinPost.post_url == post_url)
        .first()
    )
    if existing:
        if post_data.get("post_caption") and len(post_data["post_caption"]) > len(existing.post_caption or ""):
            existing.post_caption = post_data["post_caption"]
        if post_data.get("video_url") and not existing.video_url:
            existing.video_url = post_data["video_url"]
        db.flush()
        return existing, False

    post = LinkedinPost(
        agency_id=agency_id,
        research_task_id=research_task_id,
        post_url=post_url,
        post_caption=post_data.get("post_caption", ""),
        posting_account=post_data.get("posting_account", ""),
        posting_account_url=canonicalize_url(post_data.get("posting_account_url")),
        video_url=post_data.get("video_url"),
        keywords_matched=post_data.get("keywords_matched"),
        published_label=post_data.get("published_label"),
        raw_metadata={
            "external_urls": post_data.get("external_urls", []),
            "comments": post_data.get("comments", []),
        },
    )
    db.add(post)
    db.flush()
    return post, True


def upsert_quality_assessment(
    db: Session,
    linkedin_post_id: int,
    video_score: int,
    video_quality: str,
    audio_quality: str,
    lighting: str,
    setup_quality: str,
    content_relevance: str,
    qualification_status: str,
    assessment_notes: str,
    frame_paths: list[str] | None = None,
    audio_inspected: bool = False,
    agency_id: str = "default",
) -> QualityAssessment:
    existing = (
        db.query(QualityAssessment)
        .filter(QualityAssessment.linkedin_post_id == linkedin_post_id)
        .first()
    )
    if existing:
        existing.video_score = video_score
        existing.video_quality = video_quality
        existing.audio_quality = audio_quality
        existing.lighting = lighting
        existing.setup_quality = setup_quality
        existing.content_relevance = content_relevance
        existing.qualification_status = qualification_status
        existing.assessment_notes = assessment_notes
        existing.frame_paths = frame_paths
        existing.audio_inspected = audio_inspected
        existing.assessed_at = datetime.now(timezone.utc)
        db.flush()
        return existing

    qa = QualityAssessment(
        agency_id=agency_id,
        linkedin_post_id=linkedin_post_id,
        video_score=video_score,
        video_quality=video_quality,
        audio_quality=audio_quality,
        lighting=lighting,
        setup_quality=setup_quality,
        content_relevance=content_relevance,
        qualification_status=qualification_status,
        assessment_notes=assessment_notes,
        frame_paths=frame_paths,
        audio_inspected=audio_inspected,
    )
    db.add(qa)
    db.flush()
    return qa


def upsert_host_person(
    db: Session,
    full_name: str,
    linkedin_url: str | None = None,
    designation: str | None = None,
    location: str | None = None,
    identity_status: str = "Unverified",
    confidence_score: int = 0,
    manual_review_required: bool = False,
    notes: str | None = None,
    agency_id: str = "default",
) -> Person:
    norm_li = canonicalize_url(linkedin_url)
    existing: Person | None = None
    if norm_li:
        existing = (
            db.query(Person)
            .filter(Person.agency_id == agency_id, Person.linkedin_url == norm_li)
            .first()
        )
    if not existing and full_name:
        existing = (
            db.query(Person)
            .filter(
                Person.agency_id == agency_id,
                func.lower(Person.full_name) == full_name.strip().lower(),
                Person.role_type == "host",
            )
            .first()
        )

    if existing:
        if norm_li and not existing.linkedin_url:
            existing.linkedin_url = norm_li
        if designation:
            existing.designation = designation
        if location:
            existing.location = location
        if confidence_score >= existing.confidence_score:
            existing.identity_status = identity_status
            existing.confidence_score = confidence_score
            existing.manual_review_required = manual_review_required
        if notes:
            existing.notes = notes
        db.flush()
        return existing

    person = Person(
        agency_id=agency_id,
        full_name=full_name.strip(),
        linkedin_url=norm_li,
        designation=designation,
        role_type="host",
        location=location,
        identity_status=identity_status,
        confidence_score=confidence_score,
        manual_review_required=manual_review_required,
        notes=notes,
    )
    db.add(person)
    db.flush()
    return person


def upsert_company(
    db: Session,
    company_name: str,
    linkedin_url: str | None = None,
    website: str | None = None,
    location: str | None = None,
    agency_id: str = "default",
) -> Company:
    norm_li = canonicalize_url(linkedin_url)
    norm_web = canonicalize_url(website)
    existing: Company | None = None
    if norm_li:
        existing = (
            db.query(Company)
            .filter(Company.agency_id == agency_id, Company.linkedin_url == norm_li)
            .first()
        )
    if not existing and company_name:
        existing = (
            db.query(Company)
            .filter(
                Company.agency_id == agency_id,
                func.lower(Company.company_name) == company_name.strip().lower(),
            )
            .first()
        )

    if existing:
        if norm_li and not existing.linkedin_url:
            existing.linkedin_url = norm_li
        if norm_web and not existing.website:
            existing.website = norm_web
        if location and not existing.location:
            existing.location = location
        db.flush()
        return existing

    company = Company(
        agency_id=agency_id,
        company_name=company_name.strip(),
        linkedin_url=norm_li,
        website=norm_web,
        location=location,
    )
    db.add(company)
    db.flush()
    return company


def upsert_person_company_role(
    db: Session,
    person_id: int,
    company_id: int,
    designation: str | None = None,
    relationship_status: str = "Unverified",
    evidence_url: str | None = None,
    agency_id: str = "default",
) -> PersonCompanyRole:
    existing = (
        db.query(PersonCompanyRole)
        .filter(
            PersonCompanyRole.person_id == person_id,
            PersonCompanyRole.company_id == company_id,
        )
        .first()
    )
    if existing:
        if designation:
            existing.designation = designation
        existing.relationship_status = relationship_status
        if evidence_url:
            existing.evidence_url = canonicalize_url(evidence_url)
        db.flush()
        return existing

    role = PersonCompanyRole(
        agency_id=agency_id,
        person_id=person_id,
        company_id=company_id,
        designation=designation,
        relationship_status=relationship_status,
        evidence_url=canonicalize_url(evidence_url),
        is_current=True,
    )
    db.add(role)
    db.flush()
    return role


def upsert_podcast(
    db: Session,
    linkedin_post_id: int | None,
    host_id: int | None,
    podcast_name: str,
    episode_title: str | None = None,
    original_podcast_url: str | None = None,
    youtube_channel_name: str | None = None,
    youtube_channel_url: str | None = None,
    discovery_method: str = "unknown",
    confidence_score: int = 0,
    manual_review_required: bool = False,
    research_notes: str | None = None,
    agency_id: str = "default",
) -> Podcast:
    existing: Podcast | None = None
    if linkedin_post_id is not None:
        existing = db.query(Podcast).filter(Podcast.linkedin_post_id == linkedin_post_id).first()

    norm_orig = canonicalize_url(original_podcast_url)
    norm_yt = canonicalize_url(youtube_channel_url)

    if existing:
        existing.host_id = host_id or existing.host_id
        existing.podcast_name = podcast_name or existing.podcast_name
        existing.episode_title = episode_title or existing.episode_title
        existing.original_podcast_url = norm_orig or existing.original_podcast_url
        existing.youtube_channel_name = youtube_channel_name or existing.youtube_channel_name
        existing.youtube_channel_url = norm_yt or existing.youtube_channel_url
        existing.discovery_method = discovery_method
        existing.confidence_score = max(existing.confidence_score, confidence_score)
        existing.manual_review_required = manual_review_required
        if research_notes:
            existing.research_notes = research_notes
        db.flush()
        return existing

    podcast = Podcast(
        agency_id=agency_id,
        linkedin_post_id=linkedin_post_id,
        host_id=host_id,
        podcast_name=podcast_name,
        episode_title=episode_title,
        original_podcast_url=norm_orig,
        youtube_channel_name=youtube_channel_name,
        youtube_channel_url=norm_yt,
        discovery_method=discovery_method,
        confidence_score=confidence_score,
        manual_review_required=manual_review_required,
        research_notes=research_notes,
    )
    db.add(podcast)
    db.flush()
    return podcast


def upsert_contact(
    db: Session,
    person_id: int | None,
    podcast_id: int | None,
    email: str | None,
    email_category: str,
    phone: str | None,
    official_website: str | None,
    contact_page: str | None,
    verification_status: str,
    confidence_score: int,
    research_notes: str | None,
    source_type: str,
    source_url: str | None,
    discovery_method: str,
    agency_id: str = "default",
) -> Contact:
    norm_email = email.strip().lower() if email else None
    existing: Contact | None = None
    if norm_email:
        existing = (
            db.query(Contact)
            .filter(
                Contact.agency_id == agency_id,
                func.lower(Contact.email) == norm_email,
                Contact.podcast_id == podcast_id,
            )
            .first()
        )
    elif podcast_id is not None:
        existing = (
            db.query(Contact)
            .filter(
                Contact.agency_id == agency_id,
                Contact.podcast_id == podcast_id,
                Contact.email.is_(None),
            )
            .first()
        )

    if existing:
        if phone and not existing.phone:
            existing.phone = phone
        if official_website and not existing.official_website:
            existing.official_website = canonicalize_url(official_website)
        if contact_page and not existing.contact_page:
            existing.contact_page = canonicalize_url(contact_page)
        if confidence_score >= existing.confidence_score:
            existing.verification_status = verification_status
            existing.confidence_score = confidence_score
        if research_notes:
            existing.research_notes = research_notes
        contact = existing
    else:
        contact = Contact(
            agency_id=agency_id,
            person_id=person_id,
            podcast_id=podcast_id,
            email=norm_email,
            email_category=email_category,
            phone=phone,
            official_website=canonicalize_url(official_website),
            contact_page=canonicalize_url(contact_page),
            contact_status="active" if norm_email else "needs_review",
            verification_status=verification_status,
            confidence_score=confidence_score,
            research_notes=research_notes,
        )
        db.add(contact)
    db.flush()

    if source_url:
        norm_src = canonicalize_url(source_url) or source_url
        src_exists = (
            db.query(ContactSource)
            .filter(
                ContactSource.contact_id == contact.id,
                ContactSource.source_type == source_type,
                ContactSource.source_url == norm_src,
            )
            .first()
        )
        if not src_exists:
            db.add(
                ContactSource(
                    contact_id=contact.id,
                    source_type=source_type,
                    source_url=norm_src,
                    discovery_method=discovery_method,
                    verification_notes=research_notes,
                )
            )
            db.flush()

    return contact
