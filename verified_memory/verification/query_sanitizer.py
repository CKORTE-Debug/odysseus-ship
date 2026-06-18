"""Deterministic privacy gate for future verified-memory web queries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

DEFAULT_ALLOWED_TERMS = {
    "Microsoft",
    "Windows",
    "Intune",
    "Entra",
    "Teams",
    "SharePoint",
    "Surface",
    "Adobe",
    "Google",
    "Apple",
    "Cisco",
    "Fortinet",
    "Zoom",
    "GitHub",
    "OpenAI",
    "Anthropic",
    "Claude",
    "ChatGPT",
    "Grok",
    "Ollama",
    "ChromaDB",
    "SearXNG",
}

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d .()\-]{7,}\d)(?!\w)")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6_RE = re.compile(r"\b(?:[0-9A-F]{1,4}:){2,}[0-9A-F]{1,4}\b", re.IGNORECASE)
_TICKET_RE = re.compile(r"\b(?:INC|REQ|CHG)\d{4,}\b", re.IGNORECASE)
_WINDOWS_PATH_RE = re.compile(r"\b[A-Z]:\\[^\s]+", re.IGNORECASE)
_UNIX_PATH_RE = re.compile(r"(?<!\w)/(?:Users|home|etc|var|opt|srv|private|tmp|Volumes)/[^\s]+")
_INTERNAL_DOMAIN_RE = re.compile(r"\b[A-Z0-9-]+(?:\.[A-Z0-9-]+)*\.(?:local|lan|internal|corp|intranet)\b", re.IGNORECASE)
_HOSTNAME_RE = re.compile(r"\b(?:[a-z]{2,}-)?(?:srv|server|host|dc|db|app|web|nas|pc|laptop|desktop|wkstn)[a-z0-9-]*\d*(?:\.[a-z0-9-]+)*\b", re.IGNORECASE)
_FILENAME_RE = re.compile(r"\b[^\s]+\.(?:docx?|xlsx?|pptx?|pdf|txt|md|csv|log|json|yaml|yml|ini|conf)\b", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class QuerySanitizationResult:
    action: str
    original_query: str
    sanitized_query: str | None
    reasons: list[str] = field(default_factory=list)
    blocked_terms: list[str] = field(default_factory=list)
    allowed_terms: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.action in {"allow", "sanitize"}


def sanitize_query(
    query: str,
    *,
    denylist: Iterable[str] | None = None,
    private_filenames: Iterable[str] | None = None,
    allowlist: Iterable[str] | None = None,
) -> QuerySanitizationResult:
    """Allow, sanitize, or block a future web query before any network access."""

    original_query = str(query or "")
    normalized_query = _normalize_spaces(original_query)
    allowed_terms = _find_allowed_terms(normalized_query, allowlist)
    reasons: list[str] = []
    blocked_terms: list[str] = []
    sanitized_query = normalized_query
    hard_block = False

    for reason, pattern in (
        ("email_address", _EMAIL_RE),
        ("phone_number", _PHONE_RE),
        ("ipv4_address", _IPV4_RE),
        ("ipv6_address", _IPV6_RE),
        ("ticket_id", _TICKET_RE),
        ("windows_path", _WINDOWS_PATH_RE),
        ("unix_path", _UNIX_PATH_RE),
        ("internal_domain", _INTERNAL_DOMAIN_RE),
        ("internal_hostname", _HOSTNAME_RE),
    ):
        matches = _matches(pattern, normalized_query)
        if matches:
            hard_block = True
            reasons.append(reason)
            blocked_terms.extend(matches)

    private_filename_terms = _unique_terms(private_filenames or [])
    filename_matches = _matches(_FILENAME_RE, normalized_query)
    for filename in private_filename_terms:
        if _contains_term(normalized_query, filename):
            filename_matches.append(filename)
    if filename_matches:
        hard_block = True
        reasons.append("private_filename")
        blocked_terms.extend(filename_matches)

    deny_terms = _unique_terms(denylist or [])
    removed_terms: list[str] = []
    for term in deny_terms:
        if _contains_term(sanitized_query, term):
            sanitized_query = _remove_term(sanitized_query, term)
            removed_terms.append(term)

    if removed_terms:
        reasons.append("denylist_term")
        blocked_terms.extend(removed_terms)

    blocked_terms = _dedupe_preserve_order(blocked_terms)
    reasons = _dedupe_preserve_order(reasons)
    sanitized_query = _normalize_spaces(sanitized_query)

    if hard_block:
        return QuerySanitizationResult(
            action="block",
            original_query=original_query,
            sanitized_query=None,
            reasons=reasons,
            blocked_terms=blocked_terms,
            allowed_terms=allowed_terms,
        )

    if removed_terms:
        if _is_meaningful_query(sanitized_query):
            return QuerySanitizationResult(
                action="sanitize",
                original_query=original_query,
                sanitized_query=sanitized_query,
                reasons=reasons,
                blocked_terms=blocked_terms,
                allowed_terms=allowed_terms,
            )
        return QuerySanitizationResult(
            action="block",
            original_query=original_query,
            sanitized_query=None,
            reasons=_dedupe_preserve_order(reasons + ["sanitized_query_not_meaningful"]),
            blocked_terms=blocked_terms,
            allowed_terms=allowed_terms,
        )

    return QuerySanitizationResult(
        action="allow",
        original_query=original_query,
        sanitized_query=normalized_query,
        reasons=[],
        blocked_terms=[],
        allowed_terms=allowed_terms,
    )


def _matches(pattern: re.Pattern[str], text: str) -> list[str]:
    return [match.group(0) for match in pattern.finditer(text)]


def _normalize_spaces(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _unique_terms(terms: Iterable[str]) -> list[str]:
    out = []
    for term in terms:
        cleaned = str(term or "").strip()
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def _contains_term(text: str, term: str) -> bool:
    return re.search(_term_pattern(term), text, flags=re.IGNORECASE) is not None


def _remove_term(text: str, term: str) -> str:
    return re.sub(_term_pattern(term), " ", text, flags=re.IGNORECASE)


def _term_pattern(term: str) -> str:
    escaped = re.escape(term)
    if re.fullmatch(r"[A-Za-z0-9_ .'-]+", term):
        return rf"(?<!\w){escaped}(?!\w)"
    return escaped


def _find_allowed_terms(query: str, allowlist: Iterable[str] | None) -> list[str]:
    terms = _unique_terms(allowlist or DEFAULT_ALLOWED_TERMS)
    return [term for term in terms if _contains_term(query, term)]


def _is_meaningful_query(query: str) -> bool:
    tokens = [token for token in re.split(r"\s+", query) if len(token.strip()) >= 2]
    return len(tokens) >= 3


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
