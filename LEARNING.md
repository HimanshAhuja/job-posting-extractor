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

## Stage 1, Step 3 — The schema

**Why a schema with validation (Pydantic)**
The schema is the contract for every label and every model output. Pydantic checks types, allowed values and cross-field rules, so a bad label fails loudly instead of quietly teaching the model something wrong. The same check later measures *JSON validity rate*: parse the model's text → validate → pass/fail.

**One way to say "unknown"**
Single values use `null`, lists use `[]`, and every key is always present. If some labels said `null` and others `""` or left the key out, the model would learn three ways to express the same thing, and the evaluation would count correct answers as wrong.

**Extract, don't compute**
Small LLMs are unreliable at arithmetic and currency conversion. The model copies pay *as stated* (amount, currency, period, original text); deterministic, unit-tested code does conversions. Each part does what it's good at, and every number can be traced back to `pay_raw`.

**Test one change at a time**
Each test starts from a known-valid example and breaks exactly one field. If it fails validation, that one field must be the cause. Breaking two things at once can't tell you which rule actually works.

## Stage 1, Step 4 — Cleaning HTML

**Two layers of escaping, unescape exactly once**
Greenhouse escapes its whole HTML, and the entities inside it were already escaped (`&amp;nbsp;`). After one `html.unescape()` we have normal HTML; an HTML *parser* then decodes the remaining entities while reading the text. Unescaping twice turns a literal `&lt;table&gt;` in the text into a real `<table>` tag, and the word silently disappears. A test proves it: the double-unescape version outputs `"Write semantic\nmarkup"`.

**Parser over regex for HTML**
`re.sub(r"<[^>]+>", "", s)` can't tell a tag from a `<` in the text, and it loses structure. `html.parser.HTMLParser` knows what's a tag, so we can turn `<li>` into a bullet and `<p>` into a line break. Structure helps the model too: "Requirements:" followed by bullets is easier to read than one long blob.

**A good test fails on the bug it guards against**
Before trusting a test, check that it fails on the wrong implementation. Otherwise it might be passing for the wrong reason.

**Deduplication and the data funnel**
Companies repost one role once per city. Exact copies (same company + title + body, location ignored) waste labelling effort, and if one copy lands in train and another in test, the model is tested on something it has already seen. That's leakage, and it inflates the score. We keep one copy and record `n_copies`. A *funnel* report (raw → minus each filter → final) makes every removal visible, and those numbers go in the dataset card.

**Near-duplicates and why we split by company**
Same company + same title but different text (e.g. the same role with a different pay range per country) is a near-duplicate. We don't delete those, because they're genuinely different postings with different labels. Splitting train/val/test **by company** puts all of a company's variants in the same split, so near-duplicates can't leak across splits.

**Deterministic pipelines**
"Keep the first copy" is only reproducible if "first" is defined: we sort by id before deduplicating. Same input → same output, every run.

## Stage 1, Step 5 — Selection and the company split

**Group split (by company), not a random split**
A random split by posting puts Stripe postings in both train and test. Stripe reuses the same "About Stripe" text, layout and pay format everywhere, so the model would partly be recognising Stripe instead of extracting. Holding out whole companies tests what we actually care about: postings from a company the model has never seen.

**Stratified group split**
With only 40 companies, a plain random company split could put every India-heavy company in train and leave the test set with no Indian postings. So companies are grouped (India-heavy, intern-heavy, other) and each group is dealt across splits separately. Every split then has some of each kind.

**Caps and oversampling**
At most 50 / 25 / 20 postings per company (train / val / test), so Databricks can't be 10% of the data. All internships are taken first because they're rare (~2% of the pool).

**Seeds: fixed, written down, never re-rolled**
`SEED = 42` was set before any results existed. Re-shuffling until the test set "looks nice" is a quiet way to cheat. Each company gets its own seed (`random.Random("42:Stripe")`), so adding one company to the list doesn't reshuffle everyone else's sample.

**Teacher model = upper bound on what we can learn (distillation)**
The training labels come from the Groq API model, so the fine-tuned model is learning to imitate it, including its mistakes. Measuring against hand-verified gold labels (not Groq's) is what tells us the truth.
