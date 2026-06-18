"""Deterministic source URL classification and ranking."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

SOURCE_CATEGORIES = {
    "official_vendor",
    "official_release_notes",
    "official_github",
    "government_or_institution",
    "trusted_technical_blog",
    "wikipedia_background",
    "forum_or_reddit",
    "unknown",
    "blocked_low_quality",
}

CATEGORY_RANKS = {
    "official_vendor": 10,
    "official_release_notes": 20,
    "official_github": 30,
    "government_or_institution": 40,
    "trusted_technical_blog": 60,
    "wikipedia_background": 80,
    "forum_or_reddit": 90,
    "unknown": 100,
    "blocked_low_quality": 1000,
}

FINAL_AUTHORITY_CATEGORIES = {
    "official_vendor",
    "official_release_notes",
    "official_github",
    "government_or_institution",
}

DEFAULT_OFFICIAL_GITHUB_ORGS = {"microsoft", "openai", "anthropics", "anthropic", "chroma-core", "searxng"}
DEFAULT_TRUSTED_BLOG_DOMAINS = set()
BLOCKED_LOW_QUALITY_DOMAINS = {"quora.com", "answers.microsoft.com.malicious.example"}


@dataclass(frozen=True)
class SourceRankingResult:
    url: str
    domain: str
    category: str
    rank: int
    reason: str
    is_allowed_as_final_authority: bool


def rank_source(
    url: str,
    *,
    official_github_orgs: set[str] | None = None,
    trusted_blog_domains: set[str] | None = None,
) -> SourceRankingResult:
    """Classify and rank a URL with deterministic domain/path rules."""

    parsed = urlparse(url if "://" in str(url) else f"https://{url}")
    domain = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path.lower()
    official_orgs = {org.lower() for org in (official_github_orgs or DEFAULT_OFFICIAL_GITHUB_ORGS)}
    trusted_blogs = {item.lower().removeprefix("www.") for item in (trusted_blog_domains or DEFAULT_TRUSTED_BLOG_DOMAINS)}

    category = "unknown"
    reason = "Domain is not recognized by deterministic source policy."

    if not domain:
        category = "unknown"
        reason = "URL has no parseable domain."
    elif domain in BLOCKED_LOW_QUALITY_DOMAINS:
        category = "blocked_low_quality"
        reason = "Domain is explicitly blocked as low quality."
    elif domain in {"learn.microsoft.com", "support.microsoft.com", "docs.microsoft.com"}:
        category = "official_vendor"
        reason = "Microsoft documentation/support domain."
    elif domain == "microsoft.com" or domain.endswith(".microsoft.com"):
        if any(part in path for part in ("/support", "/docs", "/learn", "/download", "/windows")):
            category = "official_vendor"
            reason = "Official Microsoft domain with documentation/support path."
        elif any(part in path for part in ("/release", "/releases", "/changelog", "/whats-new", "/blog")):
            category = "official_release_notes"
            reason = "Official Microsoft domain with release/changelog path."
        else:
            category = "official_vendor"
            reason = "Official Microsoft domain."
    elif domain == "github.com":
        org = _first_path_segment(path)
        if org in official_orgs:
            category = "official_github"
            reason = f"GitHub repository under configured official org '{org}'."
        else:
            category = "unknown"
            reason = "GitHub URL is not under a configured official org."
    elif domain.endswith(".gov") or ".gov." in domain:
        category = "government_or_institution"
        reason = "Government domain."
    elif domain.endswith(".edu") or ".edu." in domain:
        category = "government_or_institution"
        reason = "Educational/institutional domain."
    elif domain == "wikipedia.org" or domain.endswith(".wikipedia.org"):
        category = "wikipedia_background"
        reason = "Wikipedia is background only."
    elif domain == "reddit.com" or domain.endswith(".reddit.com"):
        category = "forum_or_reddit"
        reason = "Reddit/forum source is clue-only."
    elif domain in {"stackoverflow.com", "serverfault.com", "superuser.com"} or domain.endswith(".stackexchange.com"):
        category = "forum_or_reddit"
        reason = "Stack Exchange source is community/forum evidence."
    elif domain in trusted_blogs:
        category = "trusted_technical_blog"
        reason = "Domain is configured as a trusted technical blog."

    return SourceRankingResult(
        url=str(url),
        domain=domain,
        category=category,
        rank=CATEGORY_RANKS[category],
        reason=reason,
        is_allowed_as_final_authority=category in FINAL_AUTHORITY_CATEGORIES,
    )


def _first_path_segment(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    return parts[0].lower() if parts else ""
