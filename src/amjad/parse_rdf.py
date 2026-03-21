# Parse ChronoGrapher TTL file → clean chronological event summaries for LLM


def parse_rdf(input_ttl, output_txt, max_events=20):
    from rdflib import Graph
    from collections import defaultdict
    from urllib.parse import unquote

    g = Graph()
    g.parse(input_ttl, format="ttl")

    events = defaultdict(lambda: {
        "date": None,
        "places": set(),
        "actors": set(),
        "desc": None
    })

    for s, p, o in g:
        p = str(p)

        if "hasTimeStamp" in p:
            events[s]["date"] = str(o).split("^^")[0]

        elif "hasPlace" in p:
            place = unquote(str(o).split("/")[-1]).replace("_", " ")
            events[s]["places"].add(place)

        elif "hasActor" in p:
            actor = unquote(str(o).split("/")[-1]).replace("_", " ")
            events[s]["actors"].add(actor)

        elif "comment" in p:
            events[s]["desc"] = str(o)

    timeline = []

    for event, info in events.items():
        name = unquote(str(event).split("/")[-1]).replace("_", " ")
        date = info["date"] if info["date"] else "Unknown"

        places = ", ".join(sorted(info["places"]))
        desc = info["desc"]

        line = f"{date} — {name}"

        if places:
            line += f" — {places}"

        if desc:
            line += f" — {desc.split('.')[0]}."

        timeline.append((date, line))

    timeline.sort(key=lambda x: x[0] if x[0] != "Unknown" else "9999-12-31")
    timeline_lines = [line for _, line in timeline[:max_events]]

    with open(output_txt, "w", encoding="utf-8") as f:
        for line in timeline_lines:
            f.write(line + "\n")


    print("====\nParsing finished successfully!")


'''
from rdflib import Graph
from collections import defaultdict
from urllib.parse import unquote
import re


# -------- 1. Load RDF graph --------
g = Graph()
g.parse("amjad_custom_search_ng.ttl", format="ttl")

# -------- 2. Collect triples per event --------
events = defaultdict(lambda: {
    "date": None,
    "places": set(),
    "actors": set(),
    "desc": None
})

for s, p, o in g:
    p = str(p)

    if "hasTimeStamp" in p:
        events[s]["date"] = str(o).split("^^")[0]

    elif "hasPlace" in p:
        place = unquote(str(o).split("/")[-1]).replace("_", " ")
        events[s]["places"].add(place)

    elif "hasActor" in p:
        actor = unquote(str(o).split("/")[-1]).replace("_", " ")
        events[s]["actors"].add(actor)

    elif "comment" in p:
        events[s]["desc"] = str(o)


# this function gets the descirption up to the first period "."
def get_first_sentence(text, max_words=None):
    if not text:
        return None

    # Remove datatype if present (just in case)
    text = str(text)

    # Extract up to first period
    match = re.search(r"(.+?\.)", text)
    if match:
        sentence = match.group(1)
    else:
        sentence = text  # fallback if no period

    # Optional word limit (safety)
    if max_words:
        words = sentence.split()
        sentence = " ".join(words[:max_words])

    return sentence.strip()

# -------- 3. Build timeline summaries --------
timeline = []

for event, info in events.items():

    name = unquote(str(event).split("/")[-1]).replace("_", " ")
    date = info["date"] if info["date"] else "Unknown"

    places = ", ".join(sorted(info["places"]))
    actors = ", ".join(sorted(info["actors"]))
    desc = info["desc"]

    line = f"{date} — {name}"

    if places:
        line += f" — Place: {places}"

    #if actors:
        #line += f" — Actors: {actors}"

    if desc:
        short_desc = get_first_sentence(desc, max_words=25)
        line += f" description: — {short_desc}"

    timeline.append((date, line))

# -------- 4. Sort chronologically --------
timeline.sort(key=lambda x: x[0] if x[0] != "Unknown" else "9999")

timeline_lines = [line for _, line in timeline]

# -------- 5. Save cleaned context for LLM --------event_timeline.txt
with open("event_timeline.txt", "w", encoding="utf-8") as f:
    for line in timeline_lines:
        f.write(line + "\n")
        



print("DONE - saved into event_timeline.txt.")'''