import os
import math
import hashlib
import base64
import tempfile
from datetime import date as _date
from urllib.parse import unquote

import altair as alt
import networkx as nx
from rdflib import Graph, Namespace, RDF, RDFS
from pyvis.network import Network
import streamlit as st

SEM = Namespace("http://semanticweb.cs.vu.nl/2009/11/sem/")


def _label(uri: str) -> str:
    return uri.split("/")[-1].replace("_", " ")


def _node_id(uri: str) -> str:
    """Short stable ID: URI fragment, e.g. 'Battle_of_Jutland'."""
    return str(uri).split("/")[-1]


def render_narrative_graph(ttl_path: str, height: int = 700):
    """Parse output_ng.ttl and embed an interactive PyVis graph in the Streamlit page."""

    if not os.path.exists(ttl_path):
        st.warning(f"Narrative graph not found: `{ttl_path}`")
        return

    g = Graph()
    g.parse(ttl_path, format="turtle")

    events = set(g.subjects(RDF.type, SEM.Event))
    if not events:
        st.info("No events found in the narrative graph.")
        return

    net = Network(
        height=f"{height}px",
        width="100%",
        directed=False,
        bgcolor="#0e1117",   # matches Streamlit dark background
        font_color="#fafafa",
    )
    net.set_options("""{
      "physics": {
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {
          "gravitationalConstant": -60,
          "centralGravity": 0.01,
          "springLength": 140,
          "springConstant": 0.06
        },
        "stabilization": { "iterations": 200 }
      },
      "interaction": {
        "hover": true,
        "navigationButtons": true,
        "tooltipDelay": 100
      },
      "edges": { "smooth": { "type": "continuous" } }
    }""")

    # ── Controls ───────────────────────────────────────────────────────────────
    col1, col2, _ = st.columns([1, 1, 6])
    show_actors = col1.checkbox("Show actors", value=False, key=f"show_actors_{ttl_path}")
    show_places = col2.checkbox("Show places", value=False, key=f"show_places_{ttl_path}")

    # ── Build nodes ────────────────────────────────────────────────────────────
    added_nodes: set = set()

    for ev in events:
        ev_id = str(ev)
        ev_label = _label(ev_id)
        date = g.value(ev, SEM.hasTimeStamp)
        comment = g.value(ev, RDFS.comment)

        tooltip = f"<b>{ev_label}</b>"
        if date:
            tooltip += f"<br/>📅 {date}"
        if comment:
            short = str(comment)[:250]
            if len(str(comment)) > 250:
                short += "…"
            tooltip += f"<br/><br/>{short}"

        net.add_node(ev_id, label=ev_label, title=tooltip,
                     color={"background": "#4C9BE8", "border": "#1a5fa8"},
                     size=22, shape="dot", font={"size": 13})
        added_nodes.add(ev_id)

    # ── subEventOf edges (always shown — primary event structure) ──────────────
    for ev in events:
        ev_id = str(ev)
        for parent in g.objects(ev, SEM.subEventOf):
            p_id = str(parent)
            if p_id in added_nodes:  # only draw if parent is itself an event node
                net.add_edge(ev_id, p_id, color="#aaaaaa", width=2, title="subEventOf")

    for ev in events:
        ev_id = str(ev)

        if show_actors:
            for actor in g.objects(ev, SEM.hasActor):
                a_id = str(actor)
                a_label = _label(a_id)
                if a_id not in added_nodes:
                    net.add_node(a_id, label=a_label, title=f"<b>{a_label}</b>",
                                 color={"background": "#50C878", "border": "#1a7a40"},
                                 size=14, shape="triangle", font={"size": 11})
                    added_nodes.add(a_id)
                net.add_edge(ev_id, a_id, color="#50C878", width=1.5, title="hasActor")

        if show_places:
            for place in g.objects(ev, SEM.hasPlace):
                p_id = str(place)
                p_label = _label(p_id)
                if p_id not in added_nodes:
                    net.add_node(p_id, label=p_label, title=f"<b>{p_label}</b>",
                                 color={"background": "#FF8C42", "border": "#b85a10"},
                                 size=14, shape="square", font={"size": 11})
                    added_nodes.add(p_id)
                net.add_edge(ev_id, p_id, color="#FF8C42", width=1.5, title="hasPlace")

    # ── Render ─────────────────────────────────────────────────────────────────
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as tmp:
        net.save_graph(tmp.name)
        html = open(tmp.name, encoding="utf-8").read()
    os.unlink(tmp.name)

    b64 = base64.b64encode(html.encode("utf-8")).decode("utf-8")

    legend = "🔵 **Event**"
    if show_actors:
        legend += " &nbsp;&nbsp; 🟢 **Actor**"
    if show_places:
        legend += " &nbsp;&nbsp; 🟠 **Place**"
    st.markdown(legend)
    st.iframe(src=f"data:text/html;base64,{b64}", height=height + 10)


def _timeline_layout(G: nx.Graph, date_map: dict) -> dict:
    """X = normalized date, Y = hash-based deterministic spread."""
    parsed: dict = {}
    for nid, ds in date_map.items():
        try:
            parts = str(ds).split("-")
            parsed[nid] = _date(int(parts[0]), int(parts[1]), int(parts[2]))
        except Exception:
            pass

    if not parsed:
        return nx.spring_layout(G, seed=42)

    min_d = min(parsed.values())
    max_d = max(parsed.values())
    span = max(1, (max_d - min_d).days)

    pos: dict = {}
    for nid in G.nodes():
        x = (parsed[nid] - min_d).days / span * 2 - 1 if nid in parsed else 0.0
        h = int(hashlib.md5(nid.encode()).hexdigest()[:8], 16)
        y = (h % 200 - 100) / 100 * 0.9   # deterministic spread in [-0.9, 0.9]
        pos[nid] = (float(x), float(y))
    return pos


def _relevance_layout(G: nx.Graph, scores: dict) -> dict:
    """Golden-angle spiral: rank-1 (highest score) → center, rank-N → outer edge."""
    nids = list(G.nodes())
    n = len(nids)
    if n == 0:
        return {}
    sorted_nids = sorted(
        nids,
        key=lambda nid: scores.get(unquote(nid).replace("_", " "), 0.0),
        reverse=True,
    )
    golden = math.pi * (3 - math.sqrt(5))   # ≈ 137.5°
    pos: dict = {}
    for i, nid in enumerate(sorted_nids):
        radius = (i / n) * 0.95
        angle  = i * golden
        pos[nid] = (radius * math.cos(angle), radius * math.sin(angle))
    return pos


def _timeline_relevance_layout(G: nx.Graph, date_map: dict, scores: dict) -> dict:
    """X = decimal year, Y = relevance score (0–1). Undated nodes sit at x=year_min-0.3."""
    pos: dict = {}
    x_vals = []

    for nid in G.nodes():
        ds = date_map.get(nid)
        if ds:
            try:
                parts = str(ds).split("-")
                year  = int(parts[0])
                month = int(parts[1]) if len(parts) > 1 else 6
                day   = int(parts[2]) if len(parts) > 2 else 15
                x = year + (month - 1) / 12 + (day - 1) / 365
                x_vals.append(x)
            except Exception:
                x = None
        else:
            x = None
        score = scores.get(unquote(nid).replace("_", " "), 0.0)
        pos[nid] = (x, float(score))   # x may still be None

    # Undated nodes: place just left of the earliest dated event
    fallback_x = (min(x_vals) - 0.4) if x_vals else 1913.6
    for nid in pos:
        x, y = pos[nid]
        if x is None:
            pos[nid] = (float(fallback_x), y)

    return pos


def render_narrative_graph_interactive(
    ttl_path: str,
    selected_ids: set,
    height: int = 700,
    scores: dict | None = None,
) -> str | None:
    """
    Interactive graph using Altair + networkx layout.
    Works through VSCode tunnels (no separate component server needed).
    Event nodes are blue; selected ones are gold.
    Clicking a node returns its ID (URI fragment), or None.
    """
    if not os.path.exists(ttl_path):
        st.warning(f"Narrative graph not found: `{ttl_path}`")
        return None

    g = Graph()
    g.parse(ttl_path, format="turtle")

    events = set(g.subjects(RDF.type, SEM.Event))
    if not events:
        st.info("No events found in the narrative graph.")
        return None

    # ── Controls ───────────────────────────────────────────────────────────────
    col_layout, col_dates, _ = st.columns([4, 1, 3])

    with col_layout:
        layout_opts = ["Force-directed", "Timeline"]
        if scores:
            layout_opts += ["Relevance", "Timeline + Relevance"]
        layout_mode = st.radio(
            "Layout",
            layout_opts,
            horizontal=True,
            key=f"layout_{ttl_path}",
        )

    show_dates = col_dates.checkbox("Show dates", value=False, key=f"show_dates_{ttl_path}")

    # ── Build networkx graph ──────────────────────────────────────────────────
    G = nx.Graph()
    event_nids: set = set()
    date_map: dict = {}

    for ev in events:
        nid = _node_id(str(ev))
        label = unquote(nid).replace("_", " ")
        date = g.value(ev, SEM.hasTimeStamp)
        comment = g.value(ev, RDFS.comment)
        tip = label
        if date:
            date_str = str(date)
            tip += f" ({date_str})"
            date_map[nid] = date_str
        if comment:
            tip += f" — {str(comment)[:150]}…"
        G.add_node(nid, label=label, tooltip=tip)
        event_nids.add(nid)

    for ev in events:
        nid = _node_id(str(ev))
        for parent in g.objects(ev, SEM.subEventOf):
            pid = _node_id(str(parent))
            if pid in event_nids:
                G.add_edge(nid, pid)

    hub_nid = max(G.nodes(), key=lambda n: G.degree(n)) if G.nodes() else None

    # ── Compute positions ─────────────────────────────────────────────────────
    if layout_mode == "Timeline":
        pos = _timeline_layout(G, date_map)
        show_edges = False
        layout_hint = "← Earlier &nbsp;&nbsp; Later →"

    elif layout_mode == "Relevance" and scores:
        pos = _relevance_layout(G, scores)
        show_edges = True
        layout_hint = "Center = most relevant &nbsp;&nbsp; Outer = less relevant"

    elif layout_mode == "Timeline + Relevance" and scores:
        pos = _timeline_relevance_layout(G, date_map, scores)
        show_edges = False
        layout_hint = "X = time &nbsp;&nbsp; Y = relevance score"

    else:  # Force-directed
        pos = nx.spring_layout(G, seed=42, k=0.6, iterations=200)
        if hub_nid and hub_nid in pos:
            hx, hy = pos[hub_nid]
            for nid in list(pos):
                if nid == hub_nid:
                    continue
                dx, dy = pos[nid][0] - hx, pos[nid][1] - hy
                dist = (dx * dx + dy * dy) ** 0.5
                if dist > 0:
                    new_dist = dist * 0.65
                    pos[nid] = (hx + dx / dist * new_dist, hy + dy / dist * new_dist)
        show_edges = True
        layout_hint = ""

    is_scatter = layout_mode == "Timeline + Relevance"

    # ── Node data ─────────────────────────────────────────────────────────────
    node_rows = []
    for nid in G.nodes():
        x, y = pos[nid]
        is_hub      = nid == hub_nid
        is_selected = nid in selected_ids
        if is_hub:
            color, size = "#FF6B35", 1200
        elif is_selected:
            color, size = "#FFD700", 700
        else:
            color, size = "#4C9BE8", 420
        node_rows.append({
            "id":      nid,
            "label":   G.nodes[nid]["label"],
            "date":    date_map.get(nid, ""),
            "score":   (scores or {}).get(unquote(nid).replace("_", " "), 0.0),
            "tooltip": G.nodes[nid]["tooltip"],
            "x":       float(x),
            "y":       float(y),
            "color":   color,
            "size":    size,
        })

    # ── Edge data ─────────────────────────────────────────────────────────────
    edge_rows = []
    if show_edges:
        for i, (u, v) in enumerate(G.edges()):
            for node in (u, v):
                x, y = pos[node]
                edge_rows.append({"x": float(x), "y": float(y), "edge_id": i})

    # ── Altair axis encodings ─────────────────────────────────────────────────
    click_sel = alt.selection_point(name="click", fields=["id"], on="click", toggle=False)

    _axis_style = dict(
        titleColor="#aaaaaa", labelColor="#aaaaaa",
        gridColor="#2a2a2a", domainColor="#555555", tickColor="#555555",
    )

    if is_scatter:
        # Collect all x values to set sensible year ticks
        xs = [r["x"] for r in node_rows]
        year_min, year_max = int(min(xs)), int(max(xs)) + 1
        year_ticks = list(range(year_min, year_max + 1))
        x_enc = alt.X("x:Q",
            scale=alt.Scale(zero=False, padding=0.05),
            axis=alt.Axis(
                title="Year", values=year_ticks, format="d",
                **_axis_style,
            ),
        )
        y_enc = alt.Y("y:Q",
            scale=alt.Scale(domain=[-0.02, 1.08]),
            axis=alt.Axis(
                title="Relevance score", tickCount=6,
                **_axis_style,
            ),
        )
    else:
        x_enc = alt.X("x:Q", axis=None, scale=alt.Scale(zero=False))
        y_enc = alt.Y("y:Q", axis=None, scale=alt.Scale(zero=False))

    layers = []

    if show_edges and edge_rows:
        edge_opacity = 0.3 if layout_mode == "Relevance" else 0.5
        layers.append(
            alt.Chart(alt.Data(values=edge_rows)).mark_line(
                color="#555555", opacity=edge_opacity, strokeWidth=1.2,
            ).encode(x=x_enc, y=y_enc, detail="edge_id:N")
        )

    tt_fields = ["label:N", "date:N", "score:Q", "tooltip:N"] if is_scatter else ["label:N", "tooltip:N"]
    layers.append(
        alt.Chart(alt.Data(values=node_rows)).mark_circle().encode(
            x=x_enc, y=y_enc,
            color=alt.Color("color:N", scale=None),
            size=alt.Size("size:Q", scale=None),
            tooltip=tt_fields,
        ).add_params(click_sel)
    )

    layers.append(
        alt.Chart(alt.Data(values=node_rows)).mark_text(
            dy=-18, fontSize=10, color="#ffffff",
        ).encode(x=x_enc, y=y_enc, text="label:N")
    )

    if show_dates:
        layers.append(
            alt.Chart(alt.Data(values=node_rows))
            .mark_text(dy=18, fontSize=9, color="#bbbbbb")
            .encode(x=x_enc, y=y_enc, text="date:N")
            .transform_filter(alt.datum.date != "")
        )

    chart = alt.layer(*layers).properties(
        width="container",
        height=height,
        background="#0e1117",
    ).interactive().configure_view(stroke=None)

    legend = "🟠 **Main event** &nbsp;&nbsp; 🔵 **Unselected** &nbsp;&nbsp; 🟡 **Selected** &nbsp;&nbsp; — Click a node to select / deselect"
    if layout_hint:
        legend += f" &nbsp;&nbsp;|&nbsp;&nbsp; {layout_hint}"
    st.markdown(legend)

    event = st.altair_chart(chart, width='stretch', on_select="rerun")

    selection = getattr(event, "selection", {})
    points = selection.get("click", []) if selection else []
    if points:
        return points[0].get("id")
    return None
