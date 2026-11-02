import pytest

import src.label.gold as g
from tests.test_schema import valid_posting

POSTING = {"id": "greenhouse:acme:1", "text": "Data Intern at Acme"}


def test_form_round_trip_keeps_the_label():
    label = g.form_to_label(g.label_to_form(valid_posting()))
    assert label == g.form_to_label(g.label_to_form(label))
    assert g.changed_fields(valid_posting(), label) == []


def test_form_text_becomes_typed_values():
    form = g.label_to_form(g.empty_label())
    form.update(skills="Python\n\n SQL ", pay_min="150,000", pay_max="200000", pay_currency="USD",
                pay_period="year", pay_raw="$150K - $200K", eligible_batches="2027, 2028", fee_required="false")
    label = g.form_to_label(form)
    assert label["skills"] == ["Python", "SQL"]  # blank lines and spaces dropped
    assert label["pay_min"] == 150000 and label["pay_max"] == 200000
    assert label["eligible_batches"] == [2027, 2028]
    assert label["fee_required"] is False
    assert label["company"] is None  # empty box -> null, never ""


def test_whole_numbers_show_without_decimals():
    form = g.label_to_form(valid_posting(pay_min=150000.0, pay_max=150000.0))
    assert form["pay_min"] == "150000"


def test_schema_rules_still_apply_in_the_form():
    form = g.label_to_form(g.empty_label())
    form.update(pay_min="100", pay_max="100")  # numbers without pay_raw
    with pytest.raises(ValueError, match="pay_raw"):
        g.form_to_label(form)


def test_save_appends_and_last_save_wins(tmp_path):
    path = tmp_path / "gold.jsonl"
    prelabel = valid_posting()
    g.save_gold(POSTING, prelabel, prelabel, path=path)
    fixed = {**prelabel, "work_mode": "remote"}
    g.save_gold(POSTING, fixed, prelabel, note=" #LI-Remote tag ", path=path)
    assert len(path.read_text().splitlines()) == 2  # nothing overwritten
    row = g.load_gold(path)[POSTING["id"]]
    assert row["label"]["work_mode"] == "remote"
    assert row["changed_from_prelabel"] == ["work_mode"]
    assert row["note"] == "#LI-Remote tag"


def test_gold_goes_stale_when_the_posting_text_changes(tmp_path):
    path = tmp_path / "gold.jsonl"
    g.save_gold(POSTING, valid_posting(), valid_posting(), path=path)
    gold = g.load_gold(path)
    assert g.checked_ids(gold, [POSTING]) == {POSTING["id"]}
    assert g.checked_ids(gold, [{**POSTING, "text": "Data Intern at Acme (edited)"}]) == set()


def fake_test_set():
    return [{"id": f"t{k:03}", "split": "test" if k < 148 else "train",
             "is_intern": k % 4 == 0, "is_india": k % 6 == 0} for k in range(200)]


def test_gold_sample_is_fixed_and_keeps_the_test_set_mix():
    sample = g.pick_gold(fake_test_set())
    assert len(sample) == 50 and len({p["id"] for p in sample}) == 50
    assert all(p["split"] == "test" for p in sample)
    assert [p["id"] for p in sample] == [p["id"] for p in g.pick_gold(fake_test_set())]
    test = [p for p in fake_test_set() if p["split"] == "test"]
    for flag in ("is_intern", "is_india"):
        expected = 50 * sum(p[flag] for p in test) / len(test)
        assert abs(sum(p[flag] for p in sample) - expected) <= 1
