"""Deterministic prompt assembly for verified-memory context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from verified_memory.models._helpers import datetime_to_json, utc_now
from verified_memory.retrieval import VerifiedContextPackage


SYSTEM_RULES = [
    "You are answering using verified-memory context.",
    "Use only the provided evidence.",
    "Do not invent citations.",
    "Only cite source references that appear in the context.",
    "Fresh verified claims with usable_evidence=true may be treated as confirmed evidence.",
    "Stale claims are leads only, not confirmed facts.",
    "Unverified claims are leads only, not confirmed facts.",
    "Contradicted claims must not be used as evidence except to explain a conflict.",
    "Archived claims must not be used as evidence.",
    "Local document chunks may be used as source text, but do not infer beyond what the chunk says.",
    "If the evidence is insufficient, say so.",
    "If the evidence conflicts, say there is a conflict and identify the conflicting source refs.",
    "Do not use private information for online search.",
    "Do not claim that online verification was performed unless verification evidence is included.",
]


@dataclass(frozen=True)
class VerifiedMemoryPrompt:
    """Structured prompt object for later LLM answer generation."""

    system_message: str
    user_message: str
    evidence_blocks: dict[str, list[dict[str, Any]]]
    warnings: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def messages(self) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.system_message},
            {"role": "user", "content": self.user_message},
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_message": self.system_message,
            "user_message": self.user_message,
            "messages": self.messages,
            "evidence_blocks": self.evidence_blocks,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


def build_verified_memory_prompt(context: VerifiedContextPackage) -> VerifiedMemoryPrompt:
    """Build deterministic prompt messages from a verified context package.

    This function only prepares prompt text and structured metadata. It does not
    call an LLM, generate an answer, search the web, or verify evidence online.
    """

    usable_claims = [_claim_block(claim) for claim in context.retrieved_claims if getattr(claim, "usable_evidence", False)]
    non_confirmed_claims = [
        _non_confirmed_claim_block(claim)
        for claim in context.retrieved_claims
        if not getattr(claim, "usable_evidence", False)
    ]
    chunk_blocks = [_chunk_block(chunk) for chunk in context.retrieved_chunks]
    citation_refs = _citation_refs(usable_claims, non_confirmed_claims, chunk_blocks)

    evidence_blocks = {
        "usable_verified_claims": usable_claims,
        "local_evidence_chunks": chunk_blocks,
        "not_confirmed_claims": non_confirmed_claims,
        "citation_source_refs": citation_refs,
    }
    system_message = "\n".join(f"- {rule}" for rule in SYSTEM_RULES)
    user_message = _build_user_message(context.question, evidence_blocks, context.warnings)
    return VerifiedMemoryPrompt(
        system_message=system_message,
        user_message=user_message,
        evidence_blocks=evidence_blocks,
        warnings=list(context.warnings),
        metadata={
            "prompt_type": "verified_memory_context",
            "answer_generated": False,
            "llm_called": False,
            "online_verification_performed": False,
            "created_at": datetime_to_json(utc_now()),
            "context_created_at": datetime_to_json(context.created_at),
            "context_metadata": dict(context.metadata),
            "usable_claim_count": len(usable_claims),
            "local_chunk_count": len(chunk_blocks),
            "not_confirmed_claim_count": len(non_confirmed_claims),
        },
    )


def _build_user_message(question: str, evidence_blocks: dict[str, list[dict[str, Any]]], warnings: list[str]) -> str:
    sections = [
        "Original question:",
        question,
        "",
        "Usable verified claims:",
        _format_blocks(evidence_blocks["usable_verified_claims"]),
        "",
        "Local evidence chunks:",
        _format_blocks(evidence_blocks["local_evidence_chunks"]),
        "",
        "Not confirmed claims (do not treat as confirmed facts):",
        _format_blocks(evidence_blocks["not_confirmed_claims"]),
        "",
        "Warnings:",
        _format_list(warnings),
        "",
        "Citation/source reference list:",
        _format_blocks(evidence_blocks["citation_source_refs"]),
    ]
    return "\n".join(sections)


def _claim_block(claim: Any) -> dict[str, Any]:
    return {
        "claim_id": claim.claim_id,
        "claim": claim.claim,
        "claim_type": claim.claim_type,
        "confidence": claim.confidence,
        "status": claim.status,
        "staleness_status": claim.staleness_status,
        "source_refs": [ref.to_dict() for ref in claim.source_refs],
        "usable_evidence": True,
    }


def _non_confirmed_claim_block(claim: Any) -> dict[str, Any]:
    return {
        "claim_id": claim.claim_id,
        "claim": claim.claim,
        "status": claim.status,
        "staleness_status": claim.staleness_status,
        "reason_not_usable": _reason_not_usable(claim),
        "should_verify": claim.should_verify,
        "source_refs": [ref.to_dict() for ref in claim.source_refs],
        "usable_evidence": False,
    }


def _chunk_block(chunk: Any) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "document_name": chunk.document_name,
        "line_start": chunk.line_start,
        "line_end": chunk.line_end,
        "source_ref": chunk.source_ref.to_dict(),
        "text": chunk.text,
    }


def _reason_not_usable(claim: Any) -> str:
    if not claim.source_refs:
        return "missing_source_refs"
    if claim.status == "contradicted" or claim.staleness_status == "contradicted":
        return "contradicted_claim"
    if claim.status == "archived" or claim.staleness_status == "archived":
        return "archived_claim"
    if claim.staleness_status == "stale":
        return "stale_claim"
    if claim.status == "unverified" or claim.staleness_status == "unverified":
        return "unverified_claim"
    return "not_marked_usable_evidence"


def _citation_refs(
    usable_claims: list[dict[str, Any]],
    non_confirmed_claims: list[dict[str, Any]],
    chunk_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for claim in [*usable_claims, *non_confirmed_claims]:
        for ref in claim["source_refs"]:
            key = _source_ref_key(ref)
            if key not in seen:
                seen.add(key)
                refs.append(ref)
    for chunk in chunk_blocks:
        ref = chunk["source_ref"]
        key = _source_ref_key(ref)
        if key not in seen:
            seen.add(key)
            refs.append(ref)
    return refs


def _source_ref_key(ref: dict[str, Any]) -> str:
    return "|".join(
        str(ref.get(part) or "")
        for part in ("source_type", "source_id", "document_path", "chunk_id", "line_start", "line_end", "url")
    )


def _format_blocks(blocks: list[dict[str, Any]]) -> str:
    if not blocks:
        return "- none"
    lines = []
    for index, block in enumerate(blocks, start=1):
        lines.append(f"[{index}] {block}")
    return "\n".join(lines)


def _format_list(items: list[str]) -> str:
    if not items:
        return "- none"
    return "\n".join(f"- {item}" for item in items)
