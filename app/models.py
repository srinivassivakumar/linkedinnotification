from dataclasses import dataclass


@dataclass
class Connection:

    name: str

    current_title: str

    linkedin_url: str

    person_type: str = None

    company: str = None

    company_summary: str = None

    job_title: str = None

    job_url: str = None

    required_experience: str = None

    job_match_score: float = None

    generated_message: str = None

    status: str = "pending"