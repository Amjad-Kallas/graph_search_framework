from rdflib import Graph, URIRef
from datetime import datetime, timedelta
import json
import logging
import os
import re

logging.getLogger("rdflib").setLevel(logging.ERROR)

SEM = "http://semanticweb.cs.vu.nl/2009/11/sem/"

# --------------------------
# Utils
# --------------------------

def normalize_name(name):
    return re.sub(r'[^a-zA-Z0-9]+', '_', name).strip('_')

def is_bad_node(uri):
    name = str(uri).split("/")[-1]
    return re.fullmatch(r"Q\d+", name) is not None

def load_important_event_names(input_ttl):
    path = os.path.join(os.path.dirname(input_ttl), "important_nodes.json")
    if not os.path.exists(path):
        return set()

    with open(path, "r") as f:
        data = json.load(f)

    return set(normalize_name(item["name"]) for item in data)

# --------------------------
# Main filtering
# --------------------------

def apply_post_filtering(input_ttl, config_loaded, main_event=None, max_events=200):
    g = Graph()
    g.parse(input_ttl, format="ttl")

    start_date = datetime.strptime(config_loaded["start_date"], "%Y-%m-%d")
    end_date = datetime.strptime(config_loaded["end_date"], "%Y-%m-%d")

    min_date = start_date - timedelta(days=365)
    max_date = end_date + timedelta(days=365)

    important_names = load_important_event_names(input_ttl)
    main_event_normalized = normalize_name(main_event).lower() if main_event else None

    all_subjects = list({s for s, _, _ in g})

    kept = []
    removed = []

    # --------------------------
    # First pass: filtering
    # --------------------------
    for s in all_subjects:
        name = str(s).split("/")[-1]

        # 0. Remove the main seed event
        if main_event_normalized and name.lower() == main_event_normalized:
            removed.append(s)
            continue

        # 1. Remove unresolved Q nodes
        if is_bad_node(s):
            removed.append(s)
            continue

        # 2. Must have a comment
        has_comment = any(True for _ in g.triples((s, URIRef("http://www.w3.org/2000/01/rdf-schema#comment"), None)))
        if not has_comment:
            removed.append(s)
            continue

        # 3. Check date
        valid_date = False
        for _, _, date_literal in g.triples((s, URIRef(SEM + "hasTimeStamp"), None)):
            try:
                d = datetime.strptime(str(date_literal).split("^^")[0], "%Y-%m-%d")
                if min_date <= d <= max_date:
                    valid_date = True
                break
            except:
                continue

        # 4. Keep logic
        if name in important_names:
            kept.append(s)
        elif valid_date:
            kept.append(s)
        else:
            removed.append(s)

    for e in removed:
        g.remove((e, None, None))
        g.remove((None, None, e))

    # --------------------------
    # Second pass: limit size
    # --------------------------
    remaining = list({s for s, _, _ in g})

    important = []
    normal = []

    for e in remaining:
        name = str(e).split("/")[-1]
        if name in important_names:
            important.append(e)
        else:
            normal.append(e)

    final = important + normal[:max(0, max_events - len(important))]
    to_remove = set(remaining) - set(final)

    for e in to_remove:
        g.remove((e, None, None))
        g.remove((None, None, e))

    # --------------------------
    # Save
    # --------------------------
    g.serialize(input_ttl, format="ttl")
    print(f"Filtered graph updated: {input_ttl}")


if __name__ == "__main__":
    input_ttl = "/home/kallas/project/graph_search_framework/experiments/2026-05-03-15_35_02-informed_wikidata_french_revolution_10_pred_object_freq_domain_range___when__without_category_uri_iter__max_inf/output_ng.ttl"

    config = {
    "start": "http://www.wikidata.org/entity/Q361",
    "start_date": "1914-01-01",
    "end_date": "1918-12-31",

    }

    from src.wikidata_subgraph_to_readable import get_single_label

    main_event = get_single_label(config["start"])

    apply_post_filtering(input_ttl, config, main_event=main_event, max_events=200)
