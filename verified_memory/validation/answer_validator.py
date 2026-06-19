"""Deterministic validation for candidate verified-memory answers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from verified_memory.prompting import VerifiedMemoryPrompt

SEVERITY_PASS = "pass"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"

_ONLINE_VERIFICATION_PHRASES = [
    "i verified online",
    "i checked online",
    "according to current online sources",
    "confirmed from the web",
    "web search confirmed",
    "online verification shows",
]

_STRONG_CERTAINTY_PHRASES = [
    "is confirmed",
    "definitely",
    "must",
    "always",
    "will",
    "is required",
    "is verified",
    "confirmed fact",
]

_UNCERTAINTY_PHRASES = [
    "may",
    "might",
    "appears",
    "seems",
    "unverified",
    "stale",
    "not confirmed",
    "needs verification",
    "based on unverified memory",
]

_INSUFFICIENT_EVIDENCE_PHRASES = [
    "insufficient evidence",
    "not enough evidence",
    "not enough information",
    "i cannot determine",
    "the provided evidence does not say",
]

_CITATION_PATTERNS = [
    re.compile(r"\[([^\[\]\s][^\[\]]*?)\]"),
    re.compile(r"\(\s*Source:\s*([^\)]+?)\s*\)", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*Source:\s*([^\n]+)", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*cite:\s*([^\n]+)", re.IGNORECASE),
]


@dataclass(frozen=True)
class AnswerValidationIssue:
    code: str
    severity: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class AnswerValidationResult:
    is_valid: bool
    severity: str
    issues: list[AnswerValidationIssue]
    allowed_citation_refs: list[str]
    used_citation_refs: list[str]
    unknown_citation_refs: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "severity": self.severity,
            "issues": [issue.to_dict() for issue in self.issues],
            "allowed_citation_refs": list(self.allowed_citation_refs),
            "used_citation_refs": list(self.used_citation_refs),
            "unknown_citation_refs": list(self.unknown_citation_refs),
            "metadata": dict(self.metadata),
        }


def validate_answer_against_prompt(prompt: VerifiedMemoryPrompt, answer: str) -> AnswerValidationResult:
    """Validate a candidate answer against a deterministic verified-memory prompt."""

    normalized_answer = _normalize(answer)
    allowed_refs = _string_list(prompt.evidence_blocks.get("citation_source_refs", []))
    used_refs = _parse_citation_refs(answer or "")
    allowed_ref_set = set(allowed_refs)
    unknown_refs = [ref for ref in used_refs if ref not in allowed_ref_set]
    issues: list[AnswerValidationIssue] = []

    if not (answer or "").strip():
        issues.append(AnswerValidationIssue("empty_answer", SEVERITY_ERROR, "Candidate answer is empty."))
    elif unknown_refs:
        issues.append(
            AnswerValidationIssue(
                "invented_citation",
                SEVERITY_ERROR,
                "Answer cites source refs that were not included in the prompt.",
                {"unknown_citation_refs": unknown_refs},
            )
        )

    has_usable_evidence = _has_usable_evidence(prompt)
    has_any_evidence = bool(allowed_refs) or has_usable_evidence
    if normalized_answer and not used_refs and has_usable_evidence:
        issues.append(
            AnswerValidationIssue(
                "missing_citation",
                SEVERITY_WARNING,
                "Answer does not cite available usable evidence.",
            )
        )
    elif normalized_answer and not used_refs and not has_any_evidence:
        issues.append(
            AnswerValidationIssue(
                "unsupported_answer",
                SEVERITY_WARNING,
                "Answer has no citations and the prompt contains no supporting evidence.",
            )
        )

    if prompt.metadata.get("online_verification_performed") is False:
        phrase = _first_contained(normalized_answer, _ONLINE_VERIFICATION_PHRASES)
        if phrase:
            issues.append(
                AnswerValidationIssue(
                    "false_online_verification_claim",
                    SEVERITY_ERROR,
                    "Answer claims online verification even though the prompt metadata says none was performed.",
                    {"matched_phrase": phrase},
                )
            )

    if normalized_answer and _has_no_evidence(prompt) and not _first_contained(normalized_answer, _INSUFFICIENT_EVIDENCE_PHRASES):
        issues.append(
            AnswerValidationIssue(
                "answer_without_evidence",
                SEVERITY_WARNING,
                "Answer appears to provide a factual response despite no verified claims or local evidence chunks being available.",
            )
        )

    misuse = _not_confirmed_misuse(prompt, normalized_answer)
    if misuse:
        issues.append(misuse)

    severity = _overall_severity(issues)
    return AnswerValidationResult(
        is_valid=severity != SEVERITY_ERROR,
        severity=severity,
        issues=issues,
        allowed_citation_refs=allowed_refs,
        used_citation_refs=used_refs,
        unknown_citation_refs=unknown_refs,
        metadata={
            "answer_generated": False,
            "online_verification_performed": bool(prompt.metadata.get("online_verification_performed", False)),
            "issue_count": len(issues),
        },
    )


def _parse_citation_refs(answer: str) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for pattern in _CITATION_PATTERNS:
        for match in pattern.findall(answer):
            ref = _clean_ref(str(match))
            if ref and ref not in seen:
                seen.add(ref)
                refs.append(ref)
    return refs


def _clean_ref(value: str) -> str:
    return value.strip().strip(".,;: ")


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value if str(item)] if isinstance(value, list) else []


def _has_usable_evidence(prompt: VerifiedMemoryPrompt) -> bool:
    return bool(prompt.evidence_blocks.get("usable_verified_claims") or prompt.evidence_blocks.get("local_evidence_chunks"))


def _has_no_evidence(prompt: VerifiedMemoryPrompt) -> bool:
    return not prompt.evidence_blocks.get("usable_verified_claims") and not prompt.evidence_blocks.get("local_evidence_chunks")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()


def _first_contained(text: str, phrases: list[str]) -> str | None:
    for phrase in phrases:
        if phrase in text:
            return phrase
    return None


def _not_confirmed_misuse(prompt: VerifiedMemoryPrompt, normalized_answer: str) -> AnswerValidationIssue | None:
    if not normalized_answer or _first_contained(normalized_answer, _UNCERTAINTY_PHRASES):
        return None
    certainty_phrase = _first_contained(normalized_answer, _STRONG_CERTAINTY_PHRASES)
    if not certainty_phrase:
        return None
    for claim in prompt.evidence_blocks.get("not_confirmed_claims", []):
        claim_text = str(claim.get("claim", "")) if isinstance(claim, dict) else str(claim)
        normalized_claim = _normalize(claim_text)
        if normalized_claim and (normalized_claim in normalized_answer or _token_overlap(normalized_claim, normalized_answer) >= 0.7):
            return AnswerValidationIssue(
                "not_confirmed_claim_presented_as_fact",
                SEVERITY_WARNING,
                "Answer appears to present a not-confirmed claim as a confirmed fact.",
                {"claim": claim_text, "matched_certainty_phrase": certainty_phrase},
            )
    return None


def _token_overlap(left: str, right: str) -> float:
    left_tokens = {token for token in re.findall(r"[a-z0-9]+", left) if len(token) > 2}
    if not left_tokens:
        return 0.0
    right_tokens = {token for token in re.findall(r"[a-z0-9]+", right) if len(token) > 2}
    return len(left_tokens & right_tokens) / len(left_tokens)


def _overall_severity(issues: list[AnswerValidationIssue]) -> str:
    if any(issue.severity == SEVERITY_ERROR for issue in issues):
        return SEVERITY_ERROR
    if any(issue.severity == SEVERITY_WARNING for issue in issues):
        return SEVERITY_WARNING
    return SEVERITY_PASS
