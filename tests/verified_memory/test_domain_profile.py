import pytest

from verified_memory.errors import InvalidRecordError
from verified_memory.policies import list_domain_profiles, load_domain_profile


def test_load_general_profile():
    profile = load_domain_profile("general")

    assert profile.name == "general"
    assert profile.web_search_allowed is True
    assert profile.stale_after_days_for("software_behavior") == 60


def test_load_it_software_profile():
    profile = load_domain_profile("it_software")

    assert profile.name == "it_software"
    assert "official_vendor" in profile.source_priority
    assert profile.stale_after_days_for("internal_sop") == 180


def test_unknown_profile_falls_back_to_general_by_default():
    profile = load_domain_profile("unknown_profile")

    assert profile.name == "general"


def test_unknown_profile_can_raise_documented_error():
    with pytest.raises(InvalidRecordError, match="Unknown domain profile"):
        load_domain_profile("unknown_profile", fallback_to_general=False)


def test_personal_preference_has_no_stale_expiry():
    profile = load_domain_profile("personal_knowledge")

    assert profile.stale_after_days_for("personal_preference") is None
    assert profile.web_search_allowed is False


def test_microsoft_365_has_shorter_stale_period_than_general_software_behavior():
    general = load_domain_profile("general")
    microsoft_365 = load_domain_profile("microsoft_365")

    assert microsoft_365.stale_after_days_for("microsoft_365") < general.stale_after_days_for("software_behavior")


def test_medical_and_legal_profiles_require_manual_approval():
    assert load_domain_profile("medical").manual_approval_required is True
    assert load_domain_profile("legal").manual_approval_required is True


def test_expected_profiles_are_available():
    names = list_domain_profiles()

    assert "general" in names
    assert "academic" in names
    assert "gaming" in names
