import pandas as pd
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, XSD
from SPARQLWrapper import SPARQLWrapper, JSON
from urllib.parse import quote
from tqdm import tqdm
import argparse
import requests

SEM = Namespace("http://semanticweb.cs.vu.nl/2009/11/sem/")
DBR = Namespace("http://dbpedia.org/resource/")

def load_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

def get_event_info(event_uri):
    sparql = SPARQLWrapper("https://dbpedia.org/sparql")

    query = f"""
    SELECT ?actor ?place ?date WHERE {{
      OPTIONAL {{ <{event_uri}> dbo:commander ?actor . }}
      OPTIONAL {{ <{event_uri}> dbo:place ?place . }}
      OPTIONAL {{ <{event_uri}> dbo:date ?date . }}
    }}
    LIMIT 20
    """

    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    actors, places, dates = [], [], []

    for r in results["results"]["bindings"]:
        if "actor" in r:
            actors.append(r["actor"]["value"])
        if "place" in r:
            places.append(r["place"]["value"])
        if "date" in r:
            dates.append(r["date"]["value"])

    return actors, places, dates


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
    if "isPartOfMilitaryConflict" in pred:
        return SEM.subEventOf
    return None

def build_ng(input_file, output_file):
    df = pd.read_csv(input_file)

    g = Graph()
    g.bind("sem", SEM)
    g.bind("dbr", DBR)

    event_cache = {}
    wiki_cache = {}



    for _, row in tqdm(df.iterrows(), total=len(df)):
        s = encode(row["subject"])
        o = URIRef(encode(row["object"]))
        pred = row["predicate"]

        # Add event type
        g.add((s, RDF.type, SEM.Event))

        # Map predicate
        mapped = map_predicate(pred)
        if mapped:
            g.add((s, mapped, o))

        # ---- ENRICHMENT (cached) ----
        event_uri = row["subject"]

        if event_uri not in event_cache:
            event_cache[event_uri] = get_event_info(event_uri)

        actors, places, dates = event_cache[event_uri]

        for a in actors:
            g.add((s, SEM.hasActor, encode(a)))

        for p in places:
            g.add((s, SEM.hasPlace, encode(p)))

        best_date = select_best_date(dates)

        if best_date:
            g.set((s, SEM.hasTimeStamp, Literal(best_date, datatype=XSD.date)))

        # ---- WIKIPEDIA ENRICHMENT ----
        if event_uri not in wiki_cache:
            wiki_cache[event_uri] = get_wikipedia_intro(event_uri, max_words=100)

        desc = wiki_cache[event_uri]

        if desc:
            from rdflib.namespace import RDFS
            g.add((s, RDFS.comment, Literal(desc)))

        # ---- FALLBACK TIME ----
        if not best_date and len(row) >= 7:
            year = str(row.iloc[-1])
            if year.isdigit():
                date = f"{year}-01-01"
                g.set((s, SEM.hasTimeStamp,
                    Literal(date, datatype=XSD.date)))


    g.serialize(output_file, format="ttl")
    #print(f"Saved to {output_file}")
    print(f"====\nNarrative graph built successfully!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert Generated Subgraph into NG with enrichment."
    )

    parser.add_argument(
        "--input_subgraph",
        required=True,
        help="Path to the input subgraph."
    )


    parser.add_argument(
        "--output_ng",
        required=True,
        help="output narrative graph."
    )

    args = parser.parse_args()

    # --- Load inputs ---
    input_subgraph = load_text(args.input_subgraph)

    build_ng(args.input_subgraph, args.output_ng)