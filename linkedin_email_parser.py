import re
from urllib.parse import urlparse, parse_qs, unquote

from bs4 import BeautifulSoup


def clean_name(name: str | None):
    if not name:
        return None

    name = re.sub(r"\s+via LinkedIn.*$", "", name, flags=re.IGNORECASE)
    name = name.replace("↗️", "").strip()
    name = name.strip('"').strip()

    return name


def normalize_linkedin_profile_url(url: str | None):
    if not url:
        return None

    parsed = urlparse(url)

    if "/comm/in/" not in parsed.path:
        return None

    slug = parsed.path.split("/comm/in/", 1)[1].strip("/")

    if not slug:
        return None

    slug = unquote(slug)

    return f"https://www.linkedin.com/in/{slug}"


def normalize_message_url(url: str | None):
    if not url:
        return None

    parsed = urlparse(url)

    if "/comm/messaging/compose/" not in parsed.path:
        return None

    query = parse_qs(parsed.query)

    conn_id = query.get("connId", [None])[0]

    if not conn_id:
        return None

    conn_id = unquote(conn_id)

    return (
        "https://www.linkedin.com/messaging/compose/"
        f"?connId={conn_id}"
    )


def parse_acceptance_email(html: str, sender_name: str | None):
    soup = BeautifulSoup(html, "html.parser")

    text_lines = [
        line.strip()
        for line in soup.get_text("\n", strip=True).splitlines()
        if line.strip()
    ]

    name = clean_name(sender_name)

    headline = None
    location = None

    if name:
        for i, line in enumerate(text_lines):
            if line == name:
                next_lines = text_lines[i + 1:i + 4]

                for candidate in next_lines:
                    if candidate in {"Message", "Reach out to " + name}:
                        continue

                    if candidate.lower() in {
                        "india",
                        "united states",
                        "united kingdom",
                        "canada",
                        "australia"
                    }:
                        location = candidate
                        continue

                    if candidate != "." and headline is None:
                        headline = candidate

                break

    profile_url = None
    message_url = None

    for tag in soup.find_all("a", href=True):
        href = tag["href"]

        if not profile_url:
            candidate = normalize_linkedin_profile_url(href)

            if candidate and "srinivas-s-" not in candidate:
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