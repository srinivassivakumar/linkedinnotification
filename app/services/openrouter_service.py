import os
import json
import requests

from dotenv import load_dotenv


load_dotenv()


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openrouter/free"
)


# ============================================================
# HELPER: CALL OPENROUTER AND PARSE JSON
# ============================================================

def call_openrouter_json(
    prompt,
    system_message,
    temperature=0.1
):
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY missing from .env"
        )

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": OPENROUTER_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": system_message
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": temperature
        },
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    choices = data.get("choices", [])

    if not choices:
        print("OpenRouter returned no choices:")
        print(json.dumps(data, indent=2))

        raise RuntimeError(
            "OpenRouter returned no model choices."
        )

    message = choices[0].get(
        "message",
        {}
    )

    content = message.get(
        "content",
        ""
    )

    if content is None:
        content = ""

    content = content.strip()

    print()
    print("RAW OPENROUTER OUTPUT:")
    print("----------------------")
    print(repr(content))
    print()

    if not content:
        print("Full OpenRouter response:")
        print(
            json.dumps(
                data,
                indent=2
            )
        )

        raise RuntimeError(
            "OpenRouter returned empty content."
        )

    # Remove Markdown fences if present
    content = (
        content
        .replace("```json", "")
        .replace("```JSON", "")
        .replace("```", "")
        .strip()
    )

    # Extract JSON object if model added extra text
    start = content.find("{")
    end = content.rfind("}")

    if start == -1 or end == -1:
        raise RuntimeError(
            "OpenRouter response did not contain a JSON object. "
            f"Raw response: {content}"
        )

    json_text = content[start:end + 1]

    try:
        return json.loads(json_text)

    except json.JSONDecodeError as e:
        print("Invalid JSON returned by OpenRouter:")
        print(json_text)

        raise RuntimeError(
            f"Could not parse OpenRouter JSON: {e}"
        )


# ============================================================
# 1. ANALYZE LINKEDIN CONNECTION
# ============================================================

def analyze_connection(
    name,
    headline,
    linkedin_url
):
    prompt = f"""
You are an AI networking assistant helping Srinivas Sivakumar.

A new LinkedIn connection has accepted Srinivas' invitation.

Person name:
{name}

LinkedIn headline:
{headline or "Not available"}

LinkedIn profile:
{linkedin_url or "Not available"}

TASK:

1. Classify the person as:
   - founder
   - employee
   - unknown

2. Extract their current company ONLY when it is clearly
   supported by the supplied LinkedIn headline.

Examples:

Headline:
Assistant Manager at Kotak Mahindra Bank

Company:
Kotak Mahindra Bank


Headline:
Software Engineer @ Microsoft

Company:
Microsoft


Headline:
Founder & CEO at Acme AI

Company:
Acme AI


3. Do not invent a company.

4. If the company cannot be identified from the supplied
   information, return null.

5. Do not invent job openings.

6. The message generated here is only a temporary
   classification-stage message.

7. For employees, do NOT ask for a referral yet.

8. For founders, do NOT invent details about their company.
   Detailed founder messaging will happen after web research.

Return ONLY valid JSON:

{{
    "person_type": "founder|employee|unknown",
    "company": "company name or null",
    "reason": "short explanation",
    "message": "short connection-stage message"
}}
"""

    result = call_openrouter_json(
        prompt=prompt,
        system_message=(
            "Return valid JSON only. "
            "Do not use markdown. "
            "Extract the company only when clearly supported "
            "by the supplied headline. "
            "Never invent facts."
        ),
        temperature=0.1
    )

    person_type = result.get(
        "person_type"
    )

    if person_type not in {
        "founder",
        "employee",
        "unknown"
    }:
        result["person_type"] = "unknown"

    return result


# ============================================================
# 2. EVALUATE JOBS FOR EMPLOYEE
# ============================================================

def evaluate_employee_jobs(
    name,
    company,
    headline,
    search_results
):
    evidence = []

    for index, item in enumerate(
        search_results[:15],
        start=1
    ):
        evidence.append({
            "id": index,
            "title": item.get("title"),
            "url": item.get("href"),
            "snippet": item.get("body")
        })

    first_name = (
        name.split()[0]
        if name
        else "there"
    )

    prompt = f"""
You are evaluating real job opportunities for
Srinivas Sivakumar.

Candidate background:

- 3 years of experience in production AI/ML
  and data engineering
- Python
- AWS
- Docker
- Kubernetes
- RAG
- LLMs
- Agentic AI
- Data Engineering
- Airflow
- Snowflake
- CI/CD
- MLOps
- DevOps
- Cloud Infrastructure

Portfolio:
https://srinivassivakumar.github.io/

Person who accepted Srinivas' LinkedIn connection:

Name:
{name}

First name:
{first_name}

Headline:
{headline}

Company:
{company}

CURRENT WEB SEARCH EVIDENCE:

{json.dumps(evidence, indent=2)}

TARGET ROLES:

- AI Engineer
- Artificial Intelligence Engineer
- Machine Learning Engineer
- ML Engineer
- Data Engineer
- Data Scientist
- MLOps Engineer
- DevOps Engineer
- Cloud Engineer
- GenAI Engineer
- Generative AI Engineer
- LLM Engineer
- related junior AI / data / cloud roles

EXPERIENCE RULE:

Only accept a vacancy if the supplied evidence clearly
supports a required experience level of 3 years or less.

Acceptable examples include:

- 0-2 years
- 1-3 years
- 2 years
- 2+ years
- minimum 2 years
- at least 2 years
- 3 years

Reject examples include:

- 3-5 years
- 3-7 years
- 4+ years
- minimum 4 years

Be conservative.

If experience cannot be confidently determined from
the evidence, reject the role.

CRITICAL RULES:

1. Never invent a vacancy.

2. Never invent an experience requirement.

3. Never invent a job URL.

4. A generic careers page by itself is not enough
   evidence for a specific job.

5. Only return matching_job_found=true if a real
   relevant vacancy is supported by the supplied evidence.

6. Only return matching_job_found=true when the
   experience rule is also satisfied.

7. If multiple supported suitable roles exist, choose
   the strongest match for Srinivas.

8. match_score should be between 0 and 100.

9. If no suitable role exists:
   - matching_job_found must be false
   - job_title must be null
   - job_url must be null
   - required_experience must be null
   - match_score must be 0
   - referral_message must be an empty string


IF A VERIFIED SUITABLE JOB EXISTS:

Write the referral_message in this exact structure:

Hi {first_name},

I noticed {company} is actively hiring for JOB_ROLE. I have 3 years of experience in production AI/ML and data engineering (portfolio: https://srinivassivakumar.github.io/).

I'd be grateful for a referral, or if you could connect me with the right hiring contact or team for these roles.

Regards,

Srinivas Sivakumar


MESSAGE RULES:

- Replace JOB_ROLE with the verified role or a concise,
  evidence-supported role category.

- Do not say "{company} is actively hiring" unless a
  genuine vacancy is supported by the evidence.

- Never generate a referral request if
  matching_job_found is false.

- Never generate a referral request if the required
  experience exceeds 3 years.

- Never generate a referral request when experience
  cannot be verified.

Return ONLY valid JSON:

{{
    "matching_job_found": true,
    "job_title": null,
    "job_url": null,
    "required_experience": null,
    "match_score": 0,
    "reason": "",
    "referral_message": ""
}}
"""

    return call_openrouter_json(
        prompt=prompt,
        system_message=(
            "Return valid JSON only. "
            "Use only the supplied job-search evidence. "
            "Never invent jobs, URLs, or experience requirements. "
            "If evidence is insufficient, reject the role."
        ),
        temperature=0.1
    )


# ============================================================
# 3. RESEARCH FOUNDER'S COMPANY
# ============================================================

def evaluate_founder_company(
    name,
    company,
    headline,
    search_results
):
    evidence = []

    for index, item in enumerate(
        search_results[:15],
        start=1
    ):
        evidence.append({
            "id": index,
            "title": item.get("title"),
            "url": item.get("href"),
            "snippet": item.get("body")
        })

    first_name = (
        name.split()[0]
        if name
        else "there"
    )

    prompt = f"""
You are helping Srinivas Sivakumar write a
LinkedIn message to a startup founder who has
already accepted his connection request.

Srinivas' background:

- Agentic AI
- RAG
- LLMs
- Python
- AWS
- Docker
- Kubernetes
- Computer Vision
- Data Engineering
- Airflow
- Snowflake
- MLOps
- CI/CD
- Cloud Infrastructure

Portfolio:
https://srinivassivakumar.github.io/

Founder:

Name:
{name}

First name:
{first_name}

Headline:
{headline}

Company:
{company}

REAL WEB SEARCH EVIDENCE:

{json.dumps(evidence, indent=2)}

TASK:

1. Understand what the company appears to be building
   using ONLY the supplied evidence.

2. Identify one specific company idea, product,
   platform capability, workflow, or problem that
   genuinely stands out.

3. Identify 1-2 of Srinivas' relevant skills.

4. Identify realistic areas where Srinivas could
   contribute technically.

Examples of contribution areas could include:

- task agents
- RAG pipelines
- AI workflows
- matching
- ranking
- recommendation systems
- marketplace analytics
- data pipelines
- model deployment
- MLOps
- cloud infrastructure

These are only examples.

Only use contribution areas that realistically match
the company evidence.

5. Do not invent company features, products,
   technologies, customers, traction, or plans.

6. If evidence is insufficient, say so clearly.

7. If a reliable official company website appears
   in the evidence, return it as company_url.
   Otherwise return null.


FOUNDER MESSAGE FORMAT:

Write the message in this structure:

Hi {first_name},

I really liked COMPANY_SPECIFIC_POINT.

I work on RELEVANT_SKILLS and could help with SPECIFIC_CONTRIBUTION_AREAS.

Are you currently looking for someone on the AI/data engineering side as the platform grows?

Portfolio: https://srinivassivakumar.github.io/

Regards,
Srinivas Sivakumar


MESSAGE RULES:

- COMPANY_SPECIFIC_POINT must be based on real
  supplied evidence.

- Do not use vague phrases such as:
  "I was impressed by your company"
  unless followed by something specific.

- Mention 1-2 relevant skills.

- Mention specific contribution areas that are
  realistic for that company's product.

- Keep the contribution sentence concise.

- Do not say:
  "Would be great to connect"
  because the founder has already connected.

- Do not directly demand a job.

- It is acceptable to ask:
  "Are you currently looking for someone on the
   AI/data engineering side as the platform grows?"

- Keep the message natural and concise.

Return ONLY valid JSON:

{{
    "company_summary": "",
    "relevant_skills": [],
    "reason": "",
    "message": "",
    "company_url": null
}}
"""

    return call_openrouter_json(
        prompt=prompt,
        system_message=(
            "Return valid JSON only. "
            "Use only the supplied company research evidence. "
            "Never invent company facts. "
            "Keep the founder message specific, technical, "
            "natural, and concise."
        ),
        temperature=0.15
    )