import pandas as pd
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, XSD
from SPARQLWrapper import SPARQLWrapper, JSON


SEM = Namespace("http://semanticweb.cs.vu.nl/2009/11/sem/")
DBR = Namespace("http://dbpedia.org/resource/")


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

from urllib.parse import quote

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

    for _, row in df.iterrows():
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
            g.add((s, SEM.hasActor, URIRef(a)))

        for p in places:
            g.add((s, SEM.hasPlace, URIRef(p)))

        for d in dates:
            g.add((s, SEM.hasBeginTimeStamp,
                Literal(d[:10], datatype=XSD.date)))
            g.add((s, SEM.hasEndTimeStamp,
                Literal(d[:10], datatype=XSD.date)))

        # ---- FALLBACK TIME ----
        if len(row) >= 7:
            year = str(row.iloc[-1])
            if year.isdigit():
                date = f"{year}-01-01"
                g.add((s, SEM.hasBeginTimeStamp,
                    Literal(date, datatype=XSD.date)))
                g.add((s, SEM.hasEndTimeStamp,
                    Literal(date, datatype=XSD.date)))


    g.serialize(output_file, format="ttl")
    print(f"Saved to {output_file}")


if __name__ == "__main__":
    build_ng("kg-example/dummy_output_search.csv", "search_ng.ttl")