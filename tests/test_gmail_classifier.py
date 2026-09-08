from __future__ import annotations

from gmail.classifier import GmailMessage, classify_message


def test_gmail_classifier_obvious_types() -> None:
    assert classify_message(GmailMessage(subject="Thank you for applying"))["type"] == "application_receipt"
    assert classify_message(GmailMessage(subject="Schedule a call for interview"))["type"] == "interview_invite"
    assert classify_message(GmailMessage(subject="Coding test"))["type"] == "assessment"
    assert classify_message(GmailMessage(subject="Unfortunately your application"))["type"] == "rejection"
    assert classify_message(GmailMessage(subject="Offer and compensation"))["type"] == "offer"

