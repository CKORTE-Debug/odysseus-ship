"""Local CLI for manually testing the verified-memory pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from verified_memory.errors import VerifiedMemoryError
from verified_memory.storage import SQLiteVerifiedMemoryStore
from verified_memory.workflows import build_prompt, build_verified_context, extract_claims, ingest_document


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        payload = _run_command(args)
    except SystemExit as exc:
        return int(exc.code or 0)
    except (OSError, ValueError, VerifiedMemoryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m verified_memory.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="ingest a local .md/.txt document")
    ingest_parser.add_argument("path", help="local .md/.txt file path")
    ingest_parser.add_argument("--db", required=True, help="SQLite database path")
    ingest_parser.add_argument("--max-lines", type=int, default=40)
    ingest_parser.add_argument("--overlap-lines", type=int, default=5)
    ingest_parser.add_argument("--extract", action="store_true", help="run deterministic claim extraction after ingest")

    extract_parser = subparsers.add_parser("extract", help="extract candidate claims from stored chunks")
    extract_parser.add_argument("--db", required=True, help="SQLite database path")
    extract_parser.add_argument("--document-id")
    extract_parser.add_argument("--chunk-id", action="append", default=[])
    extract_parser.add_argument(
        "--default-sensitivity",
        default="private",
        choices=["public", "private", "client_confidential", "personal_sensitive"],
    )
    extract_parser.add_argument("--allow-web-search", default="false", choices=["false", "true"])

    context_parser = subparsers.add_parser("context", help="build a local verified context package")
    context_parser.add_argument("question")
    context_parser.add_argument("--db", required=True, help="SQLite database path")
    context_parser.add_argument("--max-chunks", type=int, default=5)
    context_parser.add_argument("--max-claims", type=int, default=5)
    context_parser.add_argument("--include-archived", action="store_true")

    prompt_parser = subparsers.add_parser("prompt", help="build a verified-memory prompt without generating an answer")
    prompt_parser.add_argument("question")
    prompt_parser.add_argument("--db", required=True, help="SQLite database path")
    prompt_parser.add_argument("--max-chunks", type=int, default=5)
    prompt_parser.add_argument("--max-claims", type=int, default=5)
    prompt_parser.add_argument("--include-archived", action="store_true")
    prompt_parser.add_argument("--format", choices=["json", "messages"], default="json")

    stats_parser = subparsers.add_parser("stats", help="show local verified-memory counts")
    stats_parser.add_argument("--db", required=True, help="SQLite database path")

    return parser


def _run_command(args: argparse.Namespace) -> dict[str, Any]:
    store = SQLiteVerifiedMemoryStore(args.db)
    if args.command == "ingest":
        return _cmd_ingest(args, store)
    if args.command == "extract":
        return _cmd_extract(args, store)
    if args.command == "context":
        return _cmd_context(args, store)
    if args.command == "prompt":
        return _cmd_prompt(args, store)
    if args.command == "stats":
        return _cmd_stats(store)
    raise ValueError(f"unsupported command: {args.command}")


def _cmd_ingest(args: argparse.Namespace, store: SQLiteVerifiedMemoryStore) -> dict[str, Any]:
    result = ingest_document(
        Path(args.path),
        store,
        max_lines=args.max_lines,
        overlap_lines=args.overlap_lines,
    )
    payload: dict[str, Any] = {
        "command": "ingest",
        "document_id": result.document_id,
        "document_name": result.document_name,
        "chunks_created": result.chunks_created,
        "chunk_ids": result.chunk_ids,
        "warnings": result.warnings,
    }
    if args.extract:
        extraction = extract_claims(store, document_id=result.document_id)
        payload["extraction"] = {
            "claims_created": extraction.claims_created,
            "claim_ids": extraction.claim_ids,
            "chunks_processed": extraction.chunks_processed,
            "warnings": extraction.warnings,
        }
    return payload


def _cmd_extract(args: argparse.Namespace, store: SQLiteVerifiedMemoryStore) -> dict[str, Any]:
    chunk_ids = _parse_chunk_ids(args.chunk_id)
    result = extract_claims(
        store,
        document_id=args.document_id,
        chunk_ids=chunk_ids or None,
        default_sensitivity=args.default_sensitivity,
        allowed_web_search=args.allow_web_search == "true",
    )
    return {
        "command": "extract",
        "claims_created": result.claims_created,
        "claim_ids": result.claim_ids,
        "chunks_processed": result.chunks_processed,
        "warnings": result.warnings,
    }


def _cmd_context(args: argparse.Namespace, store: SQLiteVerifiedMemoryStore) -> dict[str, Any]:
    package = build_verified_context(
        args.question,
        store,
        max_chunks=args.max_chunks,
        max_claims=args.max_claims,
        include_archived=args.include_archived,
    )
    payload = package.to_dict()
    payload["command"] = "context"
    return payload


def _cmd_prompt(args: argparse.Namespace, store: SQLiteVerifiedMemoryStore) -> dict[str, Any]:
    prompt = build_prompt(
        args.question,
        store,
        max_chunks=args.max_chunks,
        max_claims=args.max_claims,
        include_archived=args.include_archived,
    )
    if args.format == "messages":
        return {"command": "prompt", "messages": prompt.messages, "warnings": prompt.warnings}
    payload = prompt.to_dict()
    payload["command"] = "prompt"
    return payload


def _cmd_stats(store: SQLiteVerifiedMemoryStore) -> dict[str, Any]:
    return {
        "command": "stats",
        "documents": store.count_documents(),
        "chunks": store.count_document_chunks(),
        "claims": store.count_memory_claims(),
        "conflicts": store.count_conflict_records(),
        "verification_runs": store.count_verification_runs(),
    }


def _parse_chunk_ids(values: list[str]) -> list[str]:
    chunk_ids: list[str] = []
    for value in values:
        chunk_ids.extend(part.strip() for part in value.split(",") if part.strip())
    return chunk_ids


if __name__ == "__main__":
    raise SystemExit(main())
