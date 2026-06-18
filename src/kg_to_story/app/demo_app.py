"""
Demo app — Narrative graph explorer across all pre-built results.
Loads output_ng.ttl + scores_all.txt from results/narrative_graphs/.
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

RESULTS_DIR = ROOT / "results" / "narrative_graphs"

MAX_EVENTS = 35
DEFAULT_N  = 10


def _discover() -> dict[str, list[dict]]:
    """Return {category_label: [{name, ttl, scores}, ...]} sorted alphabetically."""
    categories: dict[str, list[dict]] = {}
    for cat_dir in sorted(RESULTS_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        label = cat_dir.name.replace("_", " ").title()   # "event" -> "Event"
        entries = []
        for subject_dir in sorted(cat_dir.iterdir()):
            if not subject_dir.is_dir():
                continue
            ttl = subject_dir / "output_ng.ttl"
            if not ttl.exists():
                continue
            entries.append({
                "name":   subject_dir.name.replace("_", " ").title(),
                "ttl":    ttl,
                "scores": subject_dir / "scores_all.txt",
            })
        if entries:
            categories[label] = entries
    return categories


@st.cache_data
def load_scores(scores_path: str) -> dict:
    scores: dict = {}
    p = Path(scores_path)
    if not p.exists():
        return scores
    for line in p.read_text(encoding="utf-8").splitlines():
        if "|" not in line or "combined=" not in line:
            continue
        name_part, score_part = line.split("|", 1)
        name = re.sub(r"^\s*\d+\.\s*", "", name_part).strip()
        m = re.search(r"combined=([\d.]+)", score_part)
        if name and m:
            scores[name] = float(m.group(1))
    return scores


@st.cache_data
def load_all_events(ttl_path: str) -> list[str]:
    return get_events_from_ttl(ttl_path)


@st.cache_data
def top_n_events(ttl_path: str, scores_path: str, n: int) -> list[str]:
    scores  = load_scores(scores_path)
    all_ev  = set(load_all_events(ttl_path))
    ranked  = sorted(scores, key=scores.__getitem__, reverse=True)
    return [name for name in ranked if name in all_ev][:n]


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="ChronoGrapher Demo", layout="wide", page_icon="🌍")
st.title("ChronoGrapher — Narrative Graph Explorer")
st.caption("Pre-built graphs · no pipeline required")

all_data = _discover()

# ── Sidebar: category + subject selection ─────────────────────────────────────
with st.sidebar:
    st.header("Select subject")

    category = st.radio(
        "Category",
        list(all_data.keys()),
        label_visibility="collapsed",
    )

    entries     = all_data[category]
    entry_names = [e["name"] for e in entries]

    selected_name = st.selectbox(
        "Subject",
        entry_names,
        label_visibility="collapsed",
    )

selected = next(e for e in entries if e["name"] == selected_name)
ttl_path    = str(selected["ttl"])
scores_path = str(selected["scores"])

st.subheader(f"{category}: {selected_name}")

# Reset selected events when the subject changes
subject_key = ttl_path
if st.session_state.get("_subject_key") != subject_key:
    st.session_state["_subject_key"] = subject_key
    st.session_state["ms_events"] = top_n_events(ttl_path, scores_path, DEFAULT_N)


# ── Interactive panel (graph + selection list) ────────────────────────────────
@st.fragment
def _interactive_panel():
    st.subheader("Narrative Graph")
    st.caption("Gold = selected · Blue = unselected · Click a node to toggle")

    selected_ids = {name.replace(" ", "_") for name in st.session_state.ms_events}
    clicked_id   = render_narrative_graph_interactive(
        ttl_path, selected_ids, scores=load_scores(scores_path)
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
        st.rerun(scope="fragment")

    st.divider()

    # ── Selection panel ───────────────────────────────────────────────────────
    n_sel = len(st.session_state.ms_events)
    col_title, col_btns = st.columns([5, 2])
    col_title.subheader(f"Selected Events  ({n_sel} / {MAX_EVENTS} max)")

    with col_btns:
        c1, c2, c3 = st.columns(3)
        if c1.button("Top 35", use_container_width=True):
            st.session_state.ms_events = top_n_events(ttl_path, scores_path, MAX_EVENTS)
            st.rerun(scope="fragment")
        if c2.button("None", use_container_width=True):
            st.session_state.ms_events = []
            st.rerun(scope="fragment")
        if c3.button("Reset", use_container_width=True):
            st.session_state.ms_events = top_n_events(ttl_path, scores_path, DEFAULT_N)
            st.rerun(scope="fragment")

    st.multiselect(
        "Events",
        options=load_all_events(ttl_path),
        key="ms_events",
        max_selections=MAX_EVENTS,
        placeholder="Choose events… (max 35)",
        label_visibility="collapsed",
    )


_interactive_panel()

st.divider()

# ── Generate (outside the fragment) ──────────────────────────────────────────
st.subheader("Generate Story")

n = len(st.session_state.ms_events)
if st.button(
    "▶ Generate story",
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
