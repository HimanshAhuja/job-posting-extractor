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
