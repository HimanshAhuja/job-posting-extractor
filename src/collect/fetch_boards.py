"""Fetch raw job postings from public Greenhouse and Lever job-board APIs.

Each board's response is saved untouched to
    data/raw/<platform>/<token>/<YYYY-MM-DD>.json
Cleaning happens later in a separate step, so we can always redo it from raw.

Usage (from the repo root, with .venv active):
    python -m src.collect.fetch_boards greenhouse groww    # one board
    python -m src.collect.fetch_boards --all               # every board in boards.csv
"""
import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"
BOARDS_CSV = Path(__file__).with_name("boards.csv")
HEADERS = {"User-Agent": "job-posting-extractor (student research project)"}
RETRY_STATUSES = {429, 500, 502, 503, 504}  # worth retrying: rate limit or server hiccup
PAUSE_SECONDS = 1.0  # politeness gap between requests
LEVER_PAGE_SIZE = 100


def get_json(url, params=None, retries=3):
    """GET a URL and return parsed JSON; None if the board doesn't exist (404)."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
        except requests.RequestException as err:  # DNS failure, timeout, dropped connection
            problem = repr(err)
        else:
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
            problem = f"HTTP {resp.status_code}"
            if resp.status_code not in RETRY_STATUSES:
                break  # e.g. 403: retrying won't help
        if attempt < retries:
            time.sleep(2 ** attempt)  # exponential backoff: wait 2s, then 4s
    raise RuntimeError(f"Failed to fetch {url}: {problem}")


def fetch_greenhouse(token):
    """All jobs on one Greenhouse board, including full descriptions."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    data = get_json(url, params={"content": "true"})
    return url, (data["jobs"] if data else [])


def fetch_lever(token):
    """All postings on one Lever board. Lever pages its results, so we loop."""
    url = f"https://api.lever.co/v0/postings/{token}"
    jobs = []
    while True:
        page = get_json(url, params={"mode": "json", "limit": LEVER_PAGE_SIZE, "skip": len(jobs)})
        if not page:  # None (no board) or [] (no more results)
            break
        jobs.extend(page)
        if len(page) < LEVER_PAGE_SIZE:  # a short page means it was the last one
            break
        time.sleep(PAUSE_SECONDS)
    return url, jobs


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever}


def today_utc():
    return datetime.now(timezone.utc).date().isoformat()


def raw_path(platform, token, day):
    return RAW_DIR / platform / token / f"{day}.json"


def save_raw(platform, token, url, jobs):
    """Write jobs plus provenance (where and when we got them) to data/raw."""
    fetched_at = datetime.now(timezone.utc)
    out = raw_path(platform, token, fetched_at.date().isoformat())
    out.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "platform": platform,
        "token": token,
        "source_url": url,
        "fetched_at": fetched_at.isoformat(timespec="seconds"),
        "n_jobs": len(jobs),
        "jobs": jobs,
    }
    out.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def load_boards(path=BOARDS_CSV):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fetch_all(force=False):
    """Fetch every board in boards.csv, skipping ones already saved today."""
    day = today_utc()
    rows, failed = [], []
    for board in load_boards():
        platform, token = board["platform"], board["token"]
        path = raw_path(platform, token, day)
        if path.exists() and not force:
            n_jobs = json.loads(path.read_text(encoding="utf-8"))["n_jobs"]
            status = "cached"
        else:
            try:
                url, jobs = FETCHERS[platform](token)
            except RuntimeError as err:  # one bad board shouldn't stop the whole run
                print(f"FAILED {platform}/{token}: {err}")
                failed.append(f"{platform}/{token}")
                continue
            save_raw(platform, token, url, jobs)
            n_jobs, status = len(jobs), "fetched"
            time.sleep(PAUSE_SECONDS)
        print(f"{status:8} {platform}/{token}: {n_jobs} jobs")
        rows.append((board["company"], platform, n_jobs))

    print(f"\n{'company':15} {'platform':11} {'jobs':>5}")
    for company, platform, n_jobs in sorted(rows, key=lambda r: -r[2]):
        flag = "  <- empty board" if n_jobs == 0 else ""
        print(f"{company:15} {platform:11} {n_jobs:5}{flag}")
    print(f"\nTotal: {sum(r[2] for r in rows)} jobs from {len(rows)} boards ({day} UTC)")
    if failed:
        print(f"Failed: {', '.join(failed)}  (re-run the same command to retry just these)")


def main():
    parser = argparse.ArgumentParser(description="Fetch raw postings from public job boards.")
    parser.add_argument("platform", nargs="?", choices=sorted(FETCHERS))
    parser.add_argument("token", nargs="?", help="board name, e.g. 'groww' in boards.greenhouse.io/groww")
    parser.add_argument("--all", action="store_true", help="fetch every board in boards.csv")
    parser.add_argument("--force", action="store_true", help="re-fetch boards already saved today")
    args = parser.parse_args()

    if args.all:
        fetch_all(force=args.force)
    elif args.platform and args.token:
        url, jobs = FETCHERS[args.platform](args.token)
        path = save_raw(args.platform, args.token, url, jobs)
        print(f"{args.platform}/{args.token}: {len(jobs)} jobs -> {path.relative_to(REPO_ROOT)}")
    else:
        parser.error("give PLATFORM and TOKEN, or use --all")


if __name__ == "__main__":
    main()
