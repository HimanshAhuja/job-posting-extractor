from src.collect.build_pool import dedupe_key, from_greenhouse, from_lever, model_input

GROWW = {"token": "groww", "company": "Groww"}
ZETA = {"token": "zeta", "company": "Zeta"}


def greenhouse_job(**overrides):
    job = {
        "id": 123,
        "title": " Data Analyst Intern ",
        "location": {"name": "Bengaluru, India"},
        "absolute_url": "https://example.com/123",
        "language": "en",
        "content": "&lt;p&gt;Stipend: &amp;#8377;25K/month&lt;/p&gt;",
    }
    job.update(overrides)
    return job


def test_greenhouse_posting_is_flattened_and_cleaned():
    posting = from_greenhouse(greenhouse_job(), GROWW)
    assert posting["id"] == "greenhouse:groww:123"
    assert posting["company"] == "Groww"
    assert posting["title"] == "Data Analyst Intern"
    assert posting["body"] == "Stipend: ₹25K/month"


def test_lever_sections_are_joined_with_headings():
    job = {
        "id": "abc",
        "text": "Backend Engineer",
        "categories": {"location": "Bangalore", "commitment": "Full-time"},
        "description": "<p>About Zeta</p>",
        "lists": [{"text": "Requirements", "content": "<li>Java</li><li>SQL</li>"}],
        "additional": "",
        "workplaceType": "onsite",
    }
    posting = from_lever(job, ZETA)
    assert posting["body"] == "About Zeta\n\nRequirements\n- Java\n- SQL"
    assert posting["meta"]["workplace_type"] == "onsite"


def test_model_input_has_title_and_location_on_top():
    posting = from_greenhouse(greenhouse_job(), GROWW)
    assert model_input(posting) == "Data Analyst Intern\nLocation: Bengaluru, India\n\nStipend: ₹25K/month"


def lever_job(commitment, workplace):
    return {"id": "abc", "text": "Software Engineer, Internship", "description": "<p>Build things.</p>",
            "categories": {"location": "Bangalore", "commitment": commitment}, "workplaceType": workplace}


def test_lever_header_shows_what_the_job_page_shows():
    posting = from_lever(lever_job("Internship", "onsite"), ZETA)
    assert model_input(posting) == (
        "Software Engineer, Internship\nLocation: Bangalore\nCommitment: Internship\nWorkplace: On-site"
        "\n\nBuild things."
    )


def test_unspecified_workplace_is_not_shown():
    posting = from_lever(lever_job("Full-time", "unspecified"), ZETA)
    assert "Commitment: Full-time" in model_input(posting)
    assert "Workplace:" not in model_input(posting)


def test_model_input_skips_empty_location():
    posting = from_greenhouse(greenhouse_job(location={"name": ""}), GROWW)
    assert "Location:" not in model_input(posting)


def test_reposts_in_other_cities_count_as_duplicates():
    bengaluru = from_greenhouse(greenhouse_job(), GROWW)
    mumbai = from_greenhouse(greenhouse_job(id=456, location={"name": "Mumbai, India"}), GROWW)
    assert dedupe_key(bengaluru) == dedupe_key(mumbai)


def test_different_title_is_not_a_duplicate():
    a = from_greenhouse(greenhouse_job(), GROWW)
    b = from_greenhouse(greenhouse_job(title="Data Scientist Intern"), GROWW)
    assert dedupe_key(a) != dedupe_key(b)
