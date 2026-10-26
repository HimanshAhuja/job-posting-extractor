import pytest

from src.collect.select_split import (
    ALLOCATION,
    assign_splits,
    is_india,
    is_internship,
    sample_company,
)


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Software Engineering Intern", True),
        ("Summer Internship 2027 - Data", True),
        ("Co-op, Backend", True),
        ("Internal Audit Manager", False),        # "intern" inside another word
        ("International Tax Lead", False),
        ("Senior Software Engineer", False),
    ],
)
def test_internship_detection(title, expected):
    assert is_internship({"title": title}) == expected


def test_india_from_location_or_country():
    assert is_india({"location": "Bengaluru-VTP, India", "meta": {}})
    assert is_india({"location": "Hyderabad/Bangalore", "meta": {}})
    assert is_india({"location": "East Coast", "meta": {"country": "IN"}})
    assert not is_india({"location": "Remote Canada", "meta": {"country": "CA"}})


def fake_groups():
    groups = {f"india{i}": "india_heavy" for i in range(7)}
    groups.update({f"intern{i}": "intern_heavy" for i in range(6)})
    groups.update({f"other{i}": "other" for i in range(27)})
    return groups


def test_split_sizes_follow_allocation():
    split_of = assign_splits(fake_groups())
    for group, quota in ALLOCATION.items():
        splits = [s for c, s in split_of.items() if c.startswith(group.split("_")[0])]
        assert splits.count("test") == quota["test"]
        assert splits.count("val") == quota["val"]


def test_every_company_gets_exactly_one_split():
    split_of = assign_splits(fake_groups())
    assert set(split_of) == set(fake_groups())
    assert set(split_of.values()) <= {"train", "val", "test"}


def test_split_is_reproducible():
    assert assign_splits(fake_groups()) == assign_splits(fake_groups())


def make_postings(n_intern, n_other):
    interns = [{"id": f"i{k}", "is_intern": True} for k in range(n_intern)]
    others = [{"id": f"o{k}", "is_intern": False} for k in range(n_other)]
    return interns + others


def test_sample_respects_cap_and_keeps_internships_first():
    chosen = sample_company(make_postings(n_intern=5, n_other=100), cap=20, company="Acme")
    assert len(chosen) == 20
    assert sum(p["is_intern"] for p in chosen) == 5


def test_sample_takes_everything_from_small_company():
    assert len(sample_company(make_postings(2, 3), cap=20, company="Tiny")) == 5


def test_sample_does_not_depend_on_input_order():
    postings = make_postings(3, 50)
    forward = sample_company(postings, cap=10, company="Acme")
    backward = sample_company(list(reversed(postings)), cap=10, company="Acme")
    assert [p["id"] for p in forward] == [p["id"] for p in backward]
