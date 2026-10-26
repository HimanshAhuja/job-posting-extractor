"""Check the Groq API key and discover this account's models and rate limits.

Usage (from the repo root, with .venv active):
    python -m src.label.groq_check              # list the models this key can use
    python -m src.label.groq_check MODEL_ID     # one tiny call; print its rate-limit headers
"""
import os
import sys

import requests
from dotenv import load_dotenv

API = "https://api.groq.com/openai/v1"  # Groq speaks the same API format as OpenAI


def main():
    load_dotenv()  # reads .env into environment variables
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        sys.exit("GROQ_API_KEY is missing: add it to .env (never to code)")
    headers = {"Authorization": f"Bearer {key}"}

    if len(sys.argv) == 1:
        resp = requests.get(f"{API}/models", headers=headers, timeout=30)
        resp.raise_for_status()
        for model in sorted(resp.json()["data"], key=lambda m: m["id"]):
            print(f"{model['id']:50} context_window={model.get('context_window')}")
        return

    resp = requests.post(
        f"{API}/chat/completions",
        headers=headers,
        timeout=60,
        json={
            "model": sys.argv[1],
            "messages": [{"role": "user", "content": "Reply with the word OK."}],
            "max_tokens": 5,
        },
    )
    print("status:", resp.status_code)
    # Every response tells us our limits and how much is left.
    for name, value in resp.headers.items():
        if name.lower().startswith("x-ratelimit"):
            print(f"{name}: {value}")
    if resp.ok:
        print("usage:", resp.json().get("usage"))
    else:
        print(resp.text[:500])


if __name__ == "__main__":
    main()
