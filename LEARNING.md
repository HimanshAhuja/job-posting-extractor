# LEARNING.md

Short notes on each concept, in my own words where possible. Added as the project goes.

## Stage 1, Step 1 — Setup

**Virtual environment (`.venv`)**
An isolated folder with its own Python and packages, so this project's library versions can't clash with other projects or with macOS's system Python. Activate it with `source .venv/bin/activate`; the prompt shows `(.venv)`.

**`requirements.in` vs `requirements.txt`**
`.in` lists the packages *I chose* (intent). `.txt` is the exact frozen list of every package and version that was actually installed (a lock). Anyone who runs `pip install -r requirements.txt` gets the same environment, which makes results reproducible: a different library version can change tokenization or training behaviour and therefore the numbers.

**Why a Mac can fine-tune a 1.5B–3B model**
Apple Silicon has *unified memory*: the CPU and GPU share the same 24 GB, so the GPU can hold the model weights without copying them to a separate graphics card. MLX is Apple's array framework built for this. Rough memory rule: weights ≈ parameters × bytes per parameter, so 1.5B params in 16-bit (2 bytes) ≈ 3 GB, and in 4-bit ≈ 0.75 GB. Training needs extra memory on top for activations, gradients and optimizer state.

**Why API keys go in `.env`, not code**
Anything committed to Git stays in the history forever, even after deletion, and public repos are scanned by bots for keys within minutes. `.env` is listed in `.gitignore`; `.env.example` shows the variable names without values.

**How big should the gold test set be? (sampling error)**
An accuracy measured on n examples is an estimate with noise. Standard error = √(p(1−p)/n); a rough 95% range is ±1.96 × SE. For a field the model gets right 80% of the time:

| n | ±95% range |
|---|---|
| 50 | ±11 points |
| 100 | ±8 points |
| 150 | ±6.4 points |
| 250 | ±5 points |

So with 50 test postings, "fine-tuned 78% vs prompted 72%" could just be luck. We chose **150** gold postings as the balance between labelling time and trustworthy comparisons. Comparing models on the *same* 150 postings (a paired comparison) helps further, because both models face identical difficulty.

**Commit vs push**
`git commit` saves a snapshot into the hidden `.git` folder on my Mac, and nothing leaves the laptop. `git push` uploads those commits to a *remote* (GitHub). GitHub only knows about a repo once I create it there and push to it. Commit often, at every step; push whenever I want GitHub up to date.

## Stage 1, Step 2 — Collecting raw postings

**HTML entities (`&lt;`, `&gt;`, `&amp;`, `&#8377;`)**
A way to write special characters as plain text inside HTML. `&lt;` is the character `<` ("less than"), `&amp;` is `&`, and `&#8377;` is `₹`. Greenhouse sends its HTML *escaped*, so `content` reads `&lt;div&gt;` instead of `<div>`. Cleaning means `html.unescape()` first, then removing the tags. A regex looking for `₹` would silently miss `&#8377;` if we forgot to unescape.

**Raw data is immutable**
Save exactly what the source sent; every later step reads raw and writes a new file. Cleaning code *will* have bugs and *will* change. If cleaning happened during fetching, a bug would permanently damage the data, and live job boards delete postings once roles are filled, so we couldn't download them again.

**Pagination, backoff, resumability**
Lever returns at most `limit` results per request, so we loop with `skip`; a short page means the end. On 429/5xx we wait 2s, then 4s (exponential backoff). Re-running `--all` skips boards already saved today, so a crashed run resumes instead of restarting.

**Random sampling keeps the pool's imbalance**
In the 8,604 raw postings, only about 2% are internships and 5 companies make up 37%. A random 1,500 would contain roughly 30 internships, and the model would barely learn internship fields. Worse, for a field that is almost always null (like `min_cgpa`), a model that *always* outputs null gets nearly 100% accuracy while being useless. That's an inflated metric. The fixes are **stratified selection** (choose how many of each kind to include) and **reporting accuracy separately on postings where the field is actually present**.

**Teacher model = upper bound on what we can learn (distillation)**
The training labels come from the Groq API model, so the fine-tuned model is learning to imitate it, including its mistakes. Measuring against hand-verified gold labels (not Groq's) is what tells us the truth.
