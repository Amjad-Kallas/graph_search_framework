# Parse ChronoGrapher TTL file → clean chronological event summaries for LLM

from rdflib import Graph
from collections import defaultdict
from urllib.parse import unquote

# -------- 1. Load RDF graph --------
g = Graph()
g.parse("generation_ng.ttl", format="ttl")

# -------- 2. Collect triples per event --------
events = defaultdict(lambda: {
    "date": None,
    "places": set(),
    "actors": set()
})

for s, p, o in g:
    p = str(p)

    if "hasBeginTimeStamp" in p:
        events[s]["date"] = str(o)

    elif "hasPlace" in p:
        place = unquote(str(o).split("/")[-1]).replace("_", " ")
        events[s]["places"].add(place)

    elif "hasActor" in p:
        actor = unquote(str(o).split("/")[-1]).replace("_", " ")
        events[s]["actors"].add(actor)

# -------- 3. Build timeline summaries --------
timeline = []

for event, info in events.items():

    name = unquote(str(event).split("/")[-1]).replace("_", " ")
    date = info["date"] if info["date"] else "Unknown"

    places = ", ".join(sorted(info["places"]))
    actors = ", ".join(sorted(info["actors"]))

    line = f"{date} — {name}"

    if places:
        line += f" — Place: {places}"

    if actors:
        line += f" — Actors: {actors}"

    timeline.append((date, line))

# -------- 4. Sort chronologically --------
timeline.sort(key=lambda x: x[0] if x[0] != "Unknown" else "9999")

timeline_lines = [line for _, line in timeline]

# -------- 5. Save cleaned context for LLM --------
i = 0
with open("event_timeline.txt", "w", encoding="utf-8") as f:
    for line in timeline_lines:
        f.write(line + "\n")
        i += 1
        if (i == 20):
            break

'''
# -------- 6. Example prompt input --------
context = "\n".join(timeline_lines)

prompt = f"""
You are given a set of historical events extracted from a knowledge graph.

Write a coherent historical narrative describing the sequence of events.
Explain the main developments and present them chronologically.

Events:
{context}
"""

print(prompt[:2000])  # preview first part of prompt'''