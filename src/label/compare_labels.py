"""Compare two label files field by field, on the postings both labelled.

Agreement is not accuracy: two models can agree and both be wrong, and
"both said null" is the easiest kind of agreement. So the table also shows
agreement on the postings where at least one model found a value, and the
disagreements are printed for checking by hand against the posting.

Only labels made from today's posting text and today's guide are compared;
stale ones are counted and skipped, so an old label can't pass for a new one.

Usage (from the repo root, with .venv active):
    python -m src.label.compare_labels FILE_A FILE_B
    python -m src.label.compare_labels FILE_A FILE_B --show pay_min
"""
import argparse
import json
from pathlib import Path

from src.label.label_groq import fingerprint, load_selected, up_to_date
from src.label.prompt import system_prompt
from src.schema import JobPosting


def load_fresh_labels(path, wanted):
    """Latest valid label per id, keeping only those made from today's text and guide.

    Returns (labels, number of stale labels skipped).
    """
    labels = {}
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            labels[row["id"]] = row["label"] if row["valid"] else None  # last line wins
    fresh = up_to_date(Path(path), wanted)
    valid = {i: label for i, label in labels.items() if label is not None}
    return {i: label for i, label in valid.items() if i in fresh}, len(valid) - len(fresh & set(valid))


def normalise(value):
    """Ignore differences that don't matter: case, spacing, list order, 12 vs 12.0."""
    if isinstance(value, str):
        return " ".join(value.casefold().split())
    if isinstance(value, list):
        return sorted({normalise(v) for v in value}, key=str)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def is_empty(value):
    return value is None or value == []


def main():
    parser = argparse.ArgumentParser(description="Compare two label files field by field.")
    parser.add_argument("file_a")
    parser.add_argument("file_b")
    parser.add_argument("--show", metavar="FIELD", help="print every disagreement for this field")
    args = parser.parse_args()

    prompt_sha1 = fingerprint(system_prompt())
    wanted = {p["id"]: (fingerprint(p["text"]), prompt_sha1) for p in load_selected()}
    (a, stale_a), (b, stale_b) = load_fresh_labels(args.file_a, wanted), load_fresh_labels(args.file_b, wanted)
    shared = sorted(set(a) & set(b))
    print(f"A: {args.file_a} ({stale_a} stale labels skipped)\n"
          f"B: {args.file_b} ({stale_b} stale labels skipped)\n"
          f"Postings with a fresh, valid label from both: {len(shared)}\n")
    if not shared:
        raise SystemExit("Nothing to compare: re-run the labeller for both models first.")
    print(f"{'field':17} {'agree':>7} {'both empty':>11} {'agree when a value exists':>27}")

    disagreements = {}
    for field in JobPosting.model_fields:
        agree = both_empty = has_value = agree_value = 0
        for i in shared:
            va, vb = a[i][field], b[i][field]
            same = normalise(va) == normalise(vb)
            agree += same
            if is_empty(va) and is_empty(vb):
                both_empty += 1
            else:
                has_value += 1
                agree_value += same
                if not same:
                    disagreements.setdefault(field, []).append((i, va, vb))
        value_part = f"{agree_value}/{has_value}" if has_value else "-"
        print(f"{field:17} {agree:3}/{len(shared):<3} {both_empty:11} {value_part:>27}")

    fields = [args.show] if args.show else list(disagreements)
    for field in fields:
        rows = disagreements.get(field, [])
        limit = None if args.show else 2  # all for --show, else a taste
        print(f"\n--- {field}: {len(rows)} disagreement(s)")
        for i, va, vb in rows[:limit]:
            print(f"  {i}\n    A: {json.dumps(va, ensure_ascii=False)}\n    B: {json.dumps(vb, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
