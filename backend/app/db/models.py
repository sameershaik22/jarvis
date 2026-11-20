from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ResearchTask(Base):
    __tablename__ = "research_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    user_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    search_keyword: Mapped[str] = mapped_column(String(255), default="Real Estate Podcast", nullable=False)
    task_status: Mapped[str] = mapped_column(String(50), default="pending", index=True, nullable=False)
    current_stage: Mapped[str] = mapped_column(String(120), default="initialized", nullable=False)
    current_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_posts: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    quality_threshold: Mapped[int] = mapped_column(Integer, default=65, nullable=False)
    checkpoint_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    posts: Mapped[list["LinkedinPost"]] = relationship(
        "LinkedinPost", back_populates="research_task", cascade="all, delete-orphan"
    )
    activity_logs: Mapped[list["AgentActivityLog"]] = relationship(
        "AgentActivityLog", back_populates="research_task", cascade="all, delete-orphan"
    )


class LinkedinPost(Base):
    __tablename__ = "linkedin_posts"
    __table_args__ = (
        UniqueConstraint("agency_id", "post_url", name="uq_linkedin_posts_agency_post_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    research_task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    post_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    post_caption: Mapped[str] = mapped_column(Text, default="", nullable=False)
    posting_account: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    posting_account_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    keywords_matched: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    raw_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    research_task: Mapped["ResearchTask"] = relationship("ResearchTask", back_populates="posts")
    quality_assessment: Mapped["QualityAssessment | None"] = relationship(
        "QualityAssessment", back_populates="linkedin_post", uselist=False, cascade="all, delete-orphan"
    )
    podcast: Mapped["Podcast | None"] = relationship(
        "Podcast", back_populates="linkedin_post", uselist=False
    )


class QualityAssessment(Base):
    __tablename__ = "quality_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    linkedin_post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("linkedin_posts.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    video_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    video_quality: Mapped[str] = mapped_column(String(32), default="Medium", nullable=False)
    audio_quality: Mapped[str] = mapped_column(String(32), default="Unknown", nullable=False)
    lighting: Mapped[str] = mapped_column(String(32), default="Average", nullable=False)
    setup_quality: Mapped[str] = mapped_column(String(32), default="Average", nullable=False)
    content_relevance: Mapped[str] = mapped_column(String(64), default="Relevant", nullable=False)
    qualification_status: Mapped[str] = mapped_column(
        String(32), default="Manual Review", index=True, nullable=False
    )
    assessment_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    frame_paths: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    audio_inspected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    linkedin_post: Mapped["LinkedinPost"] = relationship("LinkedinPost", back_populates="quality_assessment")


class Person(Base):
    __tablename__ = "people"
    __table_args__ = (
        UniqueConstraint("agency_id", "linkedin_url", name="uq_people_agency_linkedin_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    linkedin_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role_type: Mapped[str] = mapped_column(String(50), default="host", nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    identity_status: Mapped[str] = mapped_column(
        String(50), default="Unverified", index=True, nullable=False
    )
    confidence_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_review_required: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    podcasts: Mapped[list["Podcast"]] = relationship("Podcast", back_populates="host")
    company_roles: Mapped[list["PersonCompanyRole"]] = relationship(
        "PersonCompanyRole", back_populates="person", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["Contact"]] = relationship("Contact", back_populates="person")


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("agency_id", "linkedin_url", name="uq_companies_agency_linkedin_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    linkedin_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    website: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    person_roles: Mapped[list["PersonCompanyRole"]] = relationship(
        "PersonCompanyRole", back_populates="company", cascade="all, delete-orphan"
    )


class PersonCompanyRole(Base):
    __tablename__ = "person_company_roles"
    __table_args__ = (
        UniqueConstraint("person_id", "company_id", name="uq_person_company"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    person_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("people.id", ondelete="CASCADE"), index=True, nullable=False
    )
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    designation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    relationship_status: Mapped[str] = mapped_column(String(64), default="Unverified", nullable=False)
    evidence_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    person: Mapped["Person"] = relationship("Person", back_populates="company_roles")
    company: Mapped["Company"] = relationship("Company", back_populates="person_roles")


class Podcast(Base):
    __tablename__ = "podcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    linkedin_post_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("linkedin_posts.id", ondelete="SET NULL"), unique=True, nullable=True
    )
    host_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("people.id", ondelete="SET NULL"), index=True, nullable=True
    )
    podcast_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    episode_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_podcast_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    youtube_channel_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    youtube_channel_url: Mapped[str | None] = mapped_column(String(1024), index=True, nullable=True)
    discovery_method: Mapped[str] = mapped_column(String(64), default="unknown", nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_review_required: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    research_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    linkedin_post: Mapped["LinkedinPost | None"] = relationship("LinkedinPost", back_populates="podcast")
    host: Mapped["Person | None"] = relationship("Person", back_populates="podcasts")
    contacts: Mapped[list["Contact"]] = relationship("Contact", back_populates="podcast")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    person_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("people.id", ondelete="SET NULL"), index=True, nullable=True
    )
    podcast_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("podcasts.id", ondelete="SET NULL"), index=True, nullable=True
    )
    email: Mapped[str | None] = mapped_column(String(320), index=True, nullable=True)
    email_category: Mapped[str] = mapped_column(String(64), default="unknown", nullable=False)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    official_website: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    contact_page: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    contact_status: Mapped[str] = mapped_column(String(64), default="active", nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(64), default="Unverified", index=True, nullable=False
    )
    confidence_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    research_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    person: Mapped["Person | None"] = relationship("Person", back_populates="contacts")
    podcast: Mapped["Podcast | None"] = relationship("Podcast", back_populates="contacts")
    sources: Mapped[list["ContactSource"]] = relationship(
        "ContactSource", back_populates="contact", cascade="all, delete-orphan"
    )


class ContactSource(Base):
    __tablename__ = "contact_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contact_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contacts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    discovery_method: Mapped[str] = mapped_column(String(120), nullable=False)
    verification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    contact: Mapped["Contact"] = relationship("Contact", back_populates="sources")


class ResearchEvidence(Base):
    __tablename__ = "research_evidence"
    __table_args__ = (
        Index("ix_research_evidence_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    research_task_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("research_tasks.id", ondelete="SET NULL"), index=True, nullable=True
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_information: Mapped[str] = mapped_column(Text, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    research_task_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("research_tasks.id", ondelete="SET NULL"), index=True, nullable=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AgentActivityLog(Base):
    __tablename__ = "agent_activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    research_task_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("research_tasks.id", ondelete="CASCADE"), index=True, nullable=True
    )
    level: Mapped[str] = mapped_column(String(20), default="INFO", nullable=False)
    stage: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    screenshot_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    research_task: Mapped["ResearchTask | None"] = relationship(
        "ResearchTask", back_populates="activity_logs"
    )


class ExportLog(Base):
    __tablename__ = "export_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    export_format: Mapped[str] = mapped_column(String(16), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    filter_preset: Mapped[str] = mapped_column(String(64), default="all", nullable=False)
    filters_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = (
        UniqueConstraint("agency_id", "key", name="uq_app_settings_agency_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
