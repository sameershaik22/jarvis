"""Initial YoursBuddy AI schema (agency-isolation ready)

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("user_instruction", sa.Text(), nullable=False),
        sa.Column("search_keyword", sa.String(length=255), nullable=False),
        sa.Column("task_status", sa.String(length=50), nullable=False),
        sa.Column("current_stage", sa.String(length=120), nullable=False),
        sa.Column("current_url", sa.Text(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("max_posts", sa.Integer(), nullable=False),
        sa.Column("quality_threshold", sa.Integer(), nullable=False),
        sa.Column("checkpoint_data", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_tasks_agency_id", "research_tasks", ["agency_id"])
    op.create_index("ix_research_tasks_task_status", "research_tasks", ["task_status"])

    op.create_table(
        "linkedin_posts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("research_task_id", sa.Integer(), nullable=False),
        sa.Column("post_url", sa.String(length=1024), nullable=False),
        sa.Column("post_caption", sa.Text(), nullable=False),
        sa.Column("posting_account", sa.String(length=255), nullable=False),
        sa.Column("posting_account_url", sa.String(length=1024), nullable=True),
        sa.Column("video_url", sa.String(length=1024), nullable=True),
        sa.Column("keywords_matched", sa.JSON(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_label", sa.String(length=120), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["research_task_id"], ["research_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agency_id", "post_url", name="uq_linkedin_posts_agency_post_url"),
    )
    op.create_index("ix_linkedin_posts_agency_id", "linkedin_posts", ["agency_id"])
    op.create_index("ix_linkedin_posts_research_task_id", "linkedin_posts", ["research_task_id"])

    op.create_table(
        "quality_assessments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("linkedin_post_id", sa.Integer(), nullable=False),
        sa.Column("video_score", sa.Integer(), nullable=False),
        sa.Column("video_quality", sa.String(length=32), nullable=False),
        sa.Column("audio_quality", sa.String(length=32), nullable=False),
        sa.Column("lighting", sa.String(length=32), nullable=False),
        sa.Column("setup_quality", sa.String(length=32), nullable=False),
        sa.Column("content_relevance", sa.String(length=64), nullable=False),
        sa.Column("qualification_status", sa.String(length=32), nullable=False),
        sa.Column("assessment_notes", sa.Text(), nullable=False),
        sa.Column("frame_paths", sa.JSON(), nullable=True),
        sa.Column("audio_inspected", sa.Boolean(), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["linkedin_post_id"], ["linkedin_posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("linkedin_post_id"),
    )
    op.create_index("ix_quality_assessments_agency_id", "quality_assessments", ["agency_id"])
    op.create_index("ix_quality_assessments_qualification_status", "quality_assessments", ["qualification_status"])

    op.create_table(
        "people",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("linkedin_url", sa.String(length=1024), nullable=True),
        sa.Column("designation", sa.String(length=255), nullable=True),
        sa.Column("role_type", sa.String(length=50), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("identity_status", sa.String(length=50), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("manual_review_required", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agency_id", "linkedin_url", name="uq_people_agency_linkedin_url"),
    )
    op.create_index("ix_people_agency_id", "people", ["agency_id"])
    op.create_index("ix_people_full_name", "people", ["full_name"])
    op.create_index("ix_people_identity_status", "people", ["identity_status"])
    op.create_index("ix_people_manual_review_required", "people", ["manual_review_required"])

    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("linkedin_url", sa.String(length=1024), nullable=True),
        sa.Column("website", sa.String(length=1024), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("industry", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agency_id", "linkedin_url", name="uq_companies_agency_linkedin_url"),
    )
    op.create_index("ix_companies_agency_id", "companies", ["agency_id"])
    op.create_index("ix_companies_company_name", "companies", ["company_name"])

    op.create_table(
        "person_company_roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("designation", sa.String(length=255), nullable=True),
        sa.Column("relationship_status", sa.String(length=64), nullable=False),
        sa.Column("evidence_url", sa.String(length=1024), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["people.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "company_id", name="uq_person_company"),
    )
    op.create_index("ix_person_company_roles_agency_id", "person_company_roles", ["agency_id"])
    op.create_index("ix_person_company_roles_person_id", "person_company_roles", ["person_id"])
    op.create_index("ix_person_company_roles_company_id", "person_company_roles", ["company_id"])

    op.create_table(
        "podcasts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("linkedin_post_id", sa.Integer(), nullable=True),
        sa.Column("host_id", sa.Integer(), nullable=True),
        sa.Column("podcast_name", sa.String(length=255), nullable=False),
        sa.Column("episode_title", sa.String(length=500), nullable=True),
        sa.Column("original_podcast_url", sa.String(length=1024), nullable=True),
        sa.Column("youtube_channel_name", sa.String(length=255), nullable=True),
        sa.Column("youtube_channel_url", sa.String(length=1024), nullable=True),
        sa.Column("discovery_method", sa.String(length=64), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("manual_review_required", sa.Boolean(), nullable=False),
        sa.Column("research_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["host_id"], ["people.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linkedin_post_id"], ["linkedin_posts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("linkedin_post_id"),
    )
    op.create_index("ix_podcasts_agency_id", "podcasts", ["agency_id"])
    op.create_index("ix_podcasts_host_id", "podcasts", ["host_id"])
    op.create_index("ix_podcasts_podcast_name", "podcasts", ["podcast_name"])
    op.create_index("ix_podcasts_youtube_channel_url", "podcasts", ["youtube_channel_url"])
    op.create_index("ix_podcasts_manual_review_required", "podcasts", ["manual_review_required"])

    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column("podcast_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("email_category", sa.String(length=64), nullable=False),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("official_website", sa.String(length=1024), nullable=True),
        sa.Column("contact_page", sa.String(length=1024), nullable=True),
        sa.Column("contact_status", sa.String(length=64), nullable=False),
        sa.Column("verification_status", sa.String(length=64), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("research_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["people.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["podcast_id"], ["podcasts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contacts_agency_id", "contacts", ["agency_id"])
    op.create_index("ix_contacts_person_id", "contacts", ["person_id"])
    op.create_index("ix_contacts_podcast_id", "contacts", ["podcast_id"])
    op.create_index("ix_contacts_email", "contacts", ["email"])
    op.create_index("ix_contacts_verification_status", "contacts", ["verification_status"])

    op.create_table(
        "contact_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("discovery_method", sa.String(length=120), nullable=False),
        sa.Column("verification_notes", sa.Text(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contact_sources_contact_id", "contact_sources", ["contact_id"])

    op.create_table(
        "research_evidence",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("research_task_id", sa.Integer(), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("extracted_information", sa.Text(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["research_task_id"], ["research_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_evidence_agency_id", "research_evidence", ["agency_id"])
    op.create_index("ix_research_evidence_entity", "research_evidence", ["entity_type", "entity_id"])
    op.create_index("ix_research_evidence_research_task_id", "research_evidence", ["research_task_id"])

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("research_task_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["research_task_id"], ["research_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_messages_agency_id", "agent_messages", ["agency_id"])
    op.create_index("ix_agent_messages_research_task_id", "agent_messages", ["research_task_id"])

    op.create_table(
        "agent_activity_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("research_task_id", sa.Integer(), nullable=True),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("stage", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("screenshot_path", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["research_task_id"], ["research_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_activity_logs_agency_id", "agent_activity_logs", ["agency_id"])
    op.create_index("ix_agent_activity_logs_research_task_id", "agent_activity_logs", ["research_task_id"])

    op.create_table(
        "export_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("export_format", sa.String(length=16), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("filter_preset", sa.String(length=64), nullable=False),
        sa.Column("filters_json", sa.JSON(), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_export_logs_agency_id", "export_logs", ["agency_id"])

    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agency_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agency_id", "key", name="uq_app_settings_agency_key"),
    )
    op.create_index("ix_app_settings_agency_id", "app_settings", ["agency_id"])


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_table("export_logs")
    op.drop_table("agent_activity_logs")
    op.drop_table("agent_messages")
    op.drop_table("research_evidence")
    op.drop_table("contact_sources")
    op.drop_table("contacts")
    op.drop_table("podcasts")
    op.drop_table("person_company_roles")
    op.drop_table("companies")
    op.drop_table("people")
    op.drop_table("quality_assessments")
    op.drop_table("linkedin_posts")
    op.drop_table("research_tasks")
