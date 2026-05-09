import os
import base64
import tempfile

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


def render_narrative_graph_interactive(
    ttl_path: str,
    selected_ids: set,
    height: int = 700,
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

    # ── Build networkx graph for layout ───────────────────────────────────────
    G = nx.Graph()
    event_nids: set = set()

    for ev in events:
        nid = _node_id(str(ev))
        label = nid.replace("_", " ")
        date = g.value(ev, SEM.hasTimeStamp)
        comment = g.value(ev, RDFS.comment)
        tip = label
        if date:
            tip += f" ({date})"
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

    pos = nx.spring_layout(G, seed=42, k=1.5)

    # ── Node data ─────────────────────────────────────────────────────────────
    node_rows = []
    for nid in G.nodes():
        x, y = pos[nid]
        node_rows.append({
            "id": nid,
            "label": G.nodes[nid]["label"],
            "tooltip": G.nodes[nid]["tooltip"],
            "x": float(x),
            "y": float(y),
            "color": "#FFD700" if nid in selected_ids else "#4C9BE8",
            "size": 250 if nid in selected_ids else 150,
        })

    # ── Edge data (two rows per edge, grouped by edge_id for mark_line) ───────
    edge_rows = []
    for i, (u, v) in enumerate(G.edges()):
        for node in (u, v):
            x, y = pos[node]
            edge_rows.append({"x": float(x), "y": float(y), "edge_id": i})

    # ── Altair layers ─────────────────────────────────────────────────────────
    click_sel = alt.selection_point(name="click", fields=["id"], on="click", toggle=False)

    edge_layer = alt.Chart(alt.Data(values=edge_rows)).mark_line(
        color="#666666", opacity=0.6, strokeWidth=1.5,
    ).encode(
        x=alt.X("x:Q", axis=None, scale=alt.Scale(zero=False)),
        y=alt.Y("y:Q", axis=None, scale=alt.Scale(zero=False)),
        detail="edge_id:N",
    )

    node_layer = alt.Chart(alt.Data(values=node_rows)).mark_circle().encode(
        x=alt.X("x:Q", axis=None, scale=alt.Scale(zero=False)),
        y=alt.Y("y:Q", axis=None, scale=alt.Scale(zero=False)),
        color=alt.Color("color:N", scale=None),
        size=alt.Size("size:Q", scale=None),
        tooltip=["label:N", "tooltip:N"],
    ).add_params(click_sel)

    label_layer = alt.Chart(alt.Data(values=node_rows)).mark_text(
        dy=-14, fontSize=10, color="#ffffff",
    ).encode(
        x=alt.X("x:Q", axis=None, scale=alt.Scale(zero=False)),
        y=alt.Y("y:Q", axis=None, scale=alt.Scale(zero=False)),
        text="label:N",
    )

    chart = (edge_layer + node_layer + label_layer).properties(
        width="container",
        height=height,
        background="#0e1117",
    ).configure_view(stroke=None)

    st.markdown("🔵 **Unselected** &nbsp;&nbsp; 🟡 **Selected** &nbsp;&nbsp; — Click a node to select / deselect")

    event = st.altair_chart(chart, width='stretch', on_select="rerun")

    # Extract clicked node ID from selection
    selection = getattr(event, "selection", {})
    points = selection.get("click", []) if selection else []
    if points:
        return points[0].get("id")
    return None
