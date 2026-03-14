from SPARQLWrapper import SPARQLWrapper, JSON


def get_events():
  sparql = SPARQLWrapper("https://query.wikidata.org/sparql")

  query = """
  PREFIX wd: <http://www.wikidata.org/entity/>
  PREFIX wdt: <http://www.wikidata.org/prop/direct/>

  SELECT ?event ?eventLabel WHERE {
    ?event ?p wd:Q6534 .
    ?event wdt:P31/wdt:P279* wd:Q1656682 .

    SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
  }
  LIMIT 100
  """

  sparql.addCustomHttpHeader("User-Agent", "KG-research-project/1.0")

  sparql.setQuery(query)
  sparql.setReturnFormat(JSON)

  results = sparql.query().convert()

  events = [r["event"]["value"] for r in results["results"]["bindings"]]


  # now we get useful properties from these IDs:
  # query Wikidata again for each event to get event name, point in time, start/end time, location, ...

  results = sparql.query().convert()


  # remove duplicates
  events = list(set(events))

  # extract QIDs
  qids = [e.split("/")[-1] for e in events]

  # build VALUES clause
  values = " ".join([f"wd:{q}" for q in qids])

  query = f"""
  PREFIX wd: <http://www.wikidata.org/entity/>
  PREFIX wdt: <http://www.wikidata.org/prop/direct/>

  SELECT ?event ?eventLabel ?date WHERE {{

    VALUES ?event {{ {values} }}

    OPTIONAL {{ ?event wdt:P585 ?date }}
    OPTIONAL {{ ?event wdt:P580 ?date }}

    SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}

  }}
  """

  sparql = SPARQLWrapper("https://query.wikidata.org/sparql")
  sparql.addCustomHttpHeader("User-Agent", "research-project/1.0")
  sparql.setQuery(query)
  sparql.setReturnFormat(JSON)

  results = sparql.query().convert()

  timeline = []

  # print(results)

  for r in results["results"]["bindings"]:
      label = r["eventLabel"]["value"]
      date = r.get("date", {}).get("value", None)
      timeline.append((date, label))

  # sort by date
  timeline = sorted([t for t in timeline if t[0] is not None])

  '''for t in timeline:
      print(t)'''


  clean_timeline = []

  for date, label in timeline:

      # remove items without real labels
      if label.startswith("Q"):
          continue

      # keep only revolution period
      year = int(date[:4])

      if 1785 <= year <= 1805:
          clean_timeline.append((date, label))
    
  timeline_clean = [(d[:4], l) for d,l in clean_timeline]
  timeline_clean.sort()  # sort by year

  # print(timeline_clean)

  events = [ {"date": d, "event": l} for d,l in timeline_clean]

  return events


get_events()