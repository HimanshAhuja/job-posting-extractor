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

**Teacher model = upper bound on what we can learn (distillation)**
The training labels come from the Groq API model, so the fine-tuned model is learning to imitate it, including its mistakes. Measuring against hand-verified gold labels (not Groq's) is what tells us the truth.
