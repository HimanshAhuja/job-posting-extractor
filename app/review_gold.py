"""Hand-check the gold sample of the test set: the posting on the left, its pre-label as an editable form on the right.

Run from the repo root, with .venv active:
    streamlit run app/review_gold.py

Each save is validated against the schema and appended to data/gold/test_gold.jsonl.
Read the posting first, then the form: the pre-label is a suggestion, not the answer.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `src` imports work under streamlit

import streamlit as st

from src.label import gold as g
from src.label.compare_labels import load_fresh_labels
from src.label.label_groq import fingerprint, load_selected
from src.label.prompt import GUIDE_PATH, system_prompt

st.set_page_config(page_title="Gold check", layout="wide")


@st.cache_data
def load_test():
    postings = g.pick_gold(load_selected())  # the fixed 50, not all 148
    prompt_sha1 = fingerprint(system_prompt())
    wanted = {p["id"]: (fingerprint(p["text"]), prompt_sha1) for p in postings}
    prelabels, _ = load_fresh_labels(g.PRELABEL_PATH, wanted)
    return postings, prelabels


postings, prelabels = load_test()
by_id = {p["id"]: p for p in postings}
ids = list(by_id)
gold = g.load_gold()
done = g.checked_ids(gold, postings)

# Pick the posting to show. "goto" is set by a save; it must be applied before the selectbox exists.
if "goto" in st.session_state:
    st.session_state.current = st.session_state.pop("goto")
if "current" not in st.session_state:
    st.session_state.current = next((i for i in ids if i not in done), ids[0])

st.sidebar.progress(len(done) / len(ids), text=f"Checked {len(done)} / {len(ids)}")
current = st.sidebar.selectbox("Posting", ids, key="current",
                               format_func=lambda i: f"{'✓' if i in done else '·'} {i}")
if "last_saved" in st.session_state:
    saved_id, changed = st.session_state.last_saved
    st.sidebar.success(f"Saved {saved_id}\n\nChanged: {', '.join(changed) or 'nothing'}")

posting = by_id[current]
prelabel = prelabels.get(current, g.empty_label())
start = gold[current]["label"] if current in gold else prelabel  # re-opening shows what you saved
form0 = g.label_to_form(start)

left, right = st.columns([3, 2])
with left:
    st.subheader(posting["title"])
    st.caption(f"{posting['company']} · {posting['url']}")
    with st.container(height=760):
        # st.code shows the text exactly as the model saw it (markdown would turn "#LI-Hybrid" into a heading)
        st.code(posting["text"], language=None, wrap_lines=True)

with right:
    if current in gold:
        st.info("Already checked. Saving again replaces your earlier answer.")
    elif current not in prelabels:
        st.warning("No pre-label for this posting: starting from an empty form.")
    with st.expander("Labelling guide"):
        st.markdown(GUIDE_PATH.read_text(encoding="utf-8"))

    with st.form(key=f"form-{current}"):
        values = {}
        for field in g.FIELDS:
            key = f"{current}:{field}"
            if field in g.CHOICES:
                options = g.CHOICES[field]
                values[field] = st.selectbox(field, options, index=options.index(form0[field]), key=key,
                                             format_func=lambda option: option or "null")
            elif field in g.LIST_FIELDS:
                values[field] = st.text_area(f"{field} (one per line)", form0[field], key=key, height=100)
            else:
                values[field] = st.text_input(field, form0[field], key=key,
                                              placeholder="null" if field != "eligible_batches" else "e.g. 2027, 2028")
        note = st.text_input("note (optional: a tricky case worth adding to DECISIONS.md)",
                             (gold.get(current) or {}).get("note") or "", key=f"{current}:note")
        submitted = st.form_submit_button("Save and go to next", type="primary")

    if submitted:
        try:
            label = g.form_to_label(values)
        except ValueError as err:
            st.error(f"Not saved:\n\n{err}")
        else:
            row = g.save_gold(posting, label, prelabel, note)
            position = ids.index(current)
            after = ids[position + 1:] + ids[:position]  # wrap around to earlier ones you skipped
            st.session_state.goto = next((i for i in after if i not in done), current)
            st.session_state.last_saved = (current, row["changed_from_prelabel"])
            st.rerun()
