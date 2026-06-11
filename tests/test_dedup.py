import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone
from src.processing.dedup import (
    compute_text_hash,
    find_by_text_hash,
    find_candidate_claims,
    resolve_dedup,
    insert_claim_relation,
    merge_claim,
    insert_claim,
    copy_claims_from_message,
)
from src.processing.schemas import ClaimRelation, NLILabel


class FakeNLIChecker:
    """Protocol-compatible NLI checker driven by a lookup table."""

    def __init__(self, relations: dict[str, NLILabel]):
        self._relations = relations

    def check_relation(self, text_a: str, text_b: str) -> NLILabel:
        return self._relations.get(text_b, NLILabel.neutral)


def test_same_text_produces_same_hash():
    h1 = compute_text_hash("The FDA approved a new vaccine today.")
    h2 = compute_text_hash("The FDA approved a new vaccine today.")
    assert h1 == h2


def test_different_texts_produce_different_hashes():
    h1 = compute_text_hash("The FDA approved a new vaccine today.")
    h2 = compute_text_hash("The WHO met in Geneva to discuss boosters.")
    assert h1 != h2


def test_hash_normalizes_whitespace_and_case():
    h1 = compute_text_hash("  The FDA approved a vaccine  ")
    h2 = compute_text_hash("the fda approved a vaccine")
    assert h1 == h2


@pytest.mark.asyncio
async def test_find_by_text_hash_returns_none_when_not_found(mock_session):
    mock_session.execute.return_value.fetchone.return_value = None
    result = await find_by_text_hash(mock_session, "abc123", exclude_id=1)
    assert result is None


@pytest.mark.asyncio
async def test_find_by_text_hash_returns_id_when_found(mock_session):
    mock_session.execute.return_value.fetchone.return_value = (42,)
    result = await find_by_text_hash(mock_session, "abc123", exclude_id=1)
    assert result == 42


@pytest.mark.asyncio
async def test_find_candidate_claims_returns_empty_when_no_match(mock_session):
    mock_session.execute.return_value.fetchall.return_value = []
    result = await find_candidate_claims(mock_session, [0.1] * 768)
    assert result == []


@pytest.mark.asyncio
async def test_find_candidate_claims_returns_id_text_pairs(mock_session):
    mock_session.execute.return_value.fetchall.return_value = [
        (7, "Vaccine X causes side effects"),
        (9, "Vaccine X is dangerous"),
    ]
    result = await find_candidate_claims(mock_session, [0.1] * 768)
    assert result == [(7, "Vaccine X causes side effects"), (9, "Vaccine X is dangerous")]


@pytest.mark.asyncio
async def test_resolve_dedup_entailment_becomes_merge_target(mock_session):
    nli = FakeNLIChecker({"Vaccine X was approved by the FDA": NLILabel.entailment})
    merge_id, contradictions = await resolve_dedup(
        mock_session, nli, "The FDA approved Vaccine X",
        [(7, "Vaccine X was approved by the FDA")],
    )
    assert merge_id == 7
    assert contradictions == []


@pytest.mark.asyncio
async def test_resolve_dedup_contradiction_never_merges(mock_session):
    nli = FakeNLIChecker({"Vaccine X was NOT approved by the FDA": NLILabel.contradiction})
    merge_id, contradictions = await resolve_dedup(
        mock_session, nli, "The FDA approved Vaccine X",
        [(7, "Vaccine X was NOT approved by the FDA")],
    )
    assert merge_id is None
    assert contradictions == [7]


@pytest.mark.asyncio
async def test_resolve_dedup_neutral_ignored(mock_session):
    nli = FakeNLIChecker({"Vaccine Y entered trials": NLILabel.neutral})
    merge_id, contradictions = await resolve_dedup(
        mock_session, nli, "The FDA approved Vaccine X",
        [(7, "Vaccine Y entered trials")],
    )
    assert merge_id is None
    assert contradictions == []


@pytest.mark.asyncio
async def test_resolve_dedup_first_entailment_wins_contradictions_collected(mock_session):
    nli = FakeNLIChecker({
        "FDA approved Vaccine X": NLILabel.entailment,
        "FDA also approved Vaccine X": NLILabel.entailment,
        "FDA rejected Vaccine X": NLILabel.contradiction,
    })
    merge_id, contradictions = await resolve_dedup(
        mock_session, nli, "The FDA approved Vaccine X",
        [
            (1, "FDA approved Vaccine X"),
            (2, "FDA rejected Vaccine X"),
            (3, "FDA also approved Vaccine X"),
        ],
    )
    assert merge_id == 1
    assert contradictions == [2]


@pytest.mark.asyncio
async def test_resolve_dedup_empty_candidates(mock_session):
    nli = FakeNLIChecker({})
    merge_id, contradictions = await resolve_dedup(mock_session, nli, "Some claim", [])
    assert merge_id is None
    assert contradictions == []


@pytest.mark.asyncio
async def test_insert_claim_relation_executes_insert(mock_session):
    await insert_claim_relation(mock_session, claim_a=1, claim_b=2, relation=ClaimRelation.contradicts)
    mock_session.execute.assert_called_once()
    params = mock_session.execute.call_args[0][1]
    assert params == {"claim_a": 1, "claim_b": 2, "relation": "contradicts"}


@pytest.mark.asyncio
async def test_merge_claim_updates_occurrence_count(mock_session):
    await merge_claim(mock_session, claim_id=5, raw_message_id=10,
                      channel_name="TestChannel", message_date=datetime.now(timezone.utc),
                      channel_id=100)
    assert mock_session.execute.call_count == 2


@pytest.mark.asyncio
async def test_insert_claim_returns_id(mock_session, sample_extraction_result):
    first_result = MagicMock()
    first_result.fetchone.return_value = (99,)
    cluster_result = MagicMock()
    sources_result = MagicMock()
    mock_session.execute.side_effect = [first_result, cluster_result, sources_result]

    claim = sample_extraction_result.claims[0]
    meta = sample_extraction_result.meta
    message = {"id": 1, "channel_id": 100, "channel_name": "TestChannel",
               "message_date": datetime.now(timezone.utc)}

    claim_id = await insert_claim(
        mock_session, claim=claim, embedding=[0.1] * 768,
        source_language="en", urgency=False, meta=meta, message=message,
    )
    assert claim_id == 99
    # claim insert + cluster_id self-assign + claim_sources insert
    assert mock_session.execute.call_count == 3


@pytest.mark.asyncio
async def test_insert_claim_writes_topic_and_framing(mock_session, sample_extraction_result):
    first_result = MagicMock()
    first_result.fetchone.return_value = (99,)
    mock_session.execute.side_effect = [first_result, MagicMock(), MagicMock()]

    claim = sample_extraction_result.claims[0]
    meta = sample_extraction_result.meta
    message = {"id": 1, "channel_id": 100, "channel_name": "TestChannel",
               "message_date": datetime.now(timezone.utc)}

    await insert_claim(
        mock_session, claim=claim, embedding=[0.1] * 768,
        source_language="en", urgency=False, meta=meta, message=message,
    )
    params = mock_session.execute.call_args_list[0][0][1]
    assert params["topic"] == "health"
    assert params["conspiratorial_framing"] is False


@pytest.mark.asyncio
async def test_copy_claims_executes_insert_and_update(mock_session):
    await copy_claims_from_message(
        mock_session, source_msg_id=1, target_msg_id=2,
        channel_name="TestChannel", message_date=datetime.now(timezone.utc),
        channel_id=100,
    )
    assert mock_session.execute.call_count == 2
