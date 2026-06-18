"""Deterministic prompt assembly for verified-memory context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from verified_memory.models._helpers import datetime_to_json
from verified_memory.retrieval import VerifiedContextPackage


SYSTEM_MESSAGE = """You are answering using verified-memory context.
Use only the provided evidence.
Do not invent citations.
Only cite source references that appear in the context.
Fresh verified claims with usable_evidence=true may be treated as confirmed evidence.
Stale claims are leads only, not confirmed facts.
Unverified claims are leads only, not confirmed facts.
Contradicted claims must not be used as evidence except to explain a conflict.
Archived claims must not be used as evidence.
Local document chunks may be used as source text, but do not infer beyond what the chunk says.
If the evidence is insufficient, say so.
If the evidence conflicts, say there is a conflict and identify the conflicting source refs.
Do not use private information for online search.
Do not claim that online verification was performed unless verification evidence is included.
Provide concise reasoning in the final answer, but do not reveal hidden scratchpad or chain-of-thought."""


@dataclass(frozen=True)
class VerifiedMemoryPrompt:
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


def build_verified_memory_prompt(package: VerifiedContextPackage) -> VerifiedMemoryPrompt:
    """Build a local, deterministic prompt object without LLM or network calls."""

    usable_claims: list[dict[str, Any]] = []
    non_confirmed_claims: list[dict[str, Any]] = []
    for claim in package.retrieved_claims:
        claim_block = _claim_block(claim)
        if getattr(claim, "usable_evidence", False):
            usable_claims.append(claim_block)
        else:
            claim_block["reason_not_usable"] = _reason_not_usable(claim)
            claim_block["should_verify"] = bool(getattr(claim, "should_verify", False))
            non_confirmed_claims.append(claim_block)

    chunk_blocks = [_chunk_block(chunk) for chunk in package.retrieved_chunks]
    citation_refs = _dedupe_refs(
        [ref for claim in usable_claims + non_confirmed_claims for ref in claim["source_refs"]]
        + [chunk["source_ref"] for chunk in chunk_blocks]
    )
    evidence_blocks = {
        "usable_verified_claims": usable_claims,
        "local_evidence_chunks": chunk_blocks,
        "not_confirmed_claims": non_confirmed_claims,
        "citation_source_refs": citation_refs,
    }
    warnings = list(package.warnings)
    metadata = {
        "prompt_created_at": datetime_to_json(package.created_at),
        "answer_generated": False,
        "online_verification_performed": False,
        "usable_claim_count": len(usable_claims),
        "local_chunk_count": len(chunk_blocks),
        "not_confirmed_claim_count": len(non_confirmed_claims),
        **dict(package.metadata),
    }
    return VerifiedMemoryPrompt(
        system_message=SYSTEM_MESSAGE,
        user_message=_user_message(package.question, evidence_blocks, warnings),
        evidence_blocks=evidence_blocks,
        warnings=warnings,
        metadata=metadata,
    )


def _claim_block(claim: Any) -> dict[str, Any]:
    return {
        "claim_id": claim.claim_id,
        "claim": claim.claim,
        "claim_type": claim.claim_type,
        "confidence": claim.confidence,
        "status": claim.status,
        "staleness_status": claim.staleness_status,
        "source_refs": [_source_ref_label(ref) for ref in claim.source_refs],
    }


def _chunk_block(chunk: Any) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "document_name": chunk.document_name,
        "line_start": chunk.line_start,
        "line_end": chunk.line_end,
        "source_ref": _source_ref_label(chunk.source_ref),
        "text": chunk.text,
    }


def _source_ref_label(ref: Any) -> str:
    if getattr(ref, "chunk_id", None):
        return str(ref.chunk_id)
    if getattr(ref, "url", None):
        return str(ref.url)
    if getattr(ref, "source_id", None):
        return str(ref.source_id)
    return str(ref.id)


def _reason_not_usable(claim: Any) -> str:
    status = getattr(claim, "status", "")
    staleness = getattr(claim, "staleness_status", "")
    if status == "archived" or staleness == "archived":
        return "archived claims must not be used as evidence"
    if status == "contradicted" or staleness == "contradicted":
        return "contradicted claims are not usable evidence except to explain a conflict"
    if status == "unverified" or staleness == "unverified":
        return "unverified claims are leads only, not confirmed facts"
    if status == "stale" or staleness == "stale":
        return "stale claims are leads only, not confirmed facts"
    if not getattr(claim, "source_refs", []):
        return "claim has no source references"
    return "claim is not marked usable_evidence=true"


def _user_message(question: str, evidence_blocks: dict[str, list[dict[str, Any]]], warnings: list[str]) -> str:
    lines = [
        "Original question:",
        question,
        "",
        "Usable verified claims:",
        _format_blocks(evidence_blocks["usable_verified_claims"]),
        "",
        "Local evidence chunks:",
        _format_blocks(evidence_blocks["local_evidence_chunks"]),
        "",
        "Unverified/stale/contradicted claims (not confirmed):",
        _format_blocks(evidence_blocks["not_confirmed_claims"]),
        "",
        "Warnings:",
        _format_blocks(warnings),
        "",
        "Citation/source reference list:",
        _format_blocks(evidence_blocks["citation_source_refs"]),
    ]
    return "\n".join(lines)


def _format_blocks(value: Any) -> str:
    if not value:
        return "- none"
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return "\n".join(f"- {item}" for item in value)
    lines: list[str] = []
    for item in value:
        lines.append(f"- {item}")
    return "\n".join(lines)


def _dedupe_refs(refs: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            result.append(ref)
    return result
