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
            d_str = str(d)
            # HDT returns literals like '"1914-09-01"^^xsd:dateTime' — strip the quotes first
            if d_str.startswith('"'):
                d_str = d_str.split('"')[1]
            d_str = d_str[:10]
            _, m, day = d_str.split("-")
            score = (m != "01") + (day != "01")
            if score > best_score:
                best_score = score
                best = d_str
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

        # dates (event predicates + person birth/death + artwork inception)
        for p in [
            "http://www.wikidata.org/prop/direct/P585",
            "http://www.wikidata.org/prop/direct/P580",
            "http://www.wikidata.org/prop/direct/P582",
            "http://www.wikidata.org/prop/direct/P569",  # date of birth
            "http://www.wikidata.org/prop/direct/P570",  # date of death
            "http://www.wikidata.org/prop/direct/P571",  # inception (artworks, orgs)
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
# Relationship date via Wikidata statement qualifiers
# --------------------------
def get_relationship_date_hdt(hdt_docs, s_uri, p_uri, o_uri):
    """Return qualifier dates (P580/P582/P585) on the statement node for (s, p, o)."""
    if "/prop/direct/" not in p_uri:
        return []

    stmt_pred = p_uri.replace("/prop/direct/", "/prop/")
    val_pred  = p_uri.replace("/prop/direct/", "/prop/statement/")

    dates = []
    for (_, _, stmt) in search_triples(hdt_docs, s_uri, stmt_pred, ""):
        if not search_triples(hdt_docs, stmt, val_pred, o_uri):
            continue
        for pq in [
            "http://www.wikidata.org/prop/qualifier/P580",  # start time
            "http://www.wikidata.org/prop/qualifier/P582",  # end time
            "http://www.wikidata.org/prop/qualifier/P585",  # point in time
        ]:
            for (_, _, d) in search_triples(hdt_docs, stmt, pq, ""):
                dates.append(d)
    return dates

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
# Predicate labels from HDT
# --------------------------
def fetch_predicate_labels_hdt(hdt_docs, pred_uris):
    labels = {}
    for uri in pred_uris:
        en_label = None

        # Try the property URI directly
        triples = search_triples(hdt_docs, uri, "http://www.w3.org/2000/01/rdf-schema#label", "")
        for (_, _, o) in triples:
            if '"@en' in o:
                en_label = o.split('"')[1]
                break

        # Wikidata stores property labels on the entity URI, not the direct property URI
        if not en_label and "/prop/direct/" in uri:
            entity_uri = uri.replace("/prop/direct/", "/entity/")
            triples = search_triples(hdt_docs, entity_uri, "http://www.w3.org/2000/01/rdf-schema#label", "")
            for (_, _, o) in triples:
                if '"@en' in o:
                    en_label = o.split('"')[1]
                    break

        labels[uri] = en_label or uri.split("/")[-1].split("#")[-1]
    return labels

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
    pred_uris = set(df["predicate"])

    print("Fetching event info (HDT)...")
    event_info = get_events_info_hdt(hdt_docs, all_nodes)

    print("Collecting nodes for labels...")
    nodes_to_label = set(all_nodes)
    for e, info in event_info.items():
        nodes_to_label.update(info["actors"])
        nodes_to_label.update(info["places"])

    print("Fetching labels (HDT)...")
    labels = fetch_labels_hdt(hdt_docs, nodes_to_label)

    print("Fetching predicate labels (HDT)...")
    pred_labels = fetch_predicate_labels_hdt(hdt_docs, pred_uris)

    print("Fetching Wikipedia descriptions (HDT sitelinks + Wikipedia API)...")
    uri_to_title = fetch_wikipedia_titles_hdt(hdt_docs, all_nodes, labels=labels)
    descriptions = fetch_wikipedia_summaries_batch(uri_to_title)
    print(f"Got descriptions for {len(descriptions)} / {len(all_nodes)} nodes.")

    # --------------------------
    # Build one event per triple
    # --------------------------
    print("Building events...")
    for _, row in tqdm(df.iterrows(), total=len(df)):
        s_uri = str(row["subject"])
        p_uri = str(row["predicate"])
        o_uri = str(row["object"])

        s_label = labels.get(s_uri) or s_uri.split("/")[-1].replace("_", " ")
        p_label = pred_labels.get(p_uri, p_uri.split("/")[-1])
        o_label = labels.get(o_uri) or o_uri.split("/")[-1].replace("_", " ")

        event_id = re.sub(r'[^a-zA-Z0-9]+', '_', f"{s_label}_{p_label}_{o_label}").strip('_')
        event_node = NG[event_id]

        g.add((event_node, RDF.type, SEM.Event))
        g.add((event_node, NG.subject, Literal(s_label)))
        g.add((event_node, NG.property, Literal(p_label)))
        g.add((event_node, NG.object, Literal(o_label)))

        # Enrichment — actors from object node, date/desc from subject node
        obj_info = event_info.get(o_uri, {})
        sub_info = event_info.get(s_uri, {})

        for a in obj_info.get("actors", []):
            g.add((event_node, SEM.hasActor, make_readable_uri(a, labels)))

        # Date: relationship qualifiers first, then subject node, then object node
        rel_dates = get_relationship_date_hdt(hdt_docs, s_uri, p_uri, o_uri)
        date_pool = rel_dates or sub_info.get("dates", []) or obj_info.get("dates", [])
        best_date = select_best_date(date_pool)
        if best_date:
            g.set((event_node, SEM.hasTimeStamp, Literal(best_date, datatype=XSD.date)))

        # Description: subject node only — no fallback to object to avoid pollution
        desc = descriptions.get(s_uri)
        if desc:
            g.add((event_node, RDFS.comment, Literal(desc)))

    # --------------------------
    # Save
    # --------------------------
    g.serialize(output_file, format="ttl")
    print("Done.")

# --------------------------
# ENTRY
# --------------------------
if __name__ == "__main__":
    input_csv = "/home/kallas/project/graph_search_framework/experiments/person/pablo_picasso/1/3-subgraph.csv"
    output_ttl = "/home/kallas/project/graph_search_framework/experiments/person/pablo_picasso/1/hohoho1.ttl"
    
    hdt_folder = "/home/kallas/project/graph_search_framework/wikidata_dataset"   # <- folder, not file


    build_ng_wikidata_hdt(input_csv, hdt_folder, output_ttl)