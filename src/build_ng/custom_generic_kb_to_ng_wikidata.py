import pandas as pd
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, RDFS, XSD
from tqdm import tqdm
from hdt import HDTDocument
import os
import re
import json
import requests
import time

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
        if not isinstance(label, str):
            label = str(label) if label is not None else ""
        if label:
            clean = re.sub(r'[^a-zA-Z0-9]+', '_', label).strip('_')
            if clean:
                return NG[clean]
    return encode(original_uri)

HEADERS = {"User-Agent": "KG-Narrative/1.0"}

def clean_uris(uris):
    return [u.strip() for u in uris if u and isinstance(u, str) and u.strip()]

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
# upgrade important_nodes.json using HDT labels
# --------------------------
def upgrade_important_nodes_json(input_file, hdt_docs):
    path = os.path.join(os.path.dirname(input_file), "important_nodes.json")
    if not os.path.exists(path):
        print("important_nodes.json not found")
        return

    with open(path, "r") as f:
        data = json.load(f)

    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        print("JSON already upgraded")
        return

    uris = clean_uris(data)
    labels = fetch_labels_hdt(hdt_docs, uris)
    upgraded = [{"uri": uri, "name": labels.get(uri, uri.split("/")[-1])} for uri in uris]

    with open(path, "w") as f:
        json.dump(upgraded, f, indent=2)
    print("important_nodes.json updated.")


# --------------------------
# Wikipedia descriptions (title via HDT, summary via Wikipedia API)
# --------------------------
def fetch_wikipedia_titles_hdt(hdt_docs, uris, labels=None):
    titles = {}
    for uri in uris:
        triples = search_triples(hdt_docs, "", "http://schema.org/about", uri)
        for (s, _, _) in triples:
            if "en.wikipedia.org/wiki/" in s:
                titles[uri] = s.split("/wiki/")[-1]
                break
        if uri not in titles and labels:
            label = labels.get(uri)
            if label and isinstance(label, str):
                titles[uri] = label.replace(" ", "_")
    return titles


def fetch_wikipedia_summaries_batch(uri_to_title, max_words=100):
    title_to_uri = {v: k for k, v in uri_to_title.items()}
    summaries = {}

    for batch in chunked(list(uri_to_title.items()), 20):
        batch_titles = [title for _, title in batch]
        try:
            r = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "prop": "extracts",
                    "exintro": True,
                    "exsentences": 3,
                    "titles": "|".join(batch_titles),
                    "format": "json",
                    "redirects": True,
                },
                headers=HEADERS,
                timeout=15,
            )
            if r.status_code != 200:
                continue
            pages = r.json().get("query", {}).get("pages", {})
            redirects = {d["from"]: d["to"] for d in r.json().get("query", {}).get("redirects", [])}
            normalized = {d["from"]: d["to"] for d in r.json().get("query", {}).get("normalized", [])}

            for _, page in pages.items():
                if page.get("missing") == "":
                    continue
                page_title = page.get("title", "")
                extract = re.sub(r"<[^>]+>", "", page.get("extract", "")).strip()
                if not extract:
                    continue
                original_title = page_title
                for mapping in [normalized, redirects]:
                    for k, v in mapping.items():
                        if v == page_title:
                            original_title = k
                            break
                uri = title_to_uri.get(original_title) or title_to_uri.get(page_title)
                if uri:
                    summaries[uri] = " ".join(extract.split()[:max_words])
        except Exception:
            continue
        time.sleep(0.5)

    return summaries


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

    upgrade_important_nodes_json(input_file, hdt_docs)

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

    print("Fetching Wikipedia descriptions (HDT sitelinks + Wikipedia API)...")
    uri_to_title = fetch_wikipedia_titles_hdt(hdt_docs, event_uris, labels=labels)
    descriptions = fetch_wikipedia_summaries_batch(uri_to_title)
    print(f"Got descriptions for {len(descriptions)} / {len(event_uris)} events.")

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

        best_date = select_best_date(info.get("dates", []))
        if best_date:
            g.set((node, SEM.hasTimeStamp, Literal(best_date, datatype=XSD.date)))

        desc = descriptions.get(uri)
        if desc:
            g.add((node, RDFS.comment, Literal(desc)))

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