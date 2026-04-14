import pandas as pd
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, XSD, RDFS
from urllib.parse import quote
from tqdm import tqdm
import requests
from uuid import uuid4

from src.hdt_interface import HDTInterface


# Namespaces
SEM = Namespace("http://semanticweb.cs.vu.nl/2009/11/sem/")
DBR = Namespace("http://dbpedia.org/resource/")


# -------------------------
# Helpers
# -------------------------

def encode(uri):
    uri = str(uri).strip()
    if uri.startswith("http://dbpedia.org/resource/"):
        base = "http://dbpedia.org/resource/"
        name = uri[len(base):]
        name = quote(name)
        return URIRef(base + name)
    return URIRef(uri)


def get_wikipedia_intro(event_uri, max_words=50):
    try:
        title = quote(event_uri.split("/")[-1])
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"

        headers = {
            "User-Agent": "KG-Narrative-Project/1.0"
        }

        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()

        if "extract" in data:
            text = data["extract"]
            return " ".join(text.split()[:max_words])
    except:
        return None

    return None


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


# -------------------------
# HDT enrichment (NO SPARQL)
# -------------------------

def get_event_info_hdt(event_uri, hdt_interface):

    actor_preds = [
        "http://dbpedia.org/ontology/commander",
        "http://dbpedia.org/ontology/combatant",
        "http://dbpedia.org/ontology/participant"
    ]

    place_preds = [
        "http://dbpedia.org/ontology/place",
        "http://dbpedia.org/ontology/location"
    ]

    date_preds = [
        "http://dbpedia.org/ontology/date",
        "http://dbpedia.org/ontology/startDate",
        "http://dbpedia.org/ontology/endDate"
    ]

    actors, places, dates = [], [], []

    for p in actor_preds:
        for _, _, o in hdt_interface.get_triples(subject=event_uri, predicate=p):
            actors.append(o)

    for p in place_preds:
        for _, _, o in hdt_interface.get_triples(subject=event_uri, predicate=p):
            places.append(o)

    for p in date_preds:
        for _, _, o in hdt_interface.get_triples(subject=event_uri, predicate=p):
            dates.append(hdt_interface.clean_hdt_object(o))

    return actors, places, dates


# -------------------------
# Event creation
# -------------------------

def create_event(graph, actor_uri, label):
    event_uri = URIRef(f"{actor_uri}_{label}_{uuid4().hex[:6]}")
    graph.add((event_uri, RDF.type, SEM.Event))
    graph.add((event_uri, SEM.hasActor, actor_uri))
    return event_uri


# -------------------------
# Main NG builder
# -------------------------

def build_ng(input_file, output_file, hdt_interface):

    df = pd.read_csv(input_file)

    g = Graph()
    g.bind("sem", SEM)
    g.bind("dbr", DBR)

    event_cache = {}
    wiki_cache = {}

    for _, row in tqdm(df.iterrows(), total=len(df)):

        subject_uri = row["subject"]
        object_uri = row["object"]
        predicate = row["predicate"]

        # Skip non DBpedia objects
        if not str(object_uri).startswith("http://dbpedia.org/resource/") \
           and not str(object_uri).isdigit():
            continue

        s = encode(subject_uri)

        # PERSON = Actor
        g.add((s, RDF.type, SEM.Actor))

        # -------------------------
        # Create EVENTS from facts
        # -------------------------

        # Birth
        if "birthDate" in predicate:
            e = create_event(g, s, "birth")
            g.add((e, SEM.hasTimeStamp,
                   Literal(object_uri, datatype=XSD.date)))

        # Death
        elif "deathDate" in predicate:
            e = create_event(g, s, "death")
            g.add((e, SEM.hasTimeStamp,
                   Literal(object_uri, datatype=XSD.date)))

        # Birth place
        elif "birthPlace" in predicate:
            e = create_event(g, s, "birth_place")
            g.add((e, SEM.hasPlace, encode(object_uri)))

        # Death place
        elif "deathPlace" in predicate:
            e = create_event(g, s, "death_place")
            g.add((e, SEM.hasPlace, encode(object_uri)))

        # Award
        elif "award" in predicate:
            e = create_event(g, s, "award")
            g.add((e, SEM.hasPlace, encode(object_uri)))

        # Known for
        elif "knownFor" in predicate:
            e = create_event(g, s, "achievement")
            g.add((e, SEM.subEventOf, encode(object_uri)))

        # Spouse
        elif "spouse" in predicate:
            e = create_event(g, s, "marriage")
            g.add((e, SEM.hasActor, encode(object_uri)))

        # -------------------------
        # HDT enrichment (cached)
        # -------------------------

        if subject_uri not in event_cache:
            event_cache[subject_uri] = get_event_info_hdt(subject_uri, hdt_interface)

        actors, places, dates = event_cache[subject_uri]

        for a in actors:
            g.add((s, SEM.hasActor, encode(a)))

        for p in places:
            g.add((s, SEM.hasPlace, encode(p)))

        best_date = select_best_date(dates)

        if best_date:
            g.set((s, SEM.hasTimeStamp,
                   Literal(best_date, datatype=XSD.date)))

        if str(object_uri).startswith("http://dbpedia.org/resource/"):

            if object_uri not in wiki_cache:
                wiki_cache[object_uri] = get_wikipedia_intro(object_uri, max_words=50)

            desc = wiki_cache[object_uri]

            if desc:
                g.add((encode(object_uri), RDFS.comment, Literal(desc)))

        # -------------------------
        # Wikipedia enrichment
        # -------------------------

        if subject_uri not in wiki_cache:
            wiki_cache[subject_uri] = get_wikipedia_intro(subject_uri)

        desc = wiki_cache[subject_uri]

        if desc:
            g.add((s, RDFS.comment, Literal(desc)))

    # Save graph
    g.serialize(output_file, format="ttl")
    print("====\nNarrative graph built successfully!")


# -------------------------
# Run
# -------------------------

if __name__ == "__main__":

    input_subgraph = "/home/kallas/project/graph_search_framework/einstein_triples.csv"
    output_ng = "/home/kallas/project/graph_search_framework/einstein_ng.ttl"

    interface = HDTInterface()

    build_ng(input_subgraph, output_ng, interface)