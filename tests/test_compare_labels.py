import json

from src.label.compare_labels import load_fresh_labels


def row(id_, text_sha1, valid=True):
    return {"id": id_, "valid": valid, "label": {"company": "Acme"} if valid else None,
            "text_sha1": text_sha1, "prompt_sha1": "guide-v2"}


def test_stale_and_invalid_labels_are_not_compared(tmp_path):
    path = tmp_path / "labels.jsonl"
    rows = [row("fresh", "t1"), row("old-text", "t0"), row("broken", "t3", valid=False)]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    wanted = {"fresh": ("t1", "guide-v2"), "old-text": ("t2", "guide-v2"), "broken": ("t3", "guide-v2")}
    labels, stale = load_fresh_labels(path, wanted)
    assert set(labels) == {"fresh"}
    assert stale == 1  # the invalid one is not "stale", just not valid
