"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-02
"""
from alembic import op

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
    CREATE TABLE raw_messages (
        id              BIGSERIAL PRIMARY KEY,
        telegram_msg_id BIGINT NOT NULL,
        channel_id      BIGINT NOT NULL,
        channel_name    TEXT NOT NULL,
        message_text    TEXT,
        message_date    TIMESTAMPTZ NOT NULL,
        views           INTEGER,
        forwards        INTEGER,
        replies         INTEGER,
        reactions_json  JSONB,
        media_type      TEXT,
        media_file_id   TEXT,
        forward_from    TEXT,
        ingested_at     TIMESTAMPTZ DEFAULT NOW(),
        processed       BOOLEAN DEFAULT FALSE,
        failed_attempts INTEGER DEFAULT 0,
        text_hash       TEXT,
        UNIQUE(channel_id, telegram_msg_id)
    )
    """)
    op.execute("CREATE INDEX idx_raw_messages_date ON raw_messages(message_date DESC)")
    op.execute("CREATE INDEX idx_raw_messages_unprocessed ON raw_messages(processed) WHERE processed = FALSE")
    op.execute("CREATE INDEX idx_raw_messages_hash ON raw_messages(text_hash)")

    op.execute("""
    CREATE TABLE claims (
        id                  BIGSERIAL PRIMARY KEY,
        claim_text          TEXT NOT NULL,
        source_language     TEXT,
        first_seen_at       TIMESTAMPTZ NOT NULL,
        last_seen_at        TIMESTAMPTZ NOT NULL,
        occurrence_count    INTEGER DEFAULT 1,
        entities_json       JSONB,
        category            TEXT,
        temporal            TEXT,
        checkworthy_score   FLOAT,
        source_attribution  TEXT,
        urgency_signals     BOOLEAN DEFAULT FALSE,
        message_type        TEXT,
        embedding           VECTOR(384),
        credibility_score   FLOAT,
        virality_score      FLOAT,
        status              TEXT DEFAULT 'unreviewed',
        created_at          TIMESTAMPTZ DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX idx_claims_status ON claims(status)")
    op.execute("CREATE INDEX idx_claims_virality ON claims(virality_score DESC NULLS LAST)")
    op.execute("CREATE INDEX idx_claims_last_seen ON claims(last_seen_at DESC)")
    op.execute("CREATE INDEX idx_claims_created ON claims(created_at DESC)")

    op.execute("""
    CREATE TABLE claim_sources (
        id              BIGSERIAL PRIMARY KEY,
        claim_id        BIGINT REFERENCES claims(id) ON DELETE RESTRICT,
        raw_message_id  BIGINT REFERENCES raw_messages(id) ON DELETE RESTRICT,
        channel_name    TEXT NOT NULL,
        message_date    TIMESTAMPTZ NOT NULL
    )
    """)
    op.execute("CREATE INDEX idx_claim_sources_claim ON claim_sources(claim_id)")

    op.execute("""
    CREATE TABLE checkpoints (
        channel_id   BIGINT PRIMARY KEY,
        channel_name TEXT NOT NULL,
        last_msg_id  BIGINT NOT NULL DEFAULT 0,
        updated_at   TIMESTAMPTZ DEFAULT NOW()
    )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS claim_sources")
    op.execute("DROP TABLE IF EXISTS claims")
    op.execute("DROP TABLE IF EXISTS raw_messages")
    op.execute("DROP TABLE IF EXISTS checkpoints")
    op.execute("DROP EXTENSION IF EXISTS vector")
