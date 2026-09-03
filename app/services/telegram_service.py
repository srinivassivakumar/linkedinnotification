import os
import requests
from dotenv import load_dotenv


load_dotenv()


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def send_approval_card(connection):

    connection_id = connection["id"]

    name = connection.get("name", "Unknown")
    person_type = connection.get("person_type", "unknown")
    company = connection.get("company", "Unknown company")

    generated_message = connection.get(
        "generated_message",
        "No message generated."
    )

    linkedin_url = connection.get("linkedin_url")
    company_url = connection.get("company_url")
    job_url = connection.get("job_url")


    if person_type == "founder":

        text = (
            f"🚀 NEW FOUNDER CONNECTION\n\n"
            f"{name}\n"
            f"Founder @ {company}\n\n"
            f"Suggested message:\n\n"
            f"{generated_message}"
        )

    else:

        job_title = connection.get("job_title")
        experience = connection.get("required_experience")
        score = connection.get("job_match_score")

        text = (
            f"🔔 NEW CONNECTION\n\n"
            f"{name}\n"
            f"Employee @ {company}\n\n"
        )

        if job_title:
            text += f"Matching vacancy:\n{job_title}\n\n"

        if experience:
            text += f"Experience:\n{experience}\n\n"

        if score is not None:
            text += f"Match:\n{score}%\n\n"

        text += (
            f"Suggested message:\n\n"
            f"{generated_message}"
        )


    buttons = [
        [
            {
                "text": "✅ APPROVE",
                "callback_data": f"approve:{connection_id}"
            },
            {
                "text": "❌ SKIP",
                "callback_data": f"skip:{connection_id}"
            }
        ]
    ]


    link_buttons = []

    if linkedin_url:
        link_buttons.append({
            "text": "👤 LINKEDIN",
            "url": linkedin_url
        })

    if person_type == "founder" and company_url:
        link_buttons.append({
            "text": "🌐 COMPANY",
            "url": company_url
        })

    elif person_type != "founder" and job_url:
        link_buttons.append({
            "text": "💼 JOB",
            "url": job_url
        })

    if link_buttons:
        buttons.append(link_buttons)


    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "reply_markup": {
            "inline_keyboard": buttons
        }
    }


    response = requests.post(
        f"{BASE_URL}/sendMessage",
        json=payload,
        timeout=15
    )

    response.raise_for_status()

    return response.json()


def get_updates(offset=None):

    params = {
        "timeout": 30
    }

    if offset is not None:
        params["offset"] = offset

    response = requests.get(
        f"{BASE_URL}/getUpdates",
        params=params,
        timeout=35
    )

    response.raise_for_status()

    return response.json()


def answer_callback_query(callback_query_id, text=None):

    payload = {
        "callback_query_id": callback_query_id
    }

    if text:
        payload["text"] = text

    response = requests.post(
        f"{BASE_URL}/answerCallbackQuery",
        json=payload,
        timeout=15
    )

    response.raise_for_status()

    return response.json()


def send_message(text, buttons=None):

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text
    }

    if buttons:
        payload["reply_markup"] = {
            "inline_keyboard": buttons
        }

    response = requests.post(
        f"{BASE_URL}/sendMessage",
        json=payload,
        timeout=15
    )

    response.raise_for_status()

    return response.json()