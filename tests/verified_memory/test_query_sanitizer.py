from verified_memory.verification import sanitize_query


def test_allowed_vendor_query_passes():
    result = sanitize_query("Microsoft Intune Autopilot OOBE Wi-Fi driver missing")

    assert result.action == "allow"
    assert result.sanitized_query == "Microsoft Intune Autopilot OOBE Wi-Fi driver missing"
    assert "Microsoft" in result.allowed_terms
    assert "Intune" in result.allowed_terms


def test_email_query_blocks():
    result = sanitize_query("user@example.com Teams folder access issue")

    assert result.action == "block"
    assert result.sanitized_query is None
    assert "email_address" in result.reasons
    assert "user@example.com" in result.blocked_terms


def test_ipv4_query_blocks():
    result = sanitize_query("192.168.10.22 Intune enrollment error")

    assert result.action == "block"
    assert "ipv4_address" in result.reasons


def test_windows_path_query_blocks():
    result = sanitize_query(r"C:\Users\Chris\Documents\ClientA\SOP.docx Teams issue")

    assert result.action == "block"
    assert "windows_path" in result.reasons


def test_japanese_denylist_terms_are_sanitized_when_remaining_query_is_meaningful():
    result = sanitize_query(
        "日本メダック 尾中さん Teams hidden folder",
        denylist=["日本メダック", "尾中"],
    )

    assert result.action == "sanitize"
    assert result.sanitized_query == "さん Teams hidden folder"
    assert "日本メダック" in result.blocked_terms
    assert "尾中" in result.blocked_terms


def test_client_name_denylist_is_sanitized_when_remaining_query_is_meaningful():
    result = sanitize_query(
        "ClientName employee Teams folder direct link not shown",
        denylist=["ClientName"],
    )

    assert result.action == "sanitize"
    assert result.sanitized_query == "employee Teams folder direct link not shown"
    assert "denylist_term" in result.reasons


def test_allowed_teams_query_passes():
    result = sanitize_query("Microsoft Teams folder visible by direct link not shown in Files tab")

    assert result.action == "allow"
    assert result.sanitized_query == "Microsoft Teams folder visible by direct link not shown in Files tab"


def test_ticket_id_blocks():
    result = sanitize_query("INC123456 Autopilot failure")

    assert result.action == "block"
    assert "ticket_id" in result.reasons


def test_internal_domain_blocks():
    result = sanitize_query("client.local SharePoint issue")

    assert result.action == "block"
    assert "internal_domain" in result.reasons
