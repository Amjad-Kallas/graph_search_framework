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


def truncate_description(desc, word_limit=30):
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


def load_selected_event_names(input_ttl):
    path = os.path.join(os.path.dirname(input_ttl), "selected_events_combined.txt")
    if not os.path.exists(path):
        return None  # None = no filter, use all events

    names = set()
    with open(path, "r") as f:
        for line in f:
            name = line.strip()
            if name:
                names.add(normalize_name(name))
    return names


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

    # Collect all event URIs from the TTL first
    event_uris = set()
    for s, p, o in g:
        if "type" in str(p) and "Event" in str(o):
            event_uris.add(s)
    if not event_uris:
        event_uris = {s for s, _, _ in g}

    events = {uri: {"date": None, "places": set(), "actors": set(), "desc": None}
              for uri in event_uris}

    for s, p, o in g:
        if s not in events:
            continue
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

    # --------------------------
    # Filter to selected events
    # --------------------------

    selected_names = load_selected_event_names(input_ttl)

    if selected_names is not None:
        events = {uri: info for uri, info in events.items()
                  if normalize_name(unquote(str(uri).split("/")[-1]).replace("_", " ")) in selected_names}

    # --------------------------
    # Build timeline
    # --------------------------

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

    timeline.sort(key=lambda x: x[0] if x[0] != "Unknown" else "9999-12-31")

    timeline_lines = [line for _, line in timeline]

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
    input_ttl_path = "/home/kallas/project/graph_search_framework/experiments/2026-05-02-20_19_01-informed_wikidata_french_revolution_10_pred_object_freq_domain_range___when__without_category_uri_iter__max_inf/output_ng.ttl"
    output_txt_path = "/home/kallas/project/graph_search_framework/experiments/2026-05-02-20_19_01-informed_wikidata_french_revolution_10_pred_object_freq_domain_range___when__without_category_uri_iter__max_inf/temp_event_timeline.txt"
    parse_rdf(input_ttl_path, output_txt_path)