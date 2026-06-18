from verified_memory.verification import rank_source


def test_learn_microsoft_ranked_official_vendor():
    result = rank_source("https://learn.microsoft.com/en-us/windows/")

    assert result.category == "official_vendor"
    assert result.is_allowed_as_final_authority is True


def test_support_microsoft_ranked_official_vendor():
    result = rank_source("https://support.microsoft.com/help")

    assert result.category == "official_vendor"


def test_github_microsoft_ranked_official_github_if_configured():
    result = rank_source("https://github.com/microsoft/winget-cli")

    assert result.category == "official_github"
    assert result.is_allowed_as_final_authority is True


def test_wikipedia_ranked_background():
    result = rank_source("https://en.wikipedia.org/wiki/Microsoft_Intune")

    assert result.category == "wikipedia_background"
    assert result.is_allowed_as_final_authority is False


def test_reddit_ranked_forum_or_reddit():
    result = rank_source("https://www.reddit.com/r/sysadmin/comments/example")

    assert result.category == "forum_or_reddit"
    assert result.is_allowed_as_final_authority is False


def test_unknown_blog_ranked_unknown_by_default():
    result = rank_source("https://random-seo-blog.example/intune-tips")

    assert result.category == "unknown"
    assert result.is_allowed_as_final_authority is False


def test_configured_blog_can_be_trusted_technical_blog():
    result = rank_source(
        "https://technical.example/intune-tips",
        trusted_blog_domains={"technical.example"},
    )

    assert result.category == "trusted_technical_blog"
    assert result.is_allowed_as_final_authority is False


def test_gov_ranked_government_or_institution():
    result = rank_source("https://www.nist.gov/publications/example")

    assert result.category == "government_or_institution"
    assert result.is_allowed_as_final_authority is True
