import re
from dataclasses import replace
from core.models import Job

def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\b[a-z0-9_\-\.\+#]+\b", text.lower()))

def score_job(job: Job, profile: dict) -> Job:
    """Pure scoring engine. Returns an updated copy of the immutable Job."""
    haystack = f"{job.title} {job.details} {job.org}".lower()
    score = 0
    matched = []

    keyword_rules = profile.get("keywords", {})
    boosts = keyword_rules.get("boost", [])
    penalties = keyword_rules.get("penalty", [])

    for rule in boosts:
        word = rule["word"].lower()
        if re.search(r"\b" + re.escape(word) + r"\b", haystack):
            score += rule["weight"]
            matched.append(f"+{rule['word']}")

    for rule in penalties:
        word = rule["word"].lower()
        if re.search(r"\b" + re.escape(word) + r"\b", haystack):
            score += rule["weight"]
            matched.append(f"-{rule['word']}")

    # Return a new instance due to frozen dataclass
    return replace(
        job,
        score=score,
        matched_keywords=tuple(matched)
    )