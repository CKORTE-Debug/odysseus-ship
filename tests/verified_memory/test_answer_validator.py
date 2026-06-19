from verified_memory.prompting import VerifiedMemoryPrompt
from verified_memory.validation import validate_answer_against_prompt


def _prompt(*, refs=None, usable=None, chunks=None, not_confirmed=None, online=False):
    return VerifiedMemoryPrompt(
        system_message="system",
        user_message="user",
        evidence_blocks={
            "usable_verified_claims": usable or [],
            "local_evidence_chunks": chunks or [],
            "not_confirmed_claims": not_confirmed or [],
            "citation_source_refs": refs or [],
        },
        warnings=[],
        metadata={"answer_generated": False, "online_verification_performed": online},
    )


def _codes(result):
    return {issue.code for issue in result.issues}


def test_answer_with_allowed_citation_passes():
    prompt = _prompt(refs=["doc-1:chunk:0001"], chunks=[{"text": "Users must connect to Wi-Fi."}])

    result = validate_answer_against_prompt(prompt, "Users must connect to Wi-Fi. [doc-1:chunk:0001]")

    assert result.is_valid is True
    assert result.severity == "pass"
    assert result.used_citation_refs == ["doc-1:chunk:0001"]
    assert result.unknown_citation_refs == []


def test_unknown_citation_returns_invented_citation_error():
    prompt = _prompt(refs=["doc-1:chunk:0001"], chunks=[{"text": "Users must connect to Wi-Fi."}])

    result = validate_answer_against_prompt(prompt, "Users must connect to Wi-Fi. [doc-9:chunk:9999]")

    assert result.is_valid is False
    assert result.severity == "error"
    assert "invented_citation" in _codes(result)
    assert result.unknown_citation_refs == ["doc-9:chunk:9999"]


def test_no_citation_with_usable_evidence_returns_missing_citation_warning():
    prompt = _prompt(refs=["doc-1:chunk:0001"], chunks=[{"text": "Users must connect to Wi-Fi."}])

    result = validate_answer_against_prompt(prompt, "Users must connect to Wi-Fi.")

    assert result.is_valid is True
    assert result.severity == "warning"
    assert "missing_citation" in _codes(result)


def test_online_verification_claim_when_metadata_false_returns_error():
    prompt = _prompt(refs=["doc-1:chunk:0001"], chunks=[{"text": "Users must connect to Wi-Fi."}])

    result = validate_answer_against_prompt(prompt, "I checked online and confirmed this. [doc-1:chunk:0001]")

    assert result.is_valid is False
    assert "false_online_verification_claim" in _codes(result)


def test_based_on_provided_local_evidence_is_allowed():
    prompt = _prompt(refs=["doc-1:chunk:0001"], chunks=[{"text": "Users must connect to Wi-Fi."}])

    result = validate_answer_against_prompt(
        prompt,
        "Based on the provided local evidence, users must connect to Wi-Fi. [doc-1:chunk:0001]",
    )

    assert result.severity == "pass"
    assert "false_online_verification_claim" not in _codes(result)


def test_empty_answer_returns_empty_answer_error():
    result = validate_answer_against_prompt(_prompt(), "  ")

    assert result.is_valid is False
    assert result.severity == "error"
    assert "empty_answer" in _codes(result)


def test_no_evidence_confident_factual_answer_returns_answer_without_evidence_warning():
    result = validate_answer_against_prompt(_prompt(), "The SOP requires Wi-Fi during setup.")

    assert result.is_valid is True
    assert result.severity == "warning"
    assert "answer_without_evidence" in _codes(result)


def test_no_evidence_insufficient_evidence_phrasing_avoids_answer_without_evidence():
    result = validate_answer_against_prompt(_prompt(), "Insufficient evidence is available to answer.")

    assert result.is_valid is True
    assert result.severity == "warning"
    assert "unsupported_answer" in _codes(result)
    assert "answer_without_evidence" not in _codes(result)


def test_not_confirmed_claim_with_strong_certainty_returns_warning():
    prompt = _prompt(not_confirmed=[{"claim": "Users must connect to Wi-Fi during OOBE"}])

    result = validate_answer_against_prompt(prompt, "Users must connect to Wi-Fi during OOBE; this is confirmed.")

    assert result.is_valid is True
    assert result.severity == "warning"
    assert "not_confirmed_claim_presented_as_fact" in _codes(result)


def test_not_confirmed_claim_described_as_unverified_is_not_misuse():
    prompt = _prompt(not_confirmed=[{"claim": "Users must connect to Wi-Fi during OOBE"}])

    result = validate_answer_against_prompt(
        prompt,
        "Based on unverified memory, users may need Wi-Fi during OOBE and this needs verification.",
    )

    assert "not_confirmed_claim_presented_as_fact" not in _codes(result)
