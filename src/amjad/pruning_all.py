import os
import re
import glob
from urllib.parse import unquote

import pandas as pd
import networkx as nx
from rdflib import Graph as RDFGraph

from src.amjad.wikipedia_similarity import (
    get_wikipedia_intro,
    compute_wiki_similarity_scores,
)
from src.amjad.llm_pruning import score_events_llm


def parse_events_from_ttl(ttl_file):
    """
    Parse all sem:Event nodes using rdflib — robust to any serialisation format,
    including files re-serialised by post_filtering.py.
    Mirrors the predicate-string matching used in parse_rdf.py.
    Returns list[dict] with keys: name, date, place, comment.
    Events without a comment are excluded (required by wiki + LLM scoring).
    """
    g = RDFGraph()
    g.parse(ttl_file, format="ttl")

    # Collect event URIs (same logic as parse_rdf.py)
    event_uris = set()
    for s, p, o in g:
        if "type" in str(p) and "Event" in str(o):
            event_uris.add(s)

    raw = {uri: {"date": None, "place": None, "comment": None} for uri in event_uris}

    for s, p, o in g:
        if s not in raw:
            continue
        p_str = str(p)
        if "hasTimeStamp" in p_str:
            raw[s]["date"] = str(o).split("^^")[0]
        elif "hasPlace" in p_str:
            raw[s]["place"] = unquote(str(o).split("/")[-1]).replace("_", " ")
        elif "comment" in p_str:
            raw[s]["comment"] = str(o)

    events = []
    for uri, info in raw.items():
        if info["comment"] is None:
            continue  # wiki + LLM signals require a comment
        name = unquote(str(uri).split("/")[-1]).replace("_", " ")
        events.append({
            "name": name,
            "date": info["date"] or "unknown",
            "place": info["place"] or "unknown",
            "comment": info["comment"],
        })
    return events


# ---------------------------------------------------------------------------
# PPR on the original KG subgraph
# ---------------------------------------------------------------------------

def _find_subgraph_files(folder):
    """Return (raw_csv, readable_csv) for the last iteration subgraph in *folder*."""
    candidates = [
        f for f in glob.glob(os.path.join(folder, "*-subgraph.csv"))
        if "pruned" not in os.path.basename(f)
    ]
    if not candidates:
        raise FileNotFoundError(f"No *-subgraph.csv found in {folder}")
    candidates.sort(key=lambda f: int(re.match(r"(\d+)-subgraph", os.path.basename(f)).group(1)))
    raw = candidates[-1]
    readable = raw.replace("-subgraph.csv", "-subgraph_readable.csv")
    if not os.path.exists(readable):
        raise FileNotFoundError(f"Readable subgraph not found: {readable}")
    return raw, readable


def _build_label_uri_map(raw_csv, readable_csv):
    """
    Join the raw (URI) and readable (label) CSVs row-by-row to build
    a {label: uri} mapping for all subjects and objects.
    """
    raw_df = pd.read_csv(raw_csv)
    readable_df = pd.read_csv(readable_csv)

    label_to_uri = {}
    for (_, raw_row), (_, read_row) in zip(raw_df.iterrows(), readable_df.iterrows()):
        for uri_col, lbl_col in [("subject", "subject_label"), ("object", "object_label")]:
            uri = raw_row[uri_col]
            lbl = str(read_row[lbl_col]).strip()
            if lbl and lbl != "nan":
                label_to_uri[lbl] = uri
    return label_to_uri


def get_ppr_scores_from_subgraph(folder, main_event, alpha=0.85):
    """
    Personalized PageRank on the original KG subgraph CSV, seeded on *main_event*.

    Uses *-subgraph.csv for graph topology (real Wikidata URIs) and
    *-subgraph_readable.csv to map labels ↔ URIs so scores are returned
    keyed by human-readable label — matching the convention in
    wikipedia_similarity.py.

    Returns
    -------
    dict {event_label: score normalized to [0, 1]}
    """
    raw_csv, readable_csv = _find_subgraph_files(folder)
    print(f"Using subgraph: {os.path.basename(raw_csv)}")

    raw_df = pd.read_csv(raw_csv)
    label_to_uri = _build_label_uri_map(raw_csv, readable_csv)
    uri_to_label = {v: k for k, v in label_to_uri.items()}

    G = nx.from_pandas_edgelist(
        raw_df, source="subject", target="object", create_using=nx.DiGraph()
    )

    seed_uri = label_to_uri.get(main_event)
    if seed_uri and seed_uri in G.nodes():
        epsilon = 1e-6
        personalization = {n: epsilon for n in G.nodes()}
        personalization[seed_uri] = 1.0
        total = sum(personalization.values())
        personalization = {k: v / total for k, v in personalization.items()}
        print(f"PPR seeded on: {main_event} ({seed_uri})")
    else:
        print(f"WARNING: '{main_event}' not found in subgraph nodes. Using uniform PageRank.")
        personalization = None

    pr = nx.pagerank(G, alpha=alpha, personalization=personalization)

    label_scores = {
        uri_to_label[uri]: score
        for uri, score in pr.items()
        if uri in uri_to_label
    }

    if not label_scores:
        return {}
    vals = list(label_scores.values())
    vmin, vmax = min(vals), max(vals)
    vrange = vmax - vmin if vmax > vmin else 1.0
    return {lbl: (v - vmin) / vrange for lbl, v in label_scores.items()}


# ---------------------------------------------------------------------------
# Combined three-score reranker
# ---------------------------------------------------------------------------

def rerank_events_three_scores(
    ttl_file,
    main_event,
    target_k=35,
    ppr_weight=0.3,
    wiki_weight=0.3,
    llm_weight=0.4,
):
    """
    Score every event in *ttl_file* using three signals:
      1. PPR  — personalized PageRank on the original KG subgraph (graph structure)
      2. Wiki — cosine similarity of event comment to Wikipedia intro of main_event
      3. LLM  — numeric relevance score from the LLM (batched to avoid timeouts)

    All scores are normalized to [0, 1] before combining.

    Outputs written to the same folder as *ttl_file*:
      - scores_all.txt                  full ranking with all three scores
      - selected_events_combined.txt    plain event names, one per line (top-k)

    Returns
    -------
    selected : list[dict]
    output_file : str   path to selected_events_combined.txt
    """
    assert abs(ppr_weight + wiki_weight + llm_weight - 1.0) < 1e-6, "Weights must sum to 1"

    folder = os.path.dirname(ttl_file)

    # 1. Parse events via rdflib (robust to rdflib re-serialised TTLs)
    events = parse_events_from_ttl(ttl_file)
    print(f"Parsed {len(events)} events with comments from TTL.")

    # 2. PPR on the original KG subgraph
    ppr_scores = get_ppr_scores_from_subgraph(folder, main_event)
    print(f"PPR scores available for {len(ppr_scores)} labelled nodes.")

    # 3. Wikipedia similarity
    print(f"Fetching Wikipedia intro for '{main_event}' ...")
    wiki_intro = get_wikipedia_intro(main_event)
    wiki_scores = compute_wiki_similarity_scores(events, wiki_intro)
    print("Wikipedia similarity scores computed.")

    wiki_vals = list(wiki_scores.values())
    w_min, w_max = min(wiki_vals), max(wiki_vals)
    w_range = w_max - w_min if w_max > w_min else 1.0
    wiki_scores_norm = {k: (v - w_min) / w_range for k, v in wiki_scores.items()}

    # 4. LLM scores (score_events_llm already returns values in [0, 1])
    llm_scores = score_events_llm(events, main_event)
    print(f"LLM returned scores for {len(llm_scores)} / {len(events)} events.")

    # 5. Combine
    combined = []
    for e in events:
        name = e["name"]
        ps = ppr_scores.get(name, 0.0)
        ws = wiki_scores_norm.get(name, 0.0)
        ls = llm_scores.get(name, 0.0)
        score = ppr_weight * ps + wiki_weight * ws + llm_weight * ls
        combined.append({**e, "ppr_score": ps, "wiki_score": ws, "llm_score": ls, "combined_score": score})

    combined.sort(key=lambda x: x["combined_score"], reverse=True)
    selected = combined[:target_k]

    # 6. Print ranking table
    col = 50
    header = (f"{'#':<4} {'Event':<{col}} {'combined':>8}"
              f"  {'ppr':>6}  {'wiki':>6}  {'llm':>6}")
    sep = "-" * len(header)
    print(f"\n{sep}\n{header}\n{sep}")
    for rank, e in enumerate(combined, 1):
        marker = "***" if rank <= target_k else "   "
        print(
            f"{rank:<4} {e['name']:<{col}.{col}}{marker} "
            f"{e['combined_score']:>8.3f}"
            f"  {e['ppr_score']:>6.3f}  {e['wiki_score']:>6.3f}  {e['llm_score']:>6.3f}"
        )
    print(sep)

    # 7. Write outputs
    def _fmt(e, rank):
        return (
            f"{rank:>3}. {e['name']}"
            f"  |  combined={e['combined_score']:.3f}"
            f"  ppr={e['ppr_score']:.3f}"
            f"  wiki={e['wiki_score']:.3f}"
            f"  llm={e['llm_score']:.3f}"
        )

    all_scores_file = os.path.join(folder, "scores_all.txt")
    with open(all_scores_file, "w", encoding="utf-8") as f:
        f.write(
            f"All {len(combined)} events ranked by combined score "
            f"(ppr={ppr_weight}, wiki={wiki_weight}, llm={llm_weight})\n"
            f"Top {target_k} marked with ***\n\n"
        )
        for rank, e in enumerate(combined, 1):
            marker = " ***" if rank <= target_k else ""
            f.write(_fmt(e, rank) + marker + "\n")

    selected_file = os.path.join(folder, "selected_events_combined.txt")
    with open(selected_file, "w", encoding="utf-8") as f:
        for e in selected:
            f.write(e["name"] + "\n")

    print(f"\nScores (all events) -> {all_scores_file}")
    print(f"Selected top-{target_k}  -> {selected_file}")
    return selected, selected_file


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ttl_path = (
        "/home/kallas/project/graph_search_framework/experiments/"
        "2026-05-02-20_19_01-informed_wikidata_french_revolution_10_pred_object_freq_"
        "domain_range___when__without_category_uri_iter__max_inf/output_ng.ttl"
    )
    main_event = "World War I"

    selected, out = rerank_events_three_scores(ttl_path, main_event, target_k=35)
