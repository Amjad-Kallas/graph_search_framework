from rdflib import Graph
from collections import defaultdict
from urllib.parse import unquote

import os
import json
import re


# --------------------------
# Utils
# --------------------------

def normalize_name(name):
    return re.sub(r'[^a-zA-Z0-9]+', '_', name).strip('_')


def truncate_description(desc, word_limit=50):
    """
    Truncate description at next period after word_limit words.
    If total words <= word_limit, return entire description.
    """
    words = desc.split()
    
    if len(words) <= word_limit:
        return desc
    
    # Find the period after the word_limit threshold
    current_text = ""
    for i, word in enumerate(words):
        current_text += word + " "
        
        if i >= word_limit - 1 and word.endswith('.'):
            return current_text.strip()
    
    # If no period found after word_limit, return up to word_limit words
    return " ".join(words[:word_limit]) + "."


def load_important_event_names(input_ttl):
    path = os.path.join(os.path.dirname(input_ttl), "important_nodes.json")
    if not os.path.exists(path):
        return set()

    with open(path, "r") as f:
        data = json.load(f)

    return set(normalize_name(item["name"]) for item in data)


# --------------------------
# Extract event names
# --------------------------

def extract_event_names(input_ttl, output_txt):

    g = Graph()
    g.parse(input_ttl, format="ttl")

    events = set()

    for s, p, o in g:
        p = str(p)

        if "type" in p and "Event" in str(o):
            events.add(s)

    if not events:
        events = {s for s, _, _ in g}

    names = []
    for e in events:
        name = unquote(str(e).split("/")[-1]).replace("_", " ")
        names.append(name)

    names = sorted(set(names))

    with open(output_txt, "w", encoding="utf-8") as f:
        for name in names:
            f.write(name + "\n")

    print("====\nEvent names file created successfully!")


# --------------------------
# Main parser
# --------------------------

def parse_rdf(input_ttl, output_txt, max_events=30):

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
            truncated = truncate_description(desc)
            if not truncated.endswith('.'):
                truncated += '.'
            line += f" — {truncated}"

        timeline.append((date, line))

    # --------------------------
    # Sort timeline
    # --------------------------

    timeline.sort(key=lambda x: x[0] if x[0] != "Unknown" else "9999-12-31")

    # --------------------------
    # Load important events
    # --------------------------

    important_names = load_important_event_names(input_ttl)

    important_events = []
    normal_events = []

    for date, line in timeline:
        try:
            name_part = line.split("—")[1].strip()
        except IndexError:
            name_part = ""

        norm_name = normalize_name(name_part)

        if norm_name in important_names:
            important_events.append((date, line))
        else:
            normal_events.append((date, line))

    # --------------------------
    # Selection logic
    # --------------------------

    selected = important_events.copy()
    remaining_slots = max_events - len(selected)

    if remaining_slots > 0:
        if len(normal_events) <= remaining_slots:
            selected += normal_events
        else:
            if remaining_slots == 1:
                selected.append(normal_events[len(normal_events) // 2])
            else:
                step = (len(normal_events) - 1) / (remaining_slots - 1)
                indices = [round(i * step) for i in range(remaining_slots)]
                selected += [normal_events[i] for i in indices]

    # Final sort (keep chronological order)
    selected.sort(key=lambda x: x[0] if x[0] != "Unknown" else "9999-12-31")

    timeline_lines = [line for _, line in selected]

    # --------------------------
    # Save timeline
    # --------------------------

    with open(output_txt, "w", encoding="utf-8") as f:
        for line in timeline_lines:
            f.write(line + "\n")

    # --------------------------
    # Save event names
    # --------------------------

    event_names_file = os.path.join(os.path.dirname(output_txt), "events_list.txt")
    extract_event_names(input_ttl, event_names_file)

    print("====\nParsing finished successfully!")


if __name__ == "__main__":
    #input_ttl_path = "/home/kallas/project/graph_search_framework/src/amjad/generation_ng.ttl"
    #output_txt_path = "/home/kallas/project/graph_search_framework/src/amjad/temp_event_timeline.txt"
    parse_rdf(input_ttl_path, output_txt_path)