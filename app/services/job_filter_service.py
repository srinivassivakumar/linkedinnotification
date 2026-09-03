import re


TARGET_KEYWORDS = [
    "ai engineer",
    "artificial intelligence",
    "machine learning",
    "ml engineer",
    "data engineer",
    "data scientist",
    "mlops",
    "devops",
    "cloud engineer",
    "python developer",
    "generative ai",
    "genai",
    "llm"
]


def is_relevant_job(title, text=""):
    combined = f"{title} {text}".lower()

    return any(
        keyword in combined
        for keyword in TARGET_KEYWORDS
    )


def extract_experience(text):
    """
    Returns an approximate minimum/maximum experience.

    Examples:
    '1-3 years' -> (1, 3)
    '2+ years' -> (2, None)
    'minimum 3 years' -> (3, None)
    """

    if not text:
        return None, None

    text = text.lower()

    patterns = [
        r"(\d+)\s*[-–to]+\s*(\d+)\s*years",
        r"(\d+)\s*\+\s*years",
        r"minimum\s+(\d+)\s*years",
        r"at least\s+(\d+)\s*years",
        r"(\d+)\s*years?\s+of\s+experience"
    ]

    match = re.search(patterns[0], text)

    if match:
        return (
            int(match.group(1)),
            int(match.group(2))
        )

    for pattern in patterns[1:]:
        match = re.search(pattern, text)

        if match:
            return int(match.group(1)), None

    return None, None


def experience_is_eligible(text, max_allowed=3):
    minimum, maximum = extract_experience(text)

    if minimum is None:
        return None

    return minimum <= max_allowed