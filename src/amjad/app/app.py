import os
import sys
import json
import threading
import queue
import contextlib
from pathlib import Path

import streamlit as st

# Ensure project root is on sys.path so `src.*` imports work
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.run_pipeline import run_pipeline_direct  # noqa: E402
from graph_view import render_narrative_graph  # noqa: E402
from manual_pipeline import (  # noqa: E402
    run_pipeline_until_graph,
    get_events_from_ttl,
    build_timeline_from_selection,
    generate_story_manual,
)

TO_TEST = ROOT / "sample-data" / "to_test"

CATEGORY_LABELS = {
    ("events", "long_known"):  "Events — Long Known",
    ("events", "short_known"): "Events — Short Known",
    ("events", "unknown"):     "Events — Unknown",
    ("persons", "known"):      "Persons — Known",
    ("persons", "unknown"):    "Persons — Unknown",
}

CATEGORY_ORDER = list(CATEGORY_LABELS.values())


def load_configs():
    """Return an ordered dict: category_label -> list of event dicts."""
    grouped = {label: [] for label in CATEGORY_ORDER}

    for config_file in sorted(TO_TEST.rglob("*_config_wikidata.json")):
        rel = config_file.relative_to(TO_TEST)
        parts = rel.parts  # e.g. ("events", "short_known", "foo.json")

        if len(parts) < 3:
            continue

        key = (parts[0], parts[1])
        label = CATEGORY_LABELS.get(key)
        if label is None:
            continue

        with open(config_file, encoding="utf-8") as f:
            config = json.load(f)

        name = config.get("start_name") or (
            config_file.stem
            .replace("_config_wikidata", "")
            .replace("_", " ")
            .title()
        )

        grouped[label].append({
            "name": name,
            "path": str(config_file),
            "config": config,
        })

    return grouped


# ── Output capture helper ──────────────────────────────────────────────────────

class _QueueWriter:
    """Minimal text-stream that forwards every write() to a queue."""
    encoding = "utf-8"

    def __init__(self, q: queue.Queue):
        self._q = q

    def write(self, s: str):
        if s:
            self._q.put(str(s))
        return len(s) if s else 0

    def flush(self):
        pass

    def isatty(self):
        return False


def _run_pipeline_thread(config_path: str, out_q: queue.Queue, result: dict):
    writer = _QueueWriter(out_q)
    try:
        with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
            target_folder, timeline_file = run_pipeline_direct(config_path)
        result["target_folder"] = target_folder
        result["success"] = True
    except Exception:
        import traceback
        out_q.put(f"\n[ERROR]\n{traceback.format_exc()}\n")
        result["success"] = False
    finally:
        out_q.put(None)


def _run_partial_thread(config_path: str, out_q: queue.Queue, result: dict):
    writer = _QueueWriter(out_q)
    try:
        with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
            target_folder, output_ng, main_event = run_pipeline_until_graph(config_path)
        result["target_folder"] = target_folder
        result["output_ng"] = output_ng
        result["main_event"] = main_event
        result["success"] = True
    except Exception:
        import traceback
        out_q.put(f"\n[ERROR]\n{traceback.format_exc()}\n")
        result["success"] = False
    finally:
        out_q.put(None)


def _run_story_thread(
    ttl_path: str, selected_names: list,
    target_folder: str, main_event: str,
    out_q: queue.Queue, result: dict,
):
    writer = _QueueWriter(out_q)
    try:
        with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
            timeline_file = os.path.join(target_folder, "event_timeline_manual.txt")
            build_timeline_from_selection(ttl_path, selected_names, timeline_file)
            story, story_file = generate_story_manual(timeline_file, main_event)
        result["story"] = story
        result["story_file"] = story_file
        result["success"] = True
    except Exception:
        import traceback
        out_q.put(f"\n[ERROR]\n{traceback.format_exc()}\n")
        result["success"] = False
    finally:
        out_q.put(None)


def _stream(out_q: queue.Queue, placeholder):
    """Read queue until sentinel, updating placeholder each chunk. Returns accumulated text."""
    text = ""
    while True:
        chunk = out_q.get()
        if chunk is None:
            break
        text += chunk
        placeholder.code(text[-8000:], language="bash")
    return text


# ── Session state defaults ─────────────────────────────────────────────────────
for k, v in [
    # normal mode
    ("running", False), ("output", ""), ("finished", False), ("success", None),
    # manual mode
    ("m_running", False), ("m_output", ""),
    ("m_partial_done", False), ("m_output_ng", ""), ("m_main_event", ""), ("m_target_folder", ""),
    ("m_story_running", False), ("m_story", ""), ("m_story_done", False),
]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="ChronoGrapher", layout="wide", page_icon="🗓️")
st.title("🗓️ ChronoGrapher — Event Narrative Explorer")

all_events = load_configs()

# ── Sidebar: category filter ───────────────────────────────────────────────────
with st.sidebar:
    st.header("Category")
    categories_with_counts = [
        f"{label}  ({len(all_events[label])})" for label in CATEGORY_ORDER
    ]
    selected_cat_idx = st.radio(
        "Select category",
        range(len(CATEGORY_ORDER)),
        format_func=lambda i: categories_with_counts[i],
        label_visibility="collapsed",
    )
    selected_category = CATEGORY_ORDER[selected_cat_idx]

# ── Main: event list ───────────────────────────────────────────────────────────
st.subheader(f"Events in: {selected_category}")

events = all_events[selected_category]
event_names = [e["name"] for e in events]

selected_idx = st.radio(
    "Choose an event",
    range(len(event_names)),
    format_func=lambda i: event_names[i],
    label_visibility="collapsed",
)
selected = events[selected_idx]
cfg = selected["config"]

# ── Event details ──────────────────────────────────────────────────────────────
with st.expander("Event details", expanded=True):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Name:** {selected['name']}")
        st.markdown(f"**Start date:** {cfg.get('start_date', '—')}")
        st.markdown(f"**End date:** {cfg.get('end_date', '—')}")
        st.markdown(f"**Iterations:** {cfg.get('iterations', '—')}")
    with c2:
        st.markdown(f"**Type:** {cfg.get('type', '—').title()}")
        st.markdown(f"**Ranking:** `{cfg.get('type_ranking', '—')}`")
        rel_path = Path(selected["path"]).relative_to(ROOT)
        st.markdown(f"**Config:** `{rel_path}`")

st.divider()

# ── DEV: quick graph preview (bypass pipeline) ─────────────────────────────────
_DEV_TTL = "/home/kallas/project/graph_search_framework/experiments/event/world_war_1/2/output_ng.ttl"
if st.checkbox("🛠 Preview graph from test TTL (dev only)"):
    st.subheader("Narrative Graph (test)")
    render_narrative_graph(_DEV_TTL)
    st.stop()

# ── Mode selector ──────────────────────────────────────────────────────────────
manual_mode = st.checkbox("Manually select events", value=False)

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# NORMAL MODE
# ══════════════════════════════════════════════════════════════════════════════
if not manual_mode:

    run_clicked = st.button(
        "▶ Run Pipeline",
        type="primary",
        disabled=st.session_state.running,
    )

    if run_clicked:
        st.session_state.running = True
        st.session_state.finished = False
        st.session_state.success = None
        st.session_state.output = ""

        out_q: queue.Queue = queue.Queue()
        result: dict = {}

        thread = threading.Thread(
            target=_run_pipeline_thread,
            args=(selected["path"], out_q, result),
            daemon=True,
        )
        thread.start()
        st.session_state.output = _stream(out_q, st.empty())
        thread.join()

        st.session_state.running = False
        st.session_state.finished = True
        st.session_state.success = result.get("success", False)
        if result.get("target_folder"):
            st.session_state.target_folder = result["target_folder"]
        st.rerun()

    if st.session_state.finished:
        if st.session_state.success:
            folder = st.session_state.get("target_folder", "")
            st.success(f"Pipeline completed. Output: `{folder}`")
            st.subheader("Narrative Graph")
            render_narrative_graph(os.path.join(folder, "output_ng.ttl"))
        else:
            st.error("Pipeline finished with errors — see output below.")

    if st.session_state.output:
        with st.expander("Pipeline log", expanded=not st.session_state.success):
            st.code(st.session_state.output, language="bash")

# ══════════════════════════════════════════════════════════════════════════════
# MANUAL MODE
# ══════════════════════════════════════════════════════════════════════════════
else:

    # ── Step 1 header + buttons ──────────────────────────────────────────────
    st.markdown("**Step 1 — Build the narrative graph**")
    col_run, col_reset, _ = st.columns([1.4, 1, 6])

    run_partial = col_run.button(
        "▶ Run until graph",
        type="primary",
        disabled=st.session_state.m_running or st.session_state.m_partial_done,
    )
    reset_clicked = col_reset.button("↺ Reset")

    if reset_clicked:
        for k, v in [
            ("m_running", False), ("m_output", ""),
            ("m_partial_done", False), ("m_output_ng", ""), ("m_main_event", ""), ("m_target_folder", ""),
            ("m_story_running", False), ("m_story", ""), ("m_story_done", False),
        ]:
            st.session_state[k] = v
        st.rerun()

    if run_partial:
        st.session_state.m_running = True
        st.session_state.m_output = ""

        out_q: queue.Queue = queue.Queue()
        result: dict = {}

        thread = threading.Thread(
            target=_run_partial_thread,
            args=(selected["path"], out_q, result),
            daemon=True,
        )
        thread.start()
        st.session_state.m_output = _stream(out_q, st.empty())
        thread.join()

        st.session_state.m_running = False
        if result.get("success"):
            st.session_state.m_partial_done = True
            st.session_state.m_output_ng = result["output_ng"]
            st.session_state.m_main_event = result["main_event"]
            st.session_state.m_target_folder = result["target_folder"]
        st.rerun()

    if st.session_state.m_output:
        with st.expander("Pipeline log", expanded=not st.session_state.m_partial_done):
            st.code(st.session_state.m_output, language="bash")

    # ── Graph + event selection ──────────────────────────────────────────────
    if st.session_state.m_partial_done:
        output_ng   = st.session_state.m_output_ng
        main_event  = st.session_state.m_main_event
        target_folder = st.session_state.m_target_folder

        st.success(f"Graph ready: `{output_ng}`")
        st.subheader("Narrative Graph")
        render_narrative_graph(output_ng)

        st.markdown("**Step 2 — Select events for your story**")
        all_event_names = get_events_from_ttl(output_ng)
        chosen = st.multiselect(
            "Events",
            options=all_event_names,
            placeholder="Choose events…",
            label_visibility="collapsed",
        )

        if chosen:
            gen_clicked = st.button(
                f"▶ Generate story  ({len(chosen)} events selected)",
                type="primary",
                disabled=st.session_state.m_story_running,
            )

            if gen_clicked:
                st.session_state.m_story_running = True

                out_q: queue.Queue = queue.Queue()
                result: dict = {}

                thread = threading.Thread(
                    target=_run_story_thread,
                    args=(output_ng, chosen, target_folder, main_event, out_q, result),
                    daemon=True,
                )
                thread.start()
                _stream(out_q, st.empty())
                thread.join()

                st.session_state.m_story_running = False
                if result.get("success"):
                    st.session_state.m_story = result["story"]
                    st.session_state.m_story_done = True
                st.rerun()

    # ── Story output ─────────────────────────────────────────────────────────
    if st.session_state.m_story_done and st.session_state.m_story:
        st.subheader("Generated Story")
        st.write(st.session_state.m_story)
