from rdflib import Graph, Namespace, RDF
from urllib.parse import unquote
from openai import OpenAI
from src.amjad.config import VLLM_URL, MODEL_NAME

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
import os
from rdflib import Namespace

RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
SEM = Namespace("http://semanticweb.cs.vu.nl/2009/11/sem/")

def save_events(events, path):
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(e + "\n")

    print(f"Saved {len(events)} events to {path}")


# ----------- STEP 1: Extract events -----------

def extract_events_from_ttl(file_path, main_event, output_file):
    g = Graph()
    g.parse(file_path, format="turtle")

    events = []

    for subj in g.subjects(RDF.type, SEM.Event):
        uri = str(subj)
        name = uri.split("/")[-1]
        name = unquote(name).replace("_", " ")



        events.append(name)

        # --- extract comment for main event ---
        if uri.endswith(main_event.replace(" ", "_")):
            for _, _, c in g.triples((subj, RDFS.comment, None)):
                main_comment = str(c)
                break

    save_events(events, output_file)

    return list(set(events)), main_comment[:600]  # remove duplicates


# ----------- STEP 2: LLM filtering -----------

MAX_EVENTS = 20     # target number after filtering

client = OpenAI(
    base_url=VLLM_URL,
    api_key="EMPTY"
)

# ---------- LLM FILTER ----------
def llm_filter_events(events, main_event, description):
    
    events_text = "\n".join(f"- {e}" for e in events)

    prompt = f"""
    You are given a list of events related to: {main_event}.

    Context:
    {description}

    Select events to form a clear, high-level historical timeline.

    STRICT RULE:
    - You MUST ONLY select events from the provided list.
    - Do NOT add or modify any event.

    Selection rules:
    - Select at most {MAX_EVENTS} events
    - Prefer events that are:
        * broad in scope (theatres, campaigns)
        * well-known or widely impactful
        * connected to many other events
    - Avoid events that are:
        * small-scale actions ("Action of ...")
        * very local or obscure battles
        * repetitive (many similar battles)

    Diversity rule:
    - Do NOT select many events of the same type
    - Prefer covering different regions and types of events

    Return ONLY the selected events.
    One event per line.
    Do not explain.

    EVENTS:
    {events_text}
    """



    print(prompt)

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    output = response.choices[0].message.content

    # ---------- PARSE ----------
    selected = []
    for line in output.split("\n"):
        line = line.strip().lstrip("-").strip()
        if line:
            selected.append(line)

    return selected



# ----------- MAIN -----------

if __name__ == "__main__":
    file_path = "/home/kallas/project/graph_search_framework/experiments/2026-04-14-16_41_29-informed_dbpedia_french_revolution_1_pred_object_freq_domain_range_what_where_when_who_wikilink_without_category_uri_iter__max_inf/output_ng.ttl"
    main_event = "World War I"

    output_file = "/home/kallas/project/graph_search_framework/experiments/2026-04-14-16_41_29-informed_dbpedia_french_revolution_1_pred_object_freq_domain_range_what_where_when_who_wikilink_without_category_uri_iter__max_inf/events.txt"

    events, description = extract_events_from_ttl(file_path, main_event, output_file)

    print(f"Extracted {len(events)} events")

    filtered_events = llm_filter_events(events, main_event, description=description)

    print(f"Filtered to {len(filtered_events)} events")

    save_events(filtered_events, "/home/kallas/project/graph_search_framework/experiments/2026-04-14-16_41_29-informed_dbpedia_french_revolution_1_pred_object_freq_domain_range_what_where_when_who_wikilink_without_category_uri_iter__max_inf/filtered_events.txt")