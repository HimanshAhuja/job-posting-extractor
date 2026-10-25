import json

import pytest
from pydantic import ValidationError

from src.schema import JobPosting


def valid_posting(**overrides):
    """A complete, valid label; tests change one thing at a time."""
    posting = {
        "company": "Stripe",
        "role": "Software Engineering Intern",
        "job_type": "internship",
        "work_mode": "hybrid",
        "locations": ["Bengaluru, India"],
        "skills": ["Python", "SQL"],
        "start": "2027-06",
        "deadline": "2026-11-30",
        "duration_value": 12,
        "duration_unit": "week",
        "pay_min": 80000,
        "pay_max": 80000,
        "pay_currency": "INR",
        "pay_period": "month",
        "pay_raw": "₹80K/month",
        "eligible_batches": [2027, 2028],
        "min_gpa": 7.5,
        "fee_required": None,
    }
    posting.update(overrides)
    return posting


def all_unknown():
    """A posting that states nothing we extract: nulls and empty lists."""
    posting = {key: None for key in valid_posting()}
    posting.update(locations=[], skills=[], eligible_batches=[])
    return posting


def test_valid_posting_passes():
    JobPosting.model_validate(valid_posting())


def test_everything_unknown_passes():
    JobPosting.model_validate(all_unknown())


def test_model_output_string_is_parsed():
    # This is how we'll check raw LLM output: a JSON string, not a dict.
    JobPosting.model_validate_json(json.dumps(valid_posting()))


def test_missing_key_rejected():
    posting = valid_posting()
    del posting["work_mode"]
    with pytest.raises(ValidationError):
        JobPosting.model_validate(posting)


def test_invented_key_rejected():
    with pytest.raises(ValidationError):
        JobPosting.model_validate(valid_posting(salary="lots"))


@pytest.mark.parametrize(
    "field, bad_value",
    [
        ("job_type", "Full-time"),       # must be one of the allowed labels
        ("start", "2027-13"),            # no month 13
        ("start", "June 2027"),          # must be YYYY-MM
        ("deadline", "2026-02-30"),      # not a real date
        ("pay_currency", "Rs"),          # must be an ISO code like INR
        ("pay_min", -5),                 # pay can't be negative
        ("eligible_batches", [28]),      # a year, not "28"
        ("min_gpa", 75),                 # GPA scales stop at 10
        ("company", ""),                 # empty string should be null
    ],
)
def test_bad_values_rejected(field, bad_value):
    with pytest.raises(ValidationError):
        JobPosting.model_validate(valid_posting(**{field: bad_value}))


def test_pay_min_above_max_rejected():
    with pytest.raises(ValidationError):
        JobPosting.model_validate(valid_posting(pay_min=90000, pay_max=80000))


def test_pay_numbers_need_raw_text():
    with pytest.raises(ValidationError):
        JobPosting.model_validate(valid_posting(pay_raw=None))


def test_pay_text_without_numbers_allowed():
    # "Competitive stipend" names pay but gives no amount.
    JobPosting.model_validate(
        valid_posting(pay_min=None, pay_max=None, pay_currency=None, pay_period=None,
                      pay_raw="Competitive stipend")
    )


def test_duration_needs_unit():
    with pytest.raises(ValidationError):
        JobPosting.model_validate(valid_posting(duration_unit=None))
