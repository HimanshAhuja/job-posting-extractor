"""Flatten raw Greenhouse and Lever postings into one clean, deduplicated pool.

Reads the newest raw file for every board in boards.csv and writes
    data/processed/pool.jsonl   (one posting per line)
then prints a funnel showing how many postings each filter removed.

Usage (from the repo root, with .venv active):
    python -m src.collect.build_pool
"""
import hashlib
import json
from collections import Counter

from src.collect.clean import escaped_html_to_text, html_to_text
from src.collect.fetch_boards import RAW_DIR, REPO_ROOT, load_boards

POOL_PATH = REPO_ROOT / "data" / "processed" / "pool.jsonl"
MIN_BODY_CHARS = 300  # shorter than this is a stub, not a real posting


def latest_raw_file(platform, token):
    files = sorted((RAW_DIR / platform / token).glob("*.json"))  # YYYY-MM-DD names sort by date
    return files[-1] if files else None


def from_greenhouse(job, board):
    return {
        "id": f"greenhouse:{board['token']}:{job['id']}",
        "company": board["company"],
        "title": job["title"].strip(),
        "location": ((job.get("location") or {}).get("name") or "").strip(),
        "url": job.get("absolute_url"),
        "language": job.get("language"),
        "body": escaped_html_to_text(job.get("content")),
        "meta": {
            "application_deadline": job.get("application_deadline"),
            "first_published": job.get("first_published"),
        },
    }


def from_lever(job, board):
    """Lever splits a posting into a description, titled lists, and a closing section."""
    categories = job.get("categories") or {}
    sections = [html_to_text(job.get("description"))]
    for section in job.get("lists") or []:
        heading = (section.get("text") or "").strip()
        sections.append(f"{heading}\n{html_to_text(section.get('content'))}".strip())
    sections.append(html_to_text(job.get("additional")))
    return {
        "id": f"lever:{board['token']}:{job['id']}",
        "company": board["company"],
        "title": job["text"].strip(),
        "location": (categories.get("location") or "").strip(),
        "url": job.get("hostedUrl"),
        "language": None,  # Lever doesn't report one
        "body": "\n\n".join(s for s in sections if s),
        "meta": {
            "workplace_type": job.get("workplaceType"),
            "commitment": categories.get("commitment"),
            "country": job.get("country"),
        },
    }


FLATTENERS = {"greenhouse": from_greenhouse, "lever": from_lever}


# How Lever job pages display workplace_type; "unspecified" isn't shown at all.
LEVER_WORKPLACE_LABELS = {"onsite": "On-site", "remote": "Remote", "hybrid": "Hybrid"}


def model_input(posting):
    """The text the model reads: what you'd copy from the job page.

    Title and location are shown at the top of every job page. Lever pages also
    show the commitment ("Internship") and workplace ("On-site"), so those lines
    are added for Lever postings only. The company name is not added: the model
    must find it in the text.
    """
    lines = [posting["title"]]
    if posting["location"]:
        lines.append(f"Location: {posting['location']}")
    meta = posting.get("meta") or {}
    if meta.get("commitment"):
        lines.append(f"Commitment: {meta['commitment']}")
    workplace = LEVER_WORKPLACE_LABELS.get((meta.get("workplace_type") or "").replace("-", "").lower())
    if workplace:
        lines.append(f"Workplace: {workplace}")
    return "\n".join(lines) + f"\n\n{posting['body']}"


def dedupe_key(posting):
    """Same company + title + body = same posting, even if the location differs.

    Big companies repost one role once per city; those copies would get
    identical labels (apart from location), so we keep only one.
    """
    raw = f"{posting['company']}\n{posting['title'].lower()}\n{posting['body']}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def build_pool():
    funnel = Counter()
    postings = []
    for board in load_boards():
        path = latest_raw_file(board["platform"], board["token"])
        if path is None:
            print(f"warning: no raw file for {board['platform']}/{board['token']}")
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        for job in raw["jobs"]:
            funnel["raw"] += 1
            posting = FLATTENERS[board["platform"]](job, board)
            posting["fetched_at"] = raw["fetched_at"]
            if posting["language"] not in (None, "en"):
                funnel["not English"] += 1
            elif len(posting["body"]) < MIN_BODY_CHARS:
                funnel[f"body < {MIN_BODY_CHARS} chars"] += 1
            else:
                postings.append(posting)

    # Sort first so "keep the first copy" picks the same one on every run.
    postings.sort(key=lambda p: p["id"])
    kept, copies = {}, Counter()
    for posting in postings:
        key = dedupe_key(posting)
        copies[key] += 1
        if key not in kept:
            kept[key] = posting
    funnel["exact duplicates"] = len(postings) - len(kept)

    POOL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with POOL_PATH.open("w", encoding="utf-8") as f:
        for key, posting in kept.items():
            record = {
                "id": posting["id"],
                "company": posting["company"],
                "title": posting["title"],
                "location": posting["location"],
                "url": posting["url"],
                "fetched_at": posting["fetched_at"],
                "n_copies": copies[key],
                "text": model_input(posting),
                "meta": posting["meta"],
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"{'raw postings':28} {funnel['raw']:6}")
    for reason in ("not English", f"body < {MIN_BODY_CHARS} chars", "exact duplicates"):
        print(f"  - {reason:24} {-funnel[reason]:6}")
    print(f"{'= pool':28} {len(kept):6}  -> {POOL_PATH.relative_to(REPO_ROOT)}")

    # Not removed, just reported: possible near-duplicates to look at by eye.
    same_title = Counter((p["company"], p["title"].lower()) for p in kept.values())
    groups = {k: n for k, n in same_title.items() if n > 1}
    print(f"\nSame company + title but different text: {len(groups)} groups, "
          f"{sum(groups.values())} postings (not removed; check a few by hand)")


if __name__ == "__main__":
    build_pool()
