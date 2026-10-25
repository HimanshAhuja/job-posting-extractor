# Labelling guide

How to fill each field of `src/schema.py` (schema version 1). Groq's labelling prompt and my hand-verification both follow this file, so the two sets of labels mean the same thing. When an ambiguous case comes up, decide a rule once and add it here.

## General
- Use only what the posting says. No outside knowledge, no guessing.
- Not stated → `null` (single values) or `[]` (lists). Never `""`.

## Pay (five fields)
| Field | Meaning |
|---|---|
| `pay_min` | lowest amount, shorthand expanded (`15K` → 15000, `6 LPA` → 600000) |
| `pay_max` | highest amount; a single amount sets `pay_min = pay_max` |
| `pay_currency` | ISO code: `INR`, `USD`, `EUR`, `GBP`… |
| `pay_period` | `hour`, `day`, `week`, `month` or `year`, as stated |
| `pay_raw` | the pay text copied from the posting |

- Pay mentioned without an amount ("Competitive salary") → `pay_raw` only, the other four `null`.
- LPA = lakhs per annum; 1 lakh = 100,000. "6–7 LPA" → 600000, 700000, `INR`, `year`.
- Never convert currencies or periods. Code does that later.

## Work mode and locations
- `work_mode` has one value. **If fully remote work is allowed, use `remote`**, even when an office is also offered ("Bengaluru or Remote" → `remote`).
- `hybrid` only when the same person splits time between office and home ("3 days in office").
- `locations` lists the places named, as written in the posting ("Bengaluru or Remote" → `["Bengaluru"]`). The word "Remote" is not a location.
