# Dataset card: job posting extraction

Structured labels for 1,529 public job and internship postings, built to answer one question: does a small LoRA-fine-tuned model extract fields from postings better than prompting?

## Sources

| | |
|---|---|
| Where | Public job-board APIs: Greenhouse Job Board API (1,282 postings) and Lever Postings API (247) |
| Boards | 40 companies, listed in [`src/collect/boards.csv`](src/collect/boards.csv) |
| Collected | 2026-10-25, one snapshot per board ([`fetch_boards.py`](src/collect/fetch_boards.py)), 1 second between requests |
| Not used | LinkedIn and any site whose terms forbid automated collection |

These APIs are published so companies' postings can be shown on other sites. Posting text still belongs to each company. **The text is not redistributed:** `data/raw/` and `data/processed/` are gitignored. Only posting ids are committed ([`data/splits.csv`](data/splits.csv)), so the split can be reproduced. Postings expire, so a later fetch will not return all of them.

## Funnel

| Step | Postings | What happened |
|---|---|---|
| Raw API responses | 8,604 | everything the 40 boards returned |
| Pool ([`build_pool.py`](src/collect/build_pool.py)) | 8,203 | HTML turned into plain text ([`clean.py`](src/collect/clean.py)); non-English postings and stubs under 300 characters dropped; exact duplicates merged (same company, title and body, e.g. one role reposted per city; `n_copies` recorded) |
| Selected ([`select_split.py`](src/collect/select_split.py)) | 1,529 | at most 50 / 25 / 20 postings per company in train / val / test, internships kept first |

The median posting is about 6,200 characters.

## Splits: by company, not by posting

| Split | Postings | Companies | Internships | India-based |
|---|---|---|---|---|
| train | 1,264 | 27 | 121 | 173 |
| val | 117 | 5 | 8 | 28 |
| test | 148 | 8 | 37 | 24 |

Every posting from a company lands in the same split. One company's postings share templates and boilerplate, so a random split would let the model memorise a template in train and be "tested" on it. Companies were grouped (India-heavy, intern-heavy, other) and dealt into splits with a fixed seed (`SEED = 42`, chosen before any results and never re-rolled).

## Labels

The schema is [`src/schema.py`](src/schema.py): 18 fields, including company, role, job type, work mode, locations, skills, start, deadline, duration, pay (min, max, currency, period, plus the original text) and eligibility. Every label is validated with Pydantic. The rules are in [`LABELING_GUIDE.md`](LABELING_GUIDE.md); it is frozen, and new edge cases go in [`DECISIONS.md`](DECISIONS.md).

| Split | Labelled by | Why |
|---|---|---|
| train, val | `qwen/qwen3.8-27b` on Groq (the teacher) | Won 5 of 7 real disagreements in a pilot against gpt-oss-120b; faster; no hidden reasoning tokens |
| test | `openai/gpt-oss-120b` on Groq, then hand-checked | A *different* model, so hand-checking isn't anchored on the teacher the fine-tuned model imitates |
| **gold** | **50 test postings checked by hand** | A stratified random sample with the same share of internships (13) and India postings (8) as the full test set |

How the labels are made:
- **Temperature 0.**
- **Retries:** an invalid answer gets one retry, with the validation error shown to the model.
- **Fingerprints:** each label stores a hash of the posting text and of the prompt (which includes the guide). If either changes, the label is marked stale and redone.
- **Pay:** pay is copied as stated in the posting. Yearly and monthly figures are computed afterwards by tested code ([`src/normalize/pay.py`](src/normalize/pay.py)), and currency is never converted.

## Known limitations

- **Mostly US tech companies.** India-based postings are about 15% of the data, and internships about 11%.
- **Training labels come from a model** and inherit its mistakes. Only the gold set is checked by hand, and scores are reported against it.
- **The gold set is small (50 postings)**, so results are reported with confidence intervals. All 148 test postings are also scored against the gpt-oss labels as a secondary, clearly labelled check.
- **Everything was collected on a single day (2026-10-25)**, so seasonal postings, such as summer internships, depend on what was open then.
- **Eligibility fields** (batches, GPA, fees) are rare in these postings and are reported separately.
