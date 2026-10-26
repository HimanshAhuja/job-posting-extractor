"""Choose ~1,500 postings from the pool and split them into train / val / test BY COMPANY.

1. Flag each posting: internship? India-based?
2. Put each company in a group (india-heavy, intern-heavy, other) and, within each
   group, shuffle companies with a fixed seed and deal them into test / val / train.
   Every posting of a company lands in the same split, so the test set only has
   companies the model never saw in training.
3. Within each company take at most CAPS[split] postings, internships first,
   so no single company dominates and the rare internships are all kept.

Writes data/processed/selected.jsonl (with text, gitignored) and
data/splits.csv (ids only, committed so the split is reproducible).

Usage: python -m src.collect.select_split
"""
import csv
import json
import random
import re
from collections import Counter, defaultdict

from src.collect.build_pool import POOL_PATH
from src.collect.fetch_boards import REPO_ROOT

SEED = 42  # fixed before looking at any results; never re-rolled for a "nicer" split
SELECTED_PATH = REPO_ROOT / "data" / "processed" / "selected.jsonl"
SPLITS_CSV = REPO_ROOT / "data" / "splits.csv"

INTERN_RE = re.compile(r"\bintern(ship)?s?\b|\bco-?op\b|\bapprentice", re.IGNORECASE)
INDIA_RE = re.compile(
    r"india|bengaluru|bangalore|mumbai|pune|hyderabad|gurgaon|gurugram|delhi|noida|chennai|kolkata",
    re.IGNORECASE,
)

# How many companies of each group go to test and val; the rest go to train.
# Val only tracks loss during training, so it gets no intern-heavy company:
# the rare internships are worth more in train.
ALLOCATION = {
    "india_heavy": {"test": 2, "val": 1},
    "intern_heavy": {"test": 2, "val": 0},
    "other": {"test": 4, "val": 4},
}
CAPS = {"train": 50, "val": 25, "test": 20}  # max postings per company in each split


def is_internship(posting):
    return bool(INTERN_RE.search(posting["title"]))


def is_india(posting):
    return bool(INDIA_RE.search(posting["location"])) or posting["meta"].get("country") == "IN"


def company_group(postings):
    n_india = sum(p["is_india"] for p in postings)
    n_intern = sum(p["is_intern"] for p in postings)
    if n_india / len(postings) >= 0.5:
        return "india_heavy"
    if n_intern >= 10:
        return "intern_heavy"
    return "other"


def assign_splits(groups):
    """Map company -> split. `groups` maps company -> group name."""
    split_of = {}
    for group, quota in ALLOCATION.items():
        companies = sorted(c for c, g in groups.items() if g == group)  # fixed order first
        random.Random(f"{SEED}:{group}").shuffle(companies)
        n_test, n_val = quota["test"], quota["val"]
        for i, company in enumerate(companies):
            split_of[company] = "test" if i < n_test else "val" if i < n_test + n_val else "train"
    return split_of


def sample_company(postings, cap, company):
    """Up to `cap` postings: all internships first (they're rare), then a random rest."""
    rng = random.Random(f"{SEED}:{company}")  # own seed per company: adding one company doesn't reshuffle others
    ordered = sorted(postings, key=lambda p: p["id"])
    interns = [p for p in ordered if p["is_intern"]]
    others = [p for p in ordered if not p["is_intern"]]
    rng.shuffle(interns)
    rng.shuffle(others)
    return (interns + others)[:cap]


def main():
    by_company = defaultdict(list)
    with POOL_PATH.open(encoding="utf-8") as f:
        for line in f:
            posting = json.loads(line)
            posting["is_intern"] = is_internship(posting)
            posting["is_india"] = is_india(posting)
            by_company[posting["company"]].append(posting)

    groups = {company: company_group(ps) for company, ps in by_company.items()}
    split_of = assign_splits(groups)

    selected = []
    for company in sorted(by_company):
        split = split_of[company]
        for posting in sample_company(by_company[company], CAPS[split], company):
            selected.append({**posting, "split": split, "group": groups[company]})

    with SELECTED_PATH.open("w", encoding="utf-8") as f:
        for posting in selected:
            f.write(json.dumps(posting, ensure_ascii=False) + "\n")
    with SPLITS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "company", "split"])
        for posting in selected:
            writer.writerow([posting["id"], posting["company"], posting["split"]])

    print(f"{'split':6} {'companies':>9} {'postings':>8} {'intern':>7} {'india':>6}")
    for split in ("train", "val", "test"):
        rows = [p for p in selected if p["split"] == split]
        n_companies = len({p["company"] for p in rows})
        print(f"{split:6} {n_companies:9} {len(rows):8} "
              f"{sum(p['is_intern'] for p in rows):7} {sum(p['is_india'] for p in rows):6}")
    print(f"{'total':6} {len(by_company):9} {len(selected):8}")
    for split in ("val", "test"):
        names = sorted(c for c, s in split_of.items() if s == split)
        print(f"\n{split} companies: {', '.join(names)}")
    print(f"\nWrote {SELECTED_PATH.relative_to(REPO_ROOT)} and {SPLITS_CSV.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
