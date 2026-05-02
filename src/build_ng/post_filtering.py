import pandas as pd
from rdflib import Graph, URIRef
from rdflib.namespace import RDF
from datetime import datetime, timedelta
import json
import os
import re

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

def apply_post_filtering(input_ttl, config_loaded, max_events=200):
    g = Graph()
    g.parse(input_ttl, format="ttl")

    start_date = datetime.strptime(config_loaded["start_date"], "%Y-%m-%d")
    end_date = datetime.strptime(config_loaded["end_date"], "%Y-%m-%d")

    min_date = start_date - timedelta(days=365)
    max_date = end_date + timedelta(days=365)

    important_names = load_important_event_names(input_ttl)

    all_events = list(g.subjects(RDF.type, URIRef(SEM + "Event")))

    kept_events = []
    removed_events = []

    # --------------------------
    # First pass: filtering
    # --------------------------
    for s in all_events:
        name = str(s).split("/")[-1]

        # 1. Remove unresolved Q nodes
        if is_bad_node(s):
            removed_events.append(s)
            continue

        # 2. Check if has comment
        has_comment = False
        for _, _, comment in g.triples((s, URIRef("http://www.w3.org/2000/01/rdf-schema#comment"), None)):
            has_comment = True
            break

        if not has_comment:
            removed_events.append(s)
            continue

        # 3. Check date
        valid_date = False
        for _, _, date_literal in g.triples((s, URIRef(SEM + "hasTimeStamp"), None)):
            try:
                d = datetime.strptime(str(date_literal), "%Y-%m-%d")
                if min_date <= d <= max_date:
                    valid_date = True
                break
            except:
                continue

        # 4. Keep logic
        if name in important_names:
            kept_events.append(s)
        elif valid_date:
            kept_events.append(s)
        else:
            removed_events.append(s)

    # Apply removal
    for e in removed_events:
        g.remove((e, None, None))
        g.remove((None, None, e))

    # --------------------------
    # Second pass: limit size
    # --------------------------
    remaining = list(g.subjects(RDF.type, URIRef(SEM + "Event")))

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
    input_ttl = "/home/kallas/project/graph_search_framework/experiments/2026-04-28-11_03_05-informed_wikidata_french_revolution_2_pred_object_freq_domain_range__where_when__without_category_uri_iter__max_inf/output_ng.ttl"

    config = {
    "start": "http://www.wikidata.org/entity/Q361",
    "start_date": "1914-01-01",
    "end_date": "1918-12-31",

    }

    apply_post_filtering(input_ttl, config, max_events=1)