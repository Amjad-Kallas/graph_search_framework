from SPARQLWrapper import SPARQLWrapper, JSON

sparql = SPARQLWrapper("https://dbpedia.org/sparql")

query = """
SELECT ?event WHERE {
  <http://dbpedia.org/resource/French_Revolution> ?p ?event .
  ?event rdf:type dbo:Event .
}
LIMIT 20
"""

sparql.setQuery(query)
sparql.setReturnFormat(JSON)
results = sparql.query().convert()

events = [r["event"]["value"] for r in results["results"]["bindings"]]
print(events)
