"""The hand-checked gold labels for the test set, and the logic behind the review app.

Every save appends one line to data/gold/test_gold.jsonl (last line per id wins),
so nothing is ever overwritten and a crash loses at most the posting on screen.
Each gold label must pass the same JobPosting schema as the model labels.

The form in the app edits every field as text. form_to_label / label_to_form
convert between that and a label, and are tested here instead of in the UI.
"""
import json
import random
from datetime import datetime, timezone

from src.collect.fetch_boards import REPO_ROOT
from src.label.label_groq import fingerprint
from src.schema import SCHEMA_VERSION, JobPosting

GOLD_PATH = REPO_ROOT / "data" / "gold" / "test_gold.jsonl"
PRELABEL_PATH = REPO_ROOT / "data" / "processed" / "labels" / "test__openai_gpt-oss-120b.jsonl"

GOLD_SIZE = 50  # hand-checking all 148 would take 5-7 hours; 50 keeps the claim honest in about 2
FIELDS = list(JobPosting.model_fields)
LIST_FIELDS = {"locations", "skills"}  # one item per line in the form
NUMBER_FIELDS = {"duration_value", "pay_min", "pay_max", "min_gpa"}
CHOICES = {  # fields picked from a fixed list; "" means null
    "job_type": ["", "internship", "full_time", "part_time", "contract"],
    "work_mode": ["", "onsite", "remote", "hybrid"],
    "duration_unit": ["", "week", "month"],
    "pay_period": ["", "hour", "day", "week", "month", "year"],
    "fee_required": ["", "true", "false"],
}


def pick_gold(postings, n=GOLD_SIZE):
    """The n test postings to hand-check, the same ones every time.

    A random sample, stratified so it has the same share of internships and
    India postings as the whole test set (a plain random 50 had only 4 India
    postings instead of 8). Proportional, so scores on the sample estimate
    scores on the full test set without reweighting. Never re-drawn after
    seeing results.
    """
    test = sorted((p for p in postings if p["split"] == "test"), key=lambda p: p["id"])
    groups = {}
    for p in test:
        groups.setdefault((p["is_intern"], p["is_india"]), []).append(p)
    exact = {k: n * len(group) / len(test) for k, group in groups.items()}
    sizes = {k: int(x) for k, x in exact.items()}
    for k in sorted(exact, key=lambda k: exact[k] - sizes[k], reverse=True)[: n - sum(sizes.values())]:
        sizes[k] += 1  # the largest remainders get the leftover places
    rng = random.Random("42:gold")
    return [p for k in sorted(groups) for p in rng.sample(groups[k], sizes[k])]


def empty_label():
    return {f: [] if f in LIST_FIELDS or f == "eligible_batches" else None for f in FIELDS}


def label_to_form(label):
    """Label -> {field: text} for the form widgets."""
    form = {}
    for field in FIELDS:
        value = label.get(field)
        if field in LIST_FIELDS:
            form[field] = "\n".join(value or [])
        elif field == "eligible_batches":
            form[field] = ", ".join(str(year) for year in value or [])
        elif field == "fee_required":
            form[field] = "" if value is None else str(value).lower()
        elif value is None:
            form[field] = ""
        elif field in NUMBER_FIELDS and float(value).is_integer():
            form[field] = str(int(value))  # 150000, not 150000.0
        else:
            form[field] = str(value)
    return form


def form_to_label(form):
    """{field: text} -> a validated label dict. Raises ValueError with a readable message."""
    raw = {}
    for field in FIELDS:
        text = form.get(field, "").strip()
        if field in LIST_FIELDS:
            raw[field] = [line.strip() for line in text.splitlines() if line.strip()]
        elif field == "eligible_batches":
            raw[field] = [int(year) for year in text.replace(",", " ").split()]
        elif field == "fee_required":
            raw[field] = {"": None, "true": True, "false": False}[text]
        elif text == "":
            raw[field] = None
        elif field in NUMBER_FIELDS:
            raw[field] = float(text.replace(",", ""))  # "150,000" -> 150000.0
        else:
            raw[field] = text
    return JobPosting(**raw).model_dump(mode="json")  # ValidationError is a ValueError


def changed_fields(prelabel, gold):
    """Fields where the hand-checked label differs from the pre-label."""
    return [f for f in FIELDS if prelabel.get(f) != gold.get(f)]


def load_gold(path=GOLD_PATH):
    """{id: row}, the latest save per posting."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    return {row["id"]: row for row in rows}


def checked_ids(gold, postings):
    """Ids whose gold label was made from the posting text as it is today."""
    current = {p["id"]: fingerprint(p["text"]) for p in postings}
    return {i for i, row in gold.items() if current.get(i) == row["text_sha1"]}


def save_gold(posting, label, prelabel, note="", path=GOLD_PATH):
    """Append one checked label. `label` must already be validated (form_to_label does that)."""
    row = {
        "id": posting["id"],
        "schema_version": SCHEMA_VERSION,
        "text_sha1": fingerprint(posting["text"]),
        "label": label,
        "changed_from_prelabel": changed_fields(prelabel, label),
        "note": note.strip() or None,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row
