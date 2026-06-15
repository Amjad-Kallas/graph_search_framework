"""
Demo app — World War I narrative graph explorer.
Uses the pre-built output_ng.ttl from experiments/world_war_1/.
No pipeline execution required.
"""
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent.parent
APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(APP_DIR))

from graph_view import render_narrative_graph_interactive  # noqa: E402
from manual_pipeline import get_events_from_ttl            # noqa: E402

EXPERIMENT_DIR = ROOT / "experiments" / "world_war_1"
TTL_PATH       = str(EXPERIMENT_DIR / "output_ng.ttl")
SCORES_FILE    = EXPERIMENT_DIR / "scores_all.txt"

MAX_EVENTS = 35
DEFAULT_N  = 10


@st.cache_data
def load_scores() -> dict:
    scores: dict = {}
    if not SCORES_FILE.exists():
        return scores
    for line in SCORES_FILE.read_text(encoding="utf-8").splitlines():
        if "|" not in line or "combined=" not in line:
            continue
        name_part, score_part = line.split("|", 1)
        name = re.sub(r"^\s*\d+\.\s*", "", name_part).strip()
        m = re.search(r"combined=([\d.]+)", score_part)
        if name and m:
            scores[name] = float(m.group(1))
    return scores


@st.cache_data
def load_all_events() -> list[str]:
    return get_events_from_ttl(TTL_PATH)


@st.cache_data
def top_n_events(n: int) -> list[str]:
    scores = load_scores()
    all_ev = set(load_all_events())
    ranked = sorted(scores, key=scores.__getitem__, reverse=True)
    return [name for name in ranked if name in all_ev][:n]


# ── Page config (runs once, never inside a fragment) ─────────────────────────
st.set_page_config(page_title="WWI Narrative Graph Demo", layout="wide", page_icon="🌍")
st.title("World War I — Narrative Graph Explorer")
st.caption("Pre-built graph · no pipeline required")

if "ms_events" not in st.session_state:
    st.session_state.ms_events = top_n_events(DEFAULT_N)


# ── Interactive panel (graph + selection list) ────────────────────────────────
# @st.fragment limits reruns to this block only — the rest of the page
# (title, generate section) is untouched when a node is clicked.
@st.fragment
def _interactive_panel():
    st.subheader("Narrative Graph")
    st.caption("Gold = selected · Blue = unselected · Click a node to toggle")

    selected_ids = {name.replace(" ", "_") for name in st.session_state.ms_events}
    clicked_id   = render_narrative_graph_interactive(
        TTL_PATH, selected_ids, scores=load_scores()
    )

    if clicked_id:
        clicked_name = unquote(clicked_id).replace("_", " ")
        current = list(st.session_state.ms_events)
        if clicked_name in current:
            current.remove(clicked_name)
        elif len(current) < MAX_EVENTS:
            current.append(clicked_name)
        else:
            st.toast(f"Maximum {MAX_EVENTS} events — deselect one first.", icon="⚠️")
        st.session_state.ms_events = current
        st.rerun(scope="fragment")   # only this panel rerenders, not the full page

    st.divider()

    # ── Selection panel ───────────────────────────────────────────────────────
    n_sel = len(st.session_state.ms_events)
    col_title, col_btns = st.columns([5, 2])
    col_title.subheader(f"Selected Events  ({n_sel} / {MAX_EVENTS} max)")

    with col_btns:
        c1, c2, c3 = st.columns(3)
        if c1.button("Top 35", use_container_width=True):
            st.session_state.ms_events = top_n_events(MAX_EVENTS)
            st.rerun(scope="fragment")
        if c2.button("None", use_container_width=True):
            st.session_state.ms_events = []
            st.rerun(scope="fragment")
        if c3.button("Reset", use_container_width=True):
            st.session_state.ms_events = top_n_events(DEFAULT_N)
            st.rerun(scope="fragment")

    st.multiselect(
        "Events",
        options=load_all_events(),
        key="ms_events",
        max_selections=MAX_EVENTS,
        placeholder="Choose events… (max 35)",
        label_visibility="collapsed",
    )


_interactive_panel()

st.divider()

# ── Generate (outside the fragment — only reruns on full page events) ─────────
st.subheader("Generate Story")

n = len(st.session_state.ms_events)
if st.button(
    f"▶ Generate story",
    type="primary",
    disabled=n == 0,
):
    st.info(
        f"**Demo mode** — story generation is disabled here.  \n"
        f"The full pipeline would use these {n} events to generate a ~700-word narrative."
    )
    with st.expander("Selected events"):
        for ev in sorted(st.session_state.ms_events):
            st.markdown(f"- {ev}")
