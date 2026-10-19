from core.models import Job
from core.scorer import score_job

def test_scorer_boost_and_penalty():
    profile = {
        "keywords": {
            "boost": [
                {"word": "python", "weight": 20},
                {"word": "junior", "weight": 10}
            ],
            "penalty": [
                {"word": "senior", "weight": -50}
            ]
        }
    }
    
    # Positive case
    good_job = Job(
        source="Test", id="1", url="http://x",
        title="Junior Python Engineer",
        details="Great role for junior developers"
    )
    scored_good = score_job(good_job, profile)
    assert scored_good.score == 30
    assert "+python" in scored_good.matched_keywords
    assert "+junior" in scored_good.matched_keywords

    # Negative penalty case
    bad_job = Job(
        source="Test", id="2", url="http://x",
        title="Senior Python Architect",
        details="Must have 10 years experience"
    )
    scored_bad = score_job(bad_job, profile)
    assert scored_bad.score == -30  # 20 (python) - 50 (senior)
    assert "-senior" in scored_bad.matched_keywords