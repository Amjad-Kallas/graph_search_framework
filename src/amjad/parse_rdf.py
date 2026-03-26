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
    if len(timeline) <= max_events:
        selected = timeline
    else:
        step = (len(timeline) - 1) / (max_events - 1)
        indices = [round(i * step) for i in range(max_events)]
        selected = [timeline[i] for i in indices]

    timeline_lines = [line for _, line in selected]

    with open(output_txt, "w", encoding="utf-8") as f:
        for line in timeline_lines:
            f.write(line + "\n")


    print("====\nParsing finished successfully!")

if __name__ == "__main__":
    #input_ttl_path = "/home/kallas/project/graph_search_framework/src/amjad/generation_ng.ttl"
    #output_txt_path = "/home/kallas/project/graph_search_framework/src/amjad/temp_event_timeline.txt"
    parse_rdf(input_ttl_path, output_txt_path)