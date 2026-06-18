"""Deterministic placeholder claim extraction from document chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass

from verified_memory.models import DocumentChunk, MemoryClaim, SourceRef

REQUIREMENT_TERMS = ("must", "required", "requires", "必須", "必要")
PROHIBITION_TERMS = ("must not", "do not", "never", "禁止", "してはいけません")
RECOMMENDATION_TERMS = ("should", "recommended", "推奨")
CONDITION_TERMS = ("if", "unless", "場合", "のみ")
INSTRUCTION_TERMS = ("always", "only", "してください")

_TERM_PATTERNS = {
    "requirement": [re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE) for term in REQUIREMENT_TERMS if term.isascii()],
    "prohibition": [re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE) for term in PROHIBITION_TERMS if term.isascii()],
    "recommendation": [re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE) for term in RECOMMENDATION_TERMS if term.isascii()],
    "condition": [re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE) for term in CONDITION_TERMS if term.isascii()],
    "instruction": [re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE) for term in INSTRUCTION_TERMS if term.isascii()],
}

_NON_ASCII_TERMS = {
    "requirement": tuple(term for term in REQUIREMENT_TERMS if not term.isascii()),
    "prohibition": tuple(term for term in PROHIBITION_TERMS if not term.isascii()),
    "recommendation": tuple(term for term in RECOMMENDATION_TERMS if not term.isascii()),
    "condition": tuple(term for term in CONDITION_TERMS if not term.isascii()),
    "instruction": tuple(term for term in INSTRUCTION_TERMS if not term.isascii()),
}


@dataclass(frozen=True)
class ClaimExtractionSettings:
    default_sensitivity: str = "private"
    allowed_web_search: bool = False


def extract_claims_from_chunk(
    chunk: DocumentChunk,
    *,
    default_sensitivity: str = "private",
    allowed_web_search: bool = False,
) -> list[MemoryClaim]:
    """Extract low-confidence, unverified candidate claims from one chunk."""

    settings = ClaimExtractionSettings(
        default_sensitivity=default_sensitivity,
        allowed_web_search=allowed_web_search,
    )
    claims: list[MemoryClaim] = []
    seen_normalized: set[str] = set()
    for offset, line in enumerate(chunk.text.splitlines()):
        claim_text = _clean_claim_line(line)
        if not claim_text:
            continue
        claim_type = classify_claim_type(claim_text)
        if claim_type is None:
            continue
        normalized = normalize_claim_text(claim_text)
        if normalized in seen_normalized:
            continue
        seen_normalized.add(normalized)
        source_line = (chunk.line_start or 1) + offset
        source_ref = SourceRef(
            source_type="local_document",
            source_id=chunk.document_id,
            document_name=chunk.document_name,
            document_path=chunk.document_path,
            chunk_id=chunk.chunk_id,
            page=chunk.page,
            line_start=source_line,
            line_end=source_line,
            quote=claim_text,
        )
        claims.append(
            MemoryClaim(
                claim=claim_text,
                claim_type=claim_type,
                source_refs=[source_ref],
                status="unverified",
                confidence="low",
                sensitivity=settings.default_sensitivity,
                allowed_web_search=settings.allowed_web_search,
                metadata={
                    "extraction_method": "deterministic_line_heuristic",
                    "source_document_id": chunk.document_id,
                    "source_chunk_id": chunk.chunk_id,
                    "source_line_start": source_line,
                    "source_line_end": source_line,
                },
            )
        )
    return claims


def classify_claim_type(text: str) -> str | None:
    """Classify a source line into a simple deterministic claim type."""

    if _matches_type(text, "prohibition"):
        return "prohibition"
    if _matches_type(text, "requirement"):
        return "requirement"
    if _matches_type(text, "recommendation"):
        return "recommendation"
    if _matches_type(text, "condition"):
        return "condition"
    if _matches_type(text, "instruction"):
        return "instruction"
    return None


def normalize_claim_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def _matches_type(text: str, claim_type: str) -> bool:
    for pattern in _TERM_PATTERNS[claim_type]:
        if pattern.search(text):
            return True
    return any(term in text for term in _NON_ASCII_TERMS[claim_type])


def _clean_claim_line(line: str) -> str:
    cleaned = line.strip()
    cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", cleaned)
    return cleaned.strip()
