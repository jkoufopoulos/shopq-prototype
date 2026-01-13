from mailq.gmail.gmail_link_builder import GmailLinkBuilder


def test_thread_link_builder():
    assert (
        GmailLinkBuilder.thread_link("thread-abc")
        == "https://mail.google.com/mail/u/0/#inbox/thread-abc"
    )


def test_message_link_builder():
    assert (
        GmailLinkBuilder.message_link("msg-123")
        == "https://mail.google.com/mail/u/0/#inbox/msg-123"
    )


# ============================================================================
# Client Label Link Tests
# ============================================================================


def test_client_label_link_known_labels():
    """Test Gmail deep links for all known client labels."""
    assert (
        GmailLinkBuilder.client_label_link("action-required")
        == "https://mail.google.com/mail/u/0/#label/MailQ%2FAction-Required"
    )
    assert (
        GmailLinkBuilder.client_label_link("receipts")
        == "https://mail.google.com/mail/u/0/#label/MailQ%2FReceipts"
    )
    assert (
        GmailLinkBuilder.client_label_link("messages")
        == "https://mail.google.com/mail/u/0/#label/MailQ%2FMessages"
    )
    assert (
        GmailLinkBuilder.client_label_link("everything-else")
        == "https://mail.google.com/mail/u/0/#label/MailQ%2FEverything-Else"
    )


def test_client_label_link_unknown_label():
    """Test fallback for unknown client label."""
    # Should fallback to generic MailQ/{label} format
    result = GmailLinkBuilder.client_label_link("custom-label")
    assert "MailQ%2Fcustom-label" in result
    assert result.startswith("https://mail.google.com/mail/u/0/#label/")


def test_client_label_link_url_encoding():
    """Test that forward slash in label name is URL-encoded."""
    # All our labels have MailQ/{label} format, slash should become %2F
    result = GmailLinkBuilder.client_label_link("receipts")
    assert "%2F" in result  # Forward slash is URL-encoded


def test_build_client_label_links():
    """Test that all 4 standard labels are included."""
    links = GmailLinkBuilder.build_client_label_links()

    assert len(links) == 4
    assert "action-required" in links
    assert "receipts" in links
    assert "messages" in links
    assert "everything-else" in links

    # All should be valid URLs
    for _label, url in links.items():
        assert url.startswith("https://mail.google.com/mail/u/0/#label/")
        assert "MailQ%2F" in url  # Forward slash should be URL-encoded


# ============================================================================
# Label Summary Prose Tests
# ============================================================================


def test_render_label_summary_prose_all_labels():
    """Test prose generation with all label types."""
    counts = {
        "action-required": 2,
        "receipts": 8,
        "messages": 3,
        "everything-else": 10,
    }
    result = GmailLinkBuilder.render_label_summary_prose(counts)

    # Should include all non-action-required labels (action-required shown in digest body)
    assert "8 receipts" in result
    assert "3 messages" in result
    assert "10 routine notifications" in result
    assert result.startswith("The rest is")
    # Verify Gmail links present
    assert 'href="https://mail.google.com/mail/u/0/#label/MailQ%2FReceipts"' in result


def test_render_label_summary_prose_single_label():
    """Test prose with only one label."""
    counts = {"receipts": 5, "messages": 0, "everything-else": 0}
    result = GmailLinkBuilder.render_label_summary_prose(counts)

    assert (
        result
        == 'The rest is <a href="https://mail.google.com/mail/u/0/#label/MailQ%2FReceipts">5 receipts</a>.'
    )


def test_render_label_summary_prose_two_labels():
    """Test prose with two labels (uses 'and' without Oxford comma)."""
    counts = {"receipts": 5, "messages": 3, "everything-else": 0}
    result = GmailLinkBuilder.render_label_summary_prose(counts)

    assert "5 receipts</a> and <a" in result
    assert "3 messages" in result


def test_render_label_summary_prose_three_labels():
    """Test prose with three labels (uses Oxford comma)."""
    counts = {"receipts": 5, "messages": 3, "everything-else": 10}
    result = GmailLinkBuilder.render_label_summary_prose(counts)

    # Oxford comma: "a, b, and c"
    assert "5 receipts</a>, <a" in result
    assert "3 messages</a>, and <a" in result
    assert "10 routine notifications" in result


def test_render_label_summary_prose_empty_counts():
    """Test that empty counts return empty string."""
    assert GmailLinkBuilder.render_label_summary_prose({}) == ""
    assert GmailLinkBuilder.render_label_summary_prose(None) == ""


def test_render_label_summary_prose_zero_counts():
    """Test that all-zero counts return empty string."""
    counts = {"receipts": 0, "messages": 0, "everything-else": 0}
    assert GmailLinkBuilder.render_label_summary_prose(counts) == ""


def test_render_label_summary_prose_html_escaping():
    """Test that links are HTML-escaped (XSS prevention)."""
    counts = {"receipts": 1}
    result = GmailLinkBuilder.render_label_summary_prose(counts)

    # The href attribute should be properly quoted
    assert 'href="' in result
    # No unescaped quotes that could break out of attribute
    assert 'href="https://' in result
