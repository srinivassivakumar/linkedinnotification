"""Parse LinkedIn "accepted your invitation" notification emails.

Ported from the linkedinnotification project. Pure and deterministic: given the
email HTML and the ``From`` display name, return the new connection's name,
headline, location and profile URL. No network, no automation.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

# The account owner's own profile slug fragment, to avoid picking "self" links.
OWN_PROFILE_FRAGMENT = "srinivas-s-"

_KNOWN_LOCATIONS = {
    "india",
    "united states",
    "united kingdom",
    "canada",
    "australia",
    "germany",
    "singapore",
}


def clean_name(name: str | None) -> str | None:
    if not name:
        return None
    name = re.sub(r"\s+via LinkedIn.*$", "", name, flags=re.IGNORECASE)
    name = name.replace("↗️", "").strip()
    return name.strip('"').strip() or None


def normalize_linkedin_profile_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if "/comm/in/" not in parsed.path:
        return None
    slug = parsed.path.split("/comm/in/", 1)[1].strip("/")
    if not slug:
        return None
    return f"https://www.linkedin.com/in/{unquote(slug)}"


def normalize_message_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if "/comm/messaging/compose/" not in parsed.path:
        return None
    conn_id = parse_qs(parsed.query).get("connId", [None])[0]
    if not conn_id:
        return None
    return f"https://www.linkedin.com/messaging/compose/?connId={unquote(conn_id)}"


def parse_acceptance_email(html: str, sender_name: str | None) -> dict[str, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    text_lines = [
        line.strip()
        for line in soup.get_text("\n", strip=True).splitlines()
        if line.strip()
    ]

    name = clean_name(sender_name)
    headline: str | None = None
    location: str | None = None

    if name:
        for i, line in enumerate(text_lines):
            if line == name:
                for candidate in text_lines[i + 1 : i + 4]:
                    if candidate in {"Message", f"Reach out to {name}"}:
                        continue
                    if candidate.lower() in _KNOWN_LOCATIONS:
                        location = candidate
                        continue
                    if candidate != "." and headline is None:
                        headline = candidate
                break

    profile_url: str | None = None
    message_url: str | None = None
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if not profile_url:
            candidate = normalize_linkedin_profile_url(href)
            if candidate and OWN_PROFILE_FRAGMENT not in candidate:
                profile_url = candidate
        if not message_url:
            candidate = normalize_message_url(href)
            if candidate:
                message_url = candidate
        if profile_url and message_url:
            break

    return {
        "name": name,
        "headline": headline,
        "location": location,
        "linkedin_profile_url": profile_url,
        "linkedin_message_url": message_url,
    }
