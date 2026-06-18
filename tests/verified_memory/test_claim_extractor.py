from verified_memory.ingestion.claim_extractor import extract_claims_from_chunk
from verified_memory.models import DocumentChunk


def _chunk(text):
    return DocumentChunk(
        document_id="doc-1",
        document_name="sop.md",
        document_path="/tmp/sop.md",
        chunk_id="doc-1:chunk:0001",
        text=text,
        line_start=10,
        line_end=10 + len(text.splitlines()) - 1,
    )


def test_extracts_requirement_claim_from_must():
    claims = extract_claims_from_chunk(_chunk("Users must connect to Wi-Fi during OOBE."))

    assert len(claims) == 1
    assert claims[0].claim_type == "requirement"
    assert claims[0].claim == "Users must connect to Wi-Fi during OOBE."


def test_extracts_prohibition_claim_from_do_not_or_never():
    claims = extract_claims_from_chunk(_chunk("Do not skip Autopilot enrollment."))

    assert len(claims) == 1
    assert claims[0].claim_type == "prohibition"


def test_extracts_recommendation_claim_from_should():
    claims = extract_claims_from_chunk(_chunk("Admins should verify Teams permissions."))

    assert len(claims) == 1
    assert claims[0].claim_type == "recommendation"


def test_extracts_condition_claim_from_if():
    claims = extract_claims_from_chunk(_chunk("If Wi-Fi is missing, load drivers from USB."))

    assert len(claims) == 1
    assert claims[0].claim_type == "condition"


def test_extracts_japanese_policy_term():
    claims = extract_claims_from_chunk(_chunk("利用者はVPNに接続してください。"))

    assert len(claims) == 1
    assert claims[0].claim_type == "instruction"


def test_ignores_ordinary_non_instructional_lines():
    claims = extract_claims_from_chunk(_chunk("Teams is a collaboration app."))

    assert claims == []


def test_extracted_claim_defaults_status_confidence_and_privacy():
    claim = extract_claims_from_chunk(_chunk("Users must connect to Wi-Fi."))[0]

    assert claim.status == "unverified"
    assert claim.confidence == "low"
    assert claim.sensitivity == "private"
    assert claim.allowed_web_search is False


def test_extracted_claim_has_source_ref_with_document_chunk_line_and_quote():
    chunk = _chunk("Intro\nUsers must connect to Wi-Fi.")

    claim = extract_claims_from_chunk(chunk)[0]
    ref = claim.source_refs[0]

    assert ref.source_type == "local_document"
    assert ref.document_name == "sop.md"
    assert ref.document_path == "/tmp/sop.md"
    assert ref.chunk_id == "doc-1:chunk:0001"
    assert ref.line_start == 11
    assert ref.line_end == 11
    assert ref.quote == "Users must connect to Wi-Fi."


def test_extracted_claim_does_not_invent_text_beyond_source_line():
    source_line = "Users must connect to Wi-Fi during OOBE before continuing Autopilot enrollment."

    claim = extract_claims_from_chunk(_chunk(source_line))[0]

    assert claim.claim == source_line
