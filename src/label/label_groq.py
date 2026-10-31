"""Pre-label postings with a Groq model, validated against the schema.

Every result (valid or not) is appended to a JSONL file the moment it arrives,
so a crash or a daily-limit stop loses nothing. Re-running the same command
skips postings that already have a valid label. If an id appears on several
lines, the last line wins.

Usage (from the repo root, with .venv active):
    python -m src.label.label_groq --model openai/gpt-oss-120b --pilot 20
    python -m src.label.label_groq --model openai/gpt-oss-120b --split test
    python -m src.label.label_groq --model qwen/qwen3.8-27b --split train --wait
"""
import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from pydantic import ValidationError

from src.collect.fetch_boards import REPO_ROOT
from src.collect.select_split import SELECTED_PATH
from src.label.prompt import system_prompt, user_prompt
from src.schema import SCHEMA_VERSION, JobPosting

API_URL = "https://api.groq.com/openai/v1/chat/completions"
LABELS_DIR = REPO_ROOT / "data" / "processed" / "labels"
MAX_ATTEMPTS = 2  # the first answer, plus one retry that shows the model its error
TOKENS_PER_REQUEST = 4000  # rough size of one call; pause if fewer tokens remain this minute
OFFLINE_WAIT = 300  # with --wait, how long to wait before trying a dead network again
# gpt-oss models "think" before answering; low effort keeps the hidden thinking short.
MODEL_OPTIONS = {
    "openai/gpt-oss-120b": {"reasoning_effort": "low"},
    "openai/gpt-oss-20b": {"reasoning_effort": "low"},
}


class DailyLimitReached(Exception):
    pass


class RequestTooLarge(Exception):
    pass


class NetworkProblem(Exception):
    pass


SSL_HELP = (
    "TLS certificate check failed: this network is intercepting HTTPS traffic "
    "(common on campus or office Wi-Fi). Switch networks, e.g. a phone hotspot, and re-run. "
    "Never turn certificate checks off: whoever intercepts the traffic would see your API key."
)


def fingerprint(text):
    """Short hash of a text. If the posting text or the prompt changes, so does this."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def parse_duration(text):
    """Groq reset headers look like '615ms', '6s' or '1m26.4s'. Returns seconds."""
    units = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}
    return sum(float(n) * units[u] for n, u in re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", text or ""))


def daily_wait_seconds(resp):
    """How long until the daily bucket holds enough tokens for this request.

    Groq's daily limit refills continuously (200K/day = 2.3 tokens/s), so the
    answer is minutes, not "tomorrow". It's in the retry-after header, or in the
    message ("Please try again in 4m54.6s").
    """
    if resp.headers.get("retry-after"):
        return float(resp.headers["retry-after"])
    found = re.search(r"try again in ([\d.hms]+)", resp.text)
    return parse_duration(found.group(1)) if found else 60


def call_groq(session, model, messages, wait_daily=False):
    """One chat completion. Waits on per-minute limits.

    On the daily limit it raises DailyLimitReached, or with wait_daily=True
    sleeps until the bucket has refilled enough and carries on.

    With wait_daily=True a network outage (lid closed overnight, Wi-Fi not
    connected yet, a network that fails the certificate check) is also waited
    out: try again every 5 minutes. Certificate checks stay on, and the API key
    is only sent after the check passes, so retrying is safe.
    """
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0,  # same input -> (nearly) same label
        "response_format": {"type": "json_object"},  # ask Groq to return JSON only
        **MODEL_OPTIONS.get(model, {}),
    }
    attempt = 0  # counts failures only; waiting for a limit is not a failure
    while attempt < 5:
        started = time.time()
        try:
            # (connect, read) timeouts: give up on a silent connection instead of hanging forever
            resp = session.post(API_URL, json=body, timeout=(10, 120))
        except requests.exceptions.SSLError as err:
            if not wait_daily:
                raise NetworkProblem(SSL_HELP) from err  # retrying now won't fix an intercepted network
            print(f"  TLS certificate check failed, retrying in {OFFLINE_WAIT // 60} min ({now()})")
            time.sleep(OFFLINE_WAIT)
            continue
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as err:
            if wait_daily and attempt >= 4:  # not a blip: offline for a while, so wait it out
                print(f"  network down ({type(err).__name__}), retrying in {OFFLINE_WAIT // 60} min ({now()})")
                time.sleep(OFFLINE_WAIT)
                continue
            print(f"  network error ({type(err).__name__}), retrying in {2 ** attempt}s")
            time.sleep(2 ** attempt)
            attempt += 1
            continue
        resp.api_seconds = time.time() - started  # time spent on the request itself, not on our waits
        if resp.status_code == 200:
            return resp
        if resp.status_code == 400 and "json_validate_failed" in resp.text:
            return resp  # the model wrote broken JSON; label_one handles it
        if resp.status_code == 413:
            raise RequestTooLarge(resp.text[:300])
        if resp.status_code == 429:
            if re.search(r"per day|\(TPD\)|\(RPD\)", resp.text):
                if not wait_daily:
                    raise DailyLimitReached(resp.text[:300])
                wait = daily_wait_seconds(resp)
                print(f"  daily limit: waiting {wait / 60:.1f} min for the bucket to refill ({now()})")
            else:
                wait = float(resp.headers.get("retry-after", 10))
                print(f"  per-minute limit hit, waiting {wait:.0f}s")
            time.sleep(wait + 2)  # a little extra so we don't arrive a moment too early
            continue
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            attempt += 1
            continue
        resp.raise_for_status()  # 400/401/404: a bug in our request, so stop loudly
    raise NetworkProblem("Groq kept failing after 5 tries (network or server errors)")


def pace(resp):
    """If this minute's token allowance is nearly used up, wait until it refills."""
    remaining = int(resp.headers.get("x-ratelimit-remaining-tokens", TOKENS_PER_REQUEST))
    if remaining < TOKENS_PER_REQUEST:
        wait = parse_duration(resp.headers.get("x-ratelimit-reset-tokens")) + 0.5
        print(f"  pacing: {remaining} tokens left this minute, waiting {wait:.0f}s")
        time.sleep(wait)


def strip_reasoning(content):
    """Some models print their thinking in <think>...</think> before the JSON."""
    return re.sub(r"<think>.*?</think>", "", content or "", flags=re.DOTALL).strip()


def label_one(session, model, posting, wait_daily=False):
    messages = [
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": user_prompt(posting["text"])},
    ]
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}
    api_seconds = 0.0
    record = {"id": posting["id"], "split": posting["split"], "model": model, "schema_version": SCHEMA_VERSION,
              # What this label was made from; a later change to either makes it stale.
              "text_sha1": fingerprint(posting["text"]), "prompt_sha1": fingerprint(messages[0]["content"])}

    for attempt in range(1, MAX_ATTEMPTS + 1):
        resp = call_groq(session, model, messages, wait_daily)
        api_seconds += resp.api_seconds
        if resp.ok:
            data = resp.json()
            usage["prompt_tokens"] += data["usage"].get("prompt_tokens", 0)
            usage["completion_tokens"] += data["usage"].get("completion_tokens", 0)
            usage["reasoning_tokens"] += (data["usage"].get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
            content = data["choices"][0]["message"]["content"]
        else:  # Groq's own JSON check failed; it returns what the model wrote
            content = resp.json()["error"].get("failed_generation", "")
        content = strip_reasoning(content)

        try:
            label = JobPosting.model_validate_json(content)  # also catches broken JSON
        except ValidationError as err:
            error = str(err)
            # Show the model exactly what was wrong and ask once more.
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user", "content": f"That JSON is invalid:\n{error[:1500]}\nReturn the corrected JSON object only."},
            ]
            pace(resp)
            continue

        pace(resp)
        return {**record, "valid": True, "label": label.model_dump(mode="json"), "error": None,
                "raw_output": content, "attempts": attempt, "usage": usage,
                "api_seconds": round(api_seconds, 2), "labelled_at": now()}

    return {**record, "valid": False, "label": None, "error": error[:2000], "raw_output": content,
            "attempts": MAX_ATTEMPTS, "usage": usage,
            "api_seconds": round(api_seconds, 2), "labelled_at": now()}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_selected():
    with SELECTED_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def pick_pilot(postings, n):
    """n TRAIN postings (never test: we don't tune prompts on the test set).

    About a quarter internships and a quarter India, so the pilot sees the hard cases.
    Fixed seed, so every model gets exactly the same postings.
    """
    train = sorted((p for p in postings if p["split"] == "train"), key=lambda p: p["id"])
    random.Random(0).shuffle(train)
    interns = [p for p in train if p["is_intern"]][: n // 4]
    chosen = {p["id"] for p in interns}
    india = [p for p in train if p["is_india"] and p["id"] not in chosen][: n // 4]
    chosen |= {p["id"] for p in india}
    rest = [p for p in train if p["id"] not in chosen]
    return (interns + india + rest)[:n]


def up_to_date(out_path, wanted):
    """Ids whose latest label is valid AND was made from today's text and prompt.

    `wanted` maps id -> (text_sha1, prompt_sha1) for the current data. A label
    made before the posting text or the labelling guide changed doesn't count.
    """
    if not out_path.exists():
        return set()
    latest = {}
    with out_path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            latest[row["id"]] = row  # last line for an id wins
    return {
        i for i, row in latest.items()
        if row["valid"] and (row.get("text_sha1"), row.get("prompt_sha1")) == wanted.get(i)
    }


def main():
    parser = argparse.ArgumentParser(description="Pre-label postings with a Groq model.")
    parser.add_argument("--model", required=True)
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--pilot", type=int, metavar="N", help="label N fixed train postings")
    which.add_argument("--split", choices=["train", "val", "test"])
    parser.add_argument("--wait", action="store_true",
                        help="wait out the daily limit and network outages instead of stopping")
    args = parser.parse_args()

    load_dotenv()
    if not os.environ.get("GROQ_API_KEY"):
        sys.exit("GROQ_API_KEY is missing: add it to .env")
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {os.environ['GROQ_API_KEY']}"

    postings = load_selected()
    if args.pilot:
        todo, tag = pick_pilot(postings, args.pilot), "pilot"
    else:
        todo, tag = [p for p in postings if p["split"] == args.split], args.split
    out_path = LABELS_DIR / f"{tag}__{args.model.replace('/', '_')}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_sha1 = fingerprint(system_prompt())
    wanted = {p["id"]: (fingerprint(p["text"]), prompt_sha1) for p in todo}
    done = up_to_date(out_path, wanted)
    todo = [p for p in todo if p["id"] not in done]
    print(f"{len(done)} up to date, {len(todo)} to go -> {out_path.relative_to(REPO_ROOT)}")

    results = []
    stopped_early = False
    with out_path.open("a", encoding="utf-8") as out:
        for i, posting in enumerate(todo, 1):
            try:
                result = label_one(session, args.model, posting, args.wait)
            except DailyLimitReached as err:
                print(f"\nDaily limit reached. It refills continuously: re-run any time, or add --wait to keep going.\n{err}")
                stopped_early = True
                break
            except NetworkProblem as err:
                print(f"\nStopped: {err}\nEverything labelled so far is saved; re-run the same command to continue.")
                stopped_early = True
                break
            except RequestTooLarge as err:
                result = {"id": posting["id"], "split": posting["split"], "model": args.model,
                          "schema_version": SCHEMA_VERSION, "text_sha1": wanted[posting["id"]][0],
                          "prompt_sha1": prompt_sha1, "valid": False, "label": None,
                          "error": f"request too large: {err}", "attempts": 0, "labelled_at": now()}
            out.write(json.dumps(result, ensure_ascii=False) + "\n")
            out.flush()  # on disk now, even if the next call crashes
            results.append(result)
            u = result.get("usage") or {}
            print(f"[{i}/{len(todo)}] {posting['id']}: {'ok ' if result['valid'] else 'BAD'} "
                  f"in={u.get('prompt_tokens', 0)} out={u.get('completion_tokens', 0)} "
                  f"(thinking {u.get('reasoning_tokens', 0)}) {result.get('api_seconds', 0)}s")

    if results:
        ok = [r for r in results if r["valid"]]
        total = sum(r["usage"]["prompt_tokens"] + r["usage"]["completion_tokens"] for r in results if r.get("usage"))
        per = total / len(results)
        print(f"\nValid: {len(ok)}/{len(results)} | first-try valid: {sum(r['attempts'] == 1 for r in ok)}")
        print(f"Tokens per posting: {per:.0f} on average "
              f"-> all {len(postings)} selected postings would need ~{per * len(postings) / 1e6:.2f}M tokens")

    if stopped_early:
        sys.exit(1)  # unfinished: makes `... --split val && ... --split train` stop here instead of skipping ahead


if __name__ == "__main__":
    main()
