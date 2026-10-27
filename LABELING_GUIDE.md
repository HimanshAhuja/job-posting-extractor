# Labelling guide

How to fill each field of `src/schema.py` (schema version 1). Groq's labelling prompt and my hand-verification both follow this file, so the two sets of labels mean the same thing. When an ambiguous case comes up, decide a rule once and add it here.

## General
- Use only what the posting says. No outside knowledge, no guessing.
- Not stated → `null` (single values) or `[]` (lists). Never `""`.

## Who and what
- `company`: the hiring company's name as written in the posting, without division or team labels ("InMobi (Corporate)" → "InMobi").
- `role`: the job title copied exactly from the first line. Don't expand abbreviations or tidy it ("HRBP_Bangalore" stays "HRBP_Bangalore").
- `job_type`: `internship` for intern / co-op / apprentice roles; `contract` for contract or temporary roles; `part_time` or `full_time` only when the posting says so about this role. Otherwise `null`.
  - Generic company text doesn't count: a benefits heading such as "How we support full-time employees" does not make the role `full_time`.
- `skills`: named technologies only (programming languages, frameworks, libraries, databases, cloud platforms, tools, protocols), e.g. "Python", "SQL", "Kubernetes", "AWS", "MDM". Copy as written, no duplicates. **Not** activities, domains or soft skills ("customer service", "documentation", "technical leadership", "software engineering") and not spoken languages ("English").

## Pay (five fields)
| Field | Meaning |
|---|---|
| `pay_min` | lowest amount, shorthand expanded (`15K` → 15000, `6 LPA` → 600000) |
| `pay_max` | highest amount; a single amount sets `pay_min = pay_max` |
| `pay_currency` | ISO code: `INR`, `USD`, `EUR`, `GBP`… |
| `pay_period` | `hour`, `day`, `week`, `month` or `year`, as stated |
| `pay_raw` | the pay text copied from the posting (at most ~300 characters) |

- Pay mentioned without an amount ("Competitive salary") → `pay_raw` only, the other four `null`.
- `pay_raw` is only text about this job's pay. General talk about wealth, growth, benefits or perks is not pay → `null`.
- LPA = lakhs per annum; 1 lakh = 100,000. "6–7 LPA" → 600000, 700000, `INR`, `year`.
- Base pay only: ignore bonus, equity and benefits amounts.
- OTE / "on-target earnings" includes commission, so it is not base pay → `pay_raw` only, the other four `null`. If a separate base salary is also stated, use that.
- Several ranges (e.g. one per location zone) → `pay_min` = lowest, `pay_max` = highest across them. If they are in different currencies, use only the first currency listed.
- Never convert currencies or periods. Code does that later.

## Work mode and locations
- `work_mode` has one value. **If fully remote work is allowed, use `remote`**, even when an office is also offered ("Bengaluru or Remote" → `remote`).
- `hybrid` only when the same person splits time between office and home ("3 days in office").
- Company-wide policy text ("many teams offer hybrid options", "some roles allow remote") does not decide this role's work mode. Use only statements about this role; if there are none, `null`.
- Recruiter tags on the posting count as a statement about this role: `#LI-Hybrid` → `hybrid`, `#LI-Remote` → `remote`, `#LI-Onsite` → `onsite` (also written `#LI_Hybrid`, any case). Other `#LI-` tags (e.g. `#LI-AG`) are recruiter initials; ignore them.
- `locations` lists the places named, one entry per place, as written ("Bengaluru or Remote" → `["Bengaluru"]`, "Remote - Bengaluru, India" → `["Bengaluru, India"]`). Don't split a city from its country. The word "Remote" is not a location.

## Dates and duration
- `start`: only when a month and year are both stated ("June 2027" → `2027-06`). "Summer 2027" → `null`. Several possible start months ("beginning in February, March or June 2027") → `null`: a list of options isn't a start date.
- `deadline`: only when a full date with year is stated. "Apply by Nov 30" (no year) → `null`.
- `duration_value` / `duration_unit`: as stated ("12-week internship" → 12, `week`; "6 months" → 6, `month`).

## Eligibility
- `eligible_batches`: graduation years stated as eligible ("2027 and 2028 batch" → [2027, 2028]).
- `min_gpa`: the minimum GPA/CGPA number as stated, on its own scale ("3.0 GPA" → 3.0, "7.5 CGPA" → 7.5).
- `fee_required`: `true` only if applicants must pay a fee; `false` only if the posting says there is no fee; otherwise `null`. A standard anti-scam line ("we'll never ask you to pay a fee") counts as saying there is no fee → `false`.
