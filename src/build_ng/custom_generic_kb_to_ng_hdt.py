import pandas as pd
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, XSD
from urllib.parse import quote
from tqdm import tqdm
import requests
from src.hdt_interface import HDTInterface


SEM = Namespace("http://semanticweb.cs.vu.nl/2009/11/sem/")
DBR = Namespace("http://dbpedia.org/resource/")

def load_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

def select_best_date(dates):
    best = None
    best_score = -1

    for d in dates:
        try:
            d = d[:10]
            year, month, day = d.split("-")

            score = 0
            if month != "01": score += 1
            if day != "01": score += 1

            if score > best_score:
                best_score = score
                best = d
        except:
            continue

    return best

def get_wikipedia_intro(event_uri, max_words=10):
    try:
        title = quote(event_uri.split("/")[-1])
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"

        headers = {
            "User-Agent": "KG-Narrative-Project/1.0 (email@example.com)"
        }

        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()

        if "extract" in data:
            text = data["extract"]
            words = text.split()
            return " ".join(words[:max_words])
    except Exception as e:
        print(e)
        return None

    return None

def encode(uri):
    uri = uri.strip()
    if uri.startswith("http://dbpedia.org/resource/"):
        base = "http://dbpedia.org/resource/"
        name = uri[len(base):]
        name = quote(name)  # encode special chars
        return URIRef(base + name)
    return URIRef(uri)

def map_predicate(pred):
    return URIRef(pred)

def build_ng(input_file, output_file, hdt_interface):
    df = pd.read_csv(input_file)

    g = Graph()
    g.bind("sem", SEM)
    g.bind("dbr", DBR)
    from rdflib.namespace import RDFS

    # Step 1: Map predicates and gather ALL unique event URIs
    all_event_uris = set()
    
    for _, row in df.iterrows():
        s_uri = row["subject"]
        o_uri = row["object"]
        pred  = row["predicate"]

        all_event_uris.add(s_uri)
        all_event_uris.add(o_uri)

        s = encode(s_uri)
        o = encode(o_uri)

        mapped = map_predicate(pred)
        if mapped:
            g.add((s, mapped, o))

    # Step 2: Enrich every unique event (no caches needed anymore!)
    print(f"Enriching {len(all_event_uris)} unique events...")
    
    for uri in tqdm(all_event_uris):
        node = encode(uri)
        g.add((node, RDF.type, SEM.Event))

        # ---- HDT ENRICHMENT ----
        actors, places, dates = hdt_interface.get_event_info(uri)

        '''for a in actors:
            g.add((node, SEM.hasActor, encode(a)))

        for p in places:
            g.add((node, SEM.hasPlace, encode(p)))

        best_date = select_best_date(dates)

        if best_date:
            g.set((node, SEM.hasTimeStamp, Literal(best_date, datatype=XSD.date)))
        else:
            g.set((node, SEM.hasTimeStamp, Literal("no_date")))

        # ---- WIKIPEDIA ENRICHMENT ----
        # (Make sure to uncomment your Wikipedia logic if you want the descriptions)
        desc = get_wikipedia_intro(uri, max_words=200)
        if desc:
            g.add((node, RDFS.comment, Literal(desc)))'''

    g.serialize(output_file, format="ttl")
    print("====\nNarrative graph built successfully!")

if __name__ == "__main__":
    input_subgraph = "/home/kallas/project/graph_search_framework/kg-example/output_search.csv"
    output_ng = "/home/kallas/project/graph_search_framework/kg-example/titi.ttl"

    interface = HDTInterface()

    build_ng(input_subgraph, output_ng, interface)