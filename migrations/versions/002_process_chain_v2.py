"""process chain v2: topic taxonomy, multilingual embeddings, NLI dedup

Revision ID: 002
Revises: 001
Create Date: 2026-06-10
"""
from alembic import op

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Taxonomy: category -> topic; existing 'conspiracy' rows fold into 'other'
    op.execute("ALTER TABLE claims RENAME COLUMN category TO topic")
    op.execute("UPDATE claims SET topic = 'other' WHERE topic = 'conspiracy'")

    op.execute("ALTER TABLE claims DROP COLUMN credibility_score")
    op.execute("ALTER TABLE claims DROP COLUMN message_type")

    # multilingual-e5-base is 768-dim; pgvector cannot alter dimensions in-place.
    # Old 384-dim embeddings are useless under the new model anyway.
    op.execute("ALTER TABLE claims DROP COLUMN embedding")
    op.execute("ALTER TABLE claims ADD COLUMN embedding VECTOR(768)")

    op.execute("""
    ALTER TABLE claims
        ADD COLUMN cluster_id              BIGINT,
        ADD COLUMN narrative_id            BIGINT,
        ADD COLUMN claim_text_display_en   TEXT,
        ADD COLUMN conspiratorial_framing  BOOLEAN DEFAULT FALSE,
        ADD COLUMN factcheck_match_id      BIGINT,
        ADD COLUMN source_reliability      FLOAT,
        ADD COLUMN priority_score          FLOAT,
        ADD COLUMN scrubbed                BOOLEAN DEFAULT FALSE
    """)
    op.execute("CREATE INDEX idx_claims_cluster ON claims(cluster_id)")

    op.execute("""
    CREATE TABLE claim_relations (
        claim_a  BIGINT REFERENCES claims(id),
        claim_b  BIGINT REFERENCES claims(id),
        relation TEXT NOT NULL,
        PRIMARY KEY (claim_a, claim_b)
    )
    """)

    op.execute("ALTER TABLE claim_sources ADD COLUMN channel_id BIGINT")


def downgrade() -> None:
    op.execute("ALTER TABLE claim_sources DROP COLUMN channel_id")
    op.execute("DROP TABLE IF EXISTS claim_relations")
    op.execute("DROP INDEX IF EXISTS idx_claims_cluster")
    op.execute("""
    ALTER TABLE claims
        DROP COLUMN cluster_id,
        DROP COLUMN narrative_id,
        DROP COLUMN claim_text_display_en,
        DROP COLUMN conspiratorial_framing,
        DROP COLUMN factcheck_match_id,
        DROP COLUMN source_reliability,
        DROP COLUMN priority_score,
        DROP COLUMN scrubbed
    """)
    op.execute("ALTER TABLE claims DROP COLUMN embedding")
    op.execute("ALTER TABLE claims ADD COLUMN embedding VECTOR(384)")
    op.execute("ALTER TABLE claims ADD COLUMN credibility_score FLOAT")
    op.execute("ALTER TABLE claims ADD COLUMN message_type TEXT")
    op.execute("ALTER TABLE claims RENAME COLUMN topic TO category")
