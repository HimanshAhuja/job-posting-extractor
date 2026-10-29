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
*Near miss (Stage 1):* I once pasted the real key into `.env.example`. That file **is** tracked by git, so the next `git add .` would have committed the key. Rule: real values only ever go in `.env`. Quick check: `git ls-files .env.example` prints the name (tracked), while `git ls-files .env` prints nothing (ignored).

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

## Stage 1, Step 6 — API budgeting

**Three kinds of rate limits**
RPD (requests per day), TPM (tokens per minute) and TPD (tokens per day). On my Groq free tier, the big models allow 1,000 RPD and 8,000 TPM, and Groq's docs list 200K TPD. The binding constraint is whichever runs out first. For us that's TPD: about 4.7M tokens needed ÷ 200K per day ≈ 24 days.

**Token budget = input + prompt + output (+ reasoning)**
Posting text ≈ chars ÷ 4 (measured: ~1,580 tokens per posting on average). Every request also pays for the instructions again, plus the answer. Reasoning models (gpt-oss) also spend hidden "reasoning tokens", and those count too. Measure on a small pilot before planning the full run.

**Why not just delete boilerplate to save tokens?**
36% of the text is paragraphs a company repeats across postings ("About Stripe", benefits, EEO). But I counted 2,240 of those repeated paragraphs mentioning work mode, pay or internships, e.g. a company-wide "we work in-office 3 days a week" line. Deleting them would delete the evidence for our labels. Data reduction has to be checked against the fields we extract.

## Stage 1, Step 7 — The labeller

**One source of truth for the rules**
The system prompt is built from LABELING_GUIDE.md, and a test checks that the prompt's key list equals the schema's fields. Groq and I label by the same rules, and schema/prompt drift is caught before any tokens are spent.

**Prompt injection**
Postings are text written by strangers. A posting could contain "ignore previous instructions…". We wrap it in `<<< >>>` and tell the model to treat it only as data. That's not a guarantee, but it's the basic defence, and Pydantic validation catches outputs that go off the rails.

**Validate, then retry with feedback**
`temperature=0` makes answers (nearly) repeatable. If the JSON fails validation, the model gets one retry *with the exact error message*, which usually fixes it. Every retry costs tokens, so we count first-try vs second-try success.

**Crash-safe, resumable jobs**
Each result is appended and `flush()`ed to disk as soon as it arrives. A crash or a daily-limit stop loses at most the posting in progress, and re-running skips what's done.

**Pilot on train, never on test**
Looking at test postings while tuning the prompt quietly fits the prompt to the test set. Pilots and prompt fixes use train postings only.

**`CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain`**
HTTPS proves you're talking to the real server: the server presents a certificate signed by an authority your computer trusts. Some campus/office networks decrypt and re-encrypt all traffic ("TLS interception") using their own certificate, and Python correctly refuses it. The fix is a different network, not `verify=False`. Turning verification off would let the interceptor read the `Authorization` header, i.e. the API key.

**Long jobs on a laptop**
Timeouts `(connect=10s, read=120s)` stop a dead connection from hanging forever. `caffeinate -i <command>` keeps the Mac awake while the command runs. Measure API time separately from deliberate rate-limit waits, or the latency numbers are meaningless.

**Testing code that calls an API**
A fake session returns canned responses (valid JSON, broken JSON, 429 errors), so retry and limit logic is tested with no network and no tokens spent.

**Agreement is not accuracy**
Two models agreeing doesn't make them right; both can be wrong the same way. And "both said null" is the cheapest agreement there is: in the pilot, `start`, `deadline` and `min_gpa` were 11/11 "agree" purely because both models left them empty. Always look at agreement *where a value exists*, and settle disagreements by reading the posting.

**Disagreements expose gaps in the guide**
The pilot's disagreements were mostly *rule* problems, not model problems. `skills` was undefined enough that one model listed "customer service" and "English". Palantir's text only had a company-wide "many teams offer hybrid" policy. Each disagreement became a sharper rule in LABELING_GUIDE.md, which is cheaper than any model upgrade.

**The model input should match what a user would paste**
Lever job pages show "Internship · On-site" in the header, but our first version left those out of the text. The model was being asked for facts it couldn't see. Now Lever postings get `Commitment:` and `Workplace:` lines, exactly as the page shows them. Greenhouse pages have no such line, so nothing is added there.

**Labels go stale: fingerprint their inputs**
A label is only valid for the exact text and the exact instructions it was made from. Each label stores `text_sha1` and `prompt_sha1` (short hashes). If the posting text or LABELING_GUIDE.md changes, the hashes no longer match and the labeller redoes that posting automatically. Old labels can't silently mix with new rules.

**A safety check only works if every reader uses it**
The labeller skipped stale labels, but the comparison script didn't, so it happily compared two sets of old labels and the table looked like a fresh result. Now `compare_labels` uses the same `up_to_date()` check and says how many stale labels it skipped. Rule: put the "is this still valid?" logic in one function and call it everywhere a label is read (comparison now; training and evaluation later).

**Count how common a case is before writing a rule for it**
The fresh pilot showed one `#LI-Hybrid` tag and one OTE pay range. Before adding rules, I counted them across all 1,529 selected postings: about 270 have a `#LI-` work-mode tag and 139 mention OTE. A case seen once in a pilot can affect a fifth of the dataset. Also, both models agreed on the Auth0 OTE range and were both wrong (OTE includes commission, and the guide says base pay only). Agreement tables can't find that; only reading the posting can.

**Anchoring bias in gold labels**
When you correct pre-filled labels, you tend to accept what's already there. If the test set were pre-labelled by the teacher (Qwen), the gold set would lean toward Qwen's answers, which flatters the teacher and the student that copies it. So test is pre-labelled by a different model (gpt-oss-120b). Any leftover bias now goes *against* the fine-tuned model, which is the safe direction when the claim is "fine-tuning wins".

**One teacher per training set; limits are per model**
Groq's daily limits are per model, so two models give two separate budgets: gpt-oss labels test, Qwen labels val and train. Never mix teachers inside train, or the student learns two slightly different labelling styles.

**Freeze the guide once real labelling starts**
Before: a guide change is cheap (re-run 20 pilot postings). After: it makes every label stale. New cases go into DECISIONS.md, and only a case that matters enough triggers a relabel.

**The daily limit is a token bucket, not a midnight reset**
Groq's 429 said "Limit 200000, Used 197125, Requested 3557, try again in 4m54.6s". If the limit reset once a day, that would say hours. The arithmetic: 200,000 / 86,400 s = 2.31 tokens/s; we were short 3,557 − 2,875 = 682 tokens; 682 / 2.31 = 294.6 s = 4m54.6s exactly (the Qwen run matched too). So the bucket holds at most 200K and refills steadily. `--wait` sleeps for exactly that time and carries on, about one posting every 21 minutes once the bucket is empty. Waiting doesn't count against the 5 retries; only real failures do.

**Normalize in code, not in the model**
`src/normalize/pay.py` turns "$40/hour" into 83,200 a year with written assumptions (2,080 working hours a year). If the model did this, every answer would be a chance for an arithmetic mistake, and the assumptions would be invisible. Code is tested once and does the same thing every time. Currency is never converted, because rates change and the posting doesn't.

**Teacher model = upper bound on what we can learn (distillation)**
The training labels come from the Groq API model, so the fine-tuned model is learning to imitate it, including its mistakes. Measuring against hand-verified gold labels (not Groq's) is what tells us the truth.
