import re

from src.label.prompt import OUTPUT_FORMAT, system_prompt, user_prompt
from src.schema import JobPosting


def test_output_format_lists_exactly_the_schema_fields():
    # If someone adds a field to the schema but forgets the prompt (or vice
    # versa), every label would fail validation. This test catches it first.
    keys = re.findall(r'^\s*"(\w+)":', OUTPUT_FORMAT, flags=re.MULTILINE)
    assert keys == list(JobPosting.model_fields)


def test_system_prompt_includes_the_labelling_guide():
    assert "If fully remote work is allowed" in system_prompt()


def test_posting_is_wrapped_in_delimiters():
    assert user_prompt("Data Intern") == "Posting:\n<<<\nData Intern\n>>>"
