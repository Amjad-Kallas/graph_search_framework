import pandas as pd
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, RDFS, XSD
from tqdm import tqdm
from hdt import HDTDocument
import os
import re

# --------------------------
# Namespaces
# --------------------------
SEM = Namespace("http://semanticweb.cs.vu.nl/2009/11/sem/")
NG  = Namespace("http://narrative.graph/entity/")

# --------------------------
# Utils
# --------------------------
def encode(uri):
    return URIRef(uri.strip())

def select_best_date(dates):
    best, best_score = None, -1
    for d in dates:
        try:
            d = d[:10]
            _, m, day = d.split("-")
            score = (m != "01") + (day != "01")
            if score > best_score:
                best_score = score
                best = d
        except:
            continue
    return best

def make_readable_uri(original_uri, labels_dict):
    if original_uri in labels_dict:
        label = labels_dict[original_uri]
        clean = re.sub(r'[^a-zA-Z0-9]+', '_', label).strip('_')
        return NG[clean]
    return encode(original_uri)

def chunked(lst, size=50):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]

# --------------------------
# Load HDT folder
# --------------------------
def load_hdt_folder(folder_path):
    hdt_docs = []
    for file in os.listdir(folder_path):
        if file.endswith(".hdt"):
            full_path = os.path.join(folder_path, file)
            hdt_docs.append(HDTDocument(full_path))
    return hdt_docs

# --------------------------
# Query helpers
# --------------------------
def search_triples(hdt_docs, s="", p="", o=""):
    results = []
    for hdt in hdt_docs:
        triples, _ = hdt.search_triples(s, p, o)
        for t in triples:
            results.append(t)
    return results

# --------------------------
# Event enrichment (HDT)
# --------------------------
def get_events_info_hdt(hdt_docs, uris):
    result = {}

    for uri in tqdm(uris):
        actors = set()
        places = set()
        dates = []

        # actors
        for p in ["http://www.wikidata.org/prop/direct/P710",
                  "http://www.wikidata.org/prop/direct/P1344"]:
            triples = search_triples(hdt_docs, uri, p, "")
            for (_, _, o) in triples:
                actors.add(o)

        # places
        triples = search_triples(
            hdt_docs,
            uri,
            "http://www.wikidata.org/prop/direct/P276",
            ""
        )
        for (_, _, o) in triples:
            places.add(o)

        # dates
        for p in [
            "http://www.wikidata.org/prop/direct/P585",
            "http://www.wikidata.org/prop/direct/P580",
            "http://www.wikidata.org/prop/direct/P582",
        ]:
            triples = search_triples(hdt_docs, uri, p, "")
            for (_, _, o) in triples:
                dates.append(o)

        result[uri] = {
            "actors": actors,
            "places": places,
            "dates": dates
        }

    return result

# --------------------------
# Labels from HDT
# --------------------------
def fetch_labels_hdt(hdt_docs, uris):
    labels = {}

    for uri in uris:
        triples = search_triples(
            hdt_docs,
            uri,
            "http://www.w3.org/2000/01/rdf-schema#label",
            ""
        )

        en_label = None
        fallback = None

        for (_, _, o) in triples:
            if '"@en' in o:
                en_label = o.split('"')[1]
                break
            elif not fallback:
                fallback = o.split('"')[1] if '"' in o else o

        labels[uri] = en_label if en_label else fallback

    return labels

# --------------------------
# Predicate mapping
# --------------------------
def map_predicate(pred):
    if pred.endswith("P361"):
        return SEM.subEventOf
    if pred.endswith("P31"):
        return RDF.type
    if pred.endswith("P279"):
        return RDFS.subClassOf
    return None

# --------------------------
# MAIN
# --------------------------
def build_ng_wikidata_hdt(input_file, hdt_folder, output_file):
    df = pd.read_csv(input_file)

    print("Loading HDT files...")
    hdt_docs = load_hdt_folder(hdt_folder)

    g = Graph()
    g.bind("sem", SEM)
    g.bind("ng", NG)

    all_nodes = set(df["subject"]).union(set(df["object"]))

    # events = keep same simple logic
    event_uris = set(all_nodes)

    print("Fetching event info (HDT)...")
    event_info = get_events_info_hdt(hdt_docs, event_uris)

    print("Collecting nodes for labels...")
    nodes_to_label = set(all_nodes)
    for e, info in event_info.items():
        nodes_to_label.update(info["actors"])
        nodes_to_label.update(info["places"])

    print("Fetching labels (HDT)...")
    labels = fetch_labels_hdt(hdt_docs, nodes_to_label)

    # --------------------------
    # Structure
    # --------------------------
    print("Building structure...")
    for _, row in df.iterrows():
        mapped = map_predicate(row["predicate"])
        if not mapped:
            continue

        s = make_readable_uri(row["subject"], labels)
        o = make_readable_uri(row["object"], labels)

        g.add((s, mapped, o))

    # --------------------------
    # Enrichment
    # --------------------------
    print("Enrichment...")
    for uri in tqdm(event_uris):
        node = make_readable_uri(uri, labels)
        g.add((node, RDF.type, SEM.Event))

        info = event_info.get(uri, {})

        for a in info.get("actors", []):
            g.add((node, SEM.hasActor, make_readable_uri(a, labels)))

        for p in info.get("places", []):
            g.add((node, SEM.hasPlace, make_readable_uri(p, labels)))

        '''best_date = select_best_date(info.get("dates", []))
        if best_date:
            g.set((node, SEM.hasTimeStamp, Literal(best_date, datatype=XSD.date)))'''

    # --------------------------
    # Save
    # --------------------------
    g.serialize(output_file, format="ttl")
    print("Done.")

# --------------------------
# ENTRY
# --------------------------
if __name__ == "__main__":
    input_csv = "/home/kallas/project/graph_search_framework/experiments/2026-04-28-08_47_05-informed_wikidata_french_revolution_2_pred_object_freq_domain_range__where_when__without_category_uri_iter__max_inf/pruned-2-subgraph.csv"
    output_ttl = "/home/kallas/project/graph_search_framework/experiments/2026-04-28-08_47_05-informed_wikidata_french_revolution_2_pred_object_freq_domain_range__where_when__without_category_uri_iter__max_inf/li_huwesh.ttl"
    hdt_folder = "/home/kallas/project/graph_search_framework/wikidata_dataset"   # <- folder, not file


    build_ng_wikidata_hdt(input_csv, hdt_folder, output_ttl)