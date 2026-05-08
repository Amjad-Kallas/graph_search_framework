import pandas as pd
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, RDFS, XSD
from tqdm import tqdm
import requests
from urllib.parse import quote
import time
import re
import os
import json 

# --------------------------
# Namespaces
# --------------------------
SEM = Namespace("http://semanticweb.cs.vu.nl/2009/11/sem/")
WDT = "http://www.wikidata.org/prop/direct/"
WD  = "http://www.wikidata.org/entity/"
NG  = Namespace("http://narrative.graph/entity/")

# --------------------------
# SPARQL CONFIG
# --------------------------
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "KG-Narrative/1.0 (harrypotterone12321@gmail.com)"
}

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

def clean_uris(uris):
    return [
        u.strip()
        for u in uris
        if u and isinstance(u, str) and u.strip()
    ]

def make_readable_uri(original_uri, labels_dict):
    if original_uri in labels_dict:
        label = labels_dict[original_uri]
        clean = re.sub(r'[^a-zA-Z0-9]+', '_', label).strip('_')
        return NG[clean]
    return encode(original_uri)

# --------------------------
# Robust SPARQL
# --------------------------
def run_sparql(query, max_retries=5, timeout=20):
    for attempt in range(max_retries):
        t0 = time.time()
        try:
            r = requests.get(
                WIKIDATA_SPARQL,
                params={"query": query},
                headers=HEADERS,
                timeout=timeout
            )
            elapsed = time.time() - t0

            if r.status_code == 200:
                print(f"  [SPARQL] OK ({elapsed:.1f}s)")
                return r.json()

            elif r.status_code == 429:
                sleep = 2 ** attempt
                print(f"  [SPARQL] 429 Rate-limited (attempt {attempt+1}/{max_retries}) — sleeping {sleep}s")
                time.sleep(sleep)

            elif r.status_code == 503:
                sleep = 2 ** attempt
                print(f"  [SPARQL] 503 Service unavailable (attempt {attempt+1}/{max_retries}) — sleeping {sleep}s")
                time.sleep(sleep)

            else:
                print(f"  [SPARQL] HTTP {r.status_code} ({elapsed:.1f}s)")
                time.sleep(2 ** attempt)

        except requests.exceptions.Timeout:
            elapsed = time.time() - t0
            print(f"  [SPARQL] Timeout after {elapsed:.1f}s (attempt {attempt+1}/{max_retries})")
            time.sleep(2 ** attempt)
        except requests.exceptions.RequestException as e:
            elapsed = time.time() - t0
            print(f"  [SPARQL] Request error after {elapsed:.1f}s (attempt {attempt+1}/{max_retries}): {e}")
            time.sleep(2 ** attempt)

    print(f"  [SPARQL] All {max_retries} attempts failed.")
    return None

# --------------------------
# Batch helpers
# --------------------------
def chunked(lst, size=50):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]

# --------------------------
# Simple duplicate removal, noteamjad: delete me later
# --------------------------
def get_events_set(uris):
    return set(uris)

# --------------------------
# Event enrichment
# --------------------------
def get_events_info(uris):
    result = {}

    for batch in chunked(list(uris), 40):
        values = " ".join(f"<{u}>" for u in batch)

        query = f"""
        SELECT ?event ?actor ?place ?date WHERE {{
          VALUES ?event {{ {values} }}

          OPTIONAL {{ ?event wdt:P710 ?actor. }}
          OPTIONAL {{ ?event wdt:P1344 ?actor. }}
          OPTIONAL {{ ?event wdt:P276 ?place. }}

          OPTIONAL {{ ?event wdt:P585 ?date. }}
          OPTIONAL {{ ?event wdt:P580 ?date. }}
          OPTIONAL {{ ?event wdt:P582 ?date. }}
        }}
        """

        data = run_sparql(query)
        if not data:
            continue

        for b in data["results"]["bindings"]:
            e = b["event"]["value"]

            if e not in result:
                result[e] = {"actors": set(), "places": set(), "dates": []}

            if "actor" in b:
                result[e]["actors"].add(b["actor"]["value"])

            if "place" in b:
                result[e]["places"].add(b["place"]["value"])

            if "date" in b:
                result[e]["dates"].append(b["date"]["value"])

        time.sleep(0.5)

    return result

# --------------------------
# Labels
# --------------------------
def fetch_labels(uris):
    labels = {}

    for batch in chunked(list(uris), 25):
        values = " ".join(f"<{u}>" for u in batch)

        query = f"""
        SELECT ?item ?itemLabel WHERE {{
          VALUES ?item {{ {values} }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        """

        data = run_sparql(query)
        if not data:
            continue

        for b in data["results"]["bindings"]:
            uri = b["item"]["value"]
            label = b["itemLabel"]["value"]
            labels[uri] = label

        time.sleep(0.5)

    return labels

# --------------------------
# Wikipedia intro (batched)
# --------------------------
def fetch_wikipedia_titles_batch(uris, max_words=100):
    """
    Batch step 1: one SPARQL query per 50 events to get Wikipedia article titles.
    Returns {uri: title_string}
    """
    titles = {}
    for batch in chunked(list(uris), 50):
        values = " ".join(f"<{u}>" for u in batch)
        query = f"""
        SELECT ?item ?article WHERE {{
          VALUES ?item {{ {values} }}
          ?article <http://schema.org/about> ?item ;
                   <http://schema.org/isPartOf> <https://en.wikipedia.org/> .
        }}
        """
        data = run_sparql(query, max_retries=3, timeout=15)
        if not data:
            continue
        for b in data["results"]["bindings"]:
            uri = b["item"]["value"]
            title = b["article"]["value"].split("/")[-1]
            titles[uri] = title
        time.sleep(1)
    return titles


def fetch_wikipedia_summaries_batch(uri_to_title, max_words=100):
    """
    Batch step 2: Wikipedia action=query supports up to ~20 titles per request.
    Returns {uri: summary_string}
    """
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
            # handle redirect title normalisation
            redirects = {d["from"]: d["to"]
                         for d in r.json().get("query", {}).get("redirects", [])}
            normalized = {d["from"]: d["to"]
                          for d in r.json().get("query", {}).get("normalized", [])}

            for _, page in pages.items():
                if page.get("missing") == "":
                    continue
                page_title = page.get("title", "")
                extract = re.sub(r"<[^>]+>", "", page.get("extract", "")).strip()
                if not extract:
                    continue
                # resolve back through redirects/normalization to original title
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

def upgrade_important_nodes_json(input_file):
    path = os.path.join(os.path.dirname(input_file), "important_nodes.json")
    if not os.path.exists(path):
        print("important_nodes.json not found")
        return

    with open(path, "r") as f:
        data = json.load(f)

    # already upgraded → skip
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        print("JSON already upgraded")
        return

    uris = data
    uris = clean_uris(uris)

    print("Fetching labels...")
    labels = fetch_labels(uris)

    upgraded = []
    for uri in uris:
        name = labels.get(uri, uri.split("/")[-1])
        upgraded.append({
            "uri": uri,
            "name": name
        })

    # overwrite file
    with open(path, "w") as f:
        json.dump(upgraded, f, indent=2)

    print("important_nodes.json updated.")

# --------------------------
# MAIN
# --------------------------
def build_ng_wikidata_online(input_file, output_file):

    upgrade_important_nodes_json(input_file)

    print("Enrichment...")
    df = pd.read_csv(input_file)


    g = Graph()
    g.bind("sem", SEM)
    g.bind("ng", NG)

    all_nodes = set(df["subject"]).union(set(df["object"]))

    #print("Detecting events...")
    event_uris = get_events_set(all_nodes)

    #print("Fetching event info...")
    event_info = get_events_info(event_uris)

    #print("Collecting nodes for labels...")
    nodes_to_label = set(all_nodes)

    for e, info in event_info.items():
        nodes_to_label.update(info["actors"])
        nodes_to_label.update(info["places"])

    #print("Fetching labels...")
    labels = fetch_labels(nodes_to_label)

    #print("Fetching Wikipedia descriptions (batched)...")
    uri_to_title = fetch_wikipedia_titles_batch(event_uris)
    descriptions = fetch_wikipedia_summaries_batch(uri_to_title)

    # --------------------------
    # Structure
    # --------------------------
    #print("Building structure...")
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
    output_ttl = "/home/kallas/project/graph_search_framework/experiments/2026-04-28-08_47_05-informed_wikidata_french_revolution_2_pred_object_freq_domain_range__where_when__without_category_uri_iter__max_inf/li_huwe.ttl"

    build_ng_wikidata_online(input_csv, output_ttl)