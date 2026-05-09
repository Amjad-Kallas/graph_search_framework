"""
Functions for the manual event-selection flow.
Nothing here modifies existing pipeline functions — these are standalone.
"""

import os
import json
from urllib.parse import unquote


# ── Step 1: run pipeline up to post_filtering ─────────────────────────────────

def run_pipeline_until_graph(
    config_path,
    mode="search_type_node_metrics",
    node_selection="all",
    end_node="",
    walk="informed",
    interface=None,
):
    """
    Run the pipeline up to and including apply_post_filtering.
    Returns (target_folder, output_ng_path, main_event).
    """
    from src.run_pipeline import run_framework
    from src.build_ng.custom_generic_kb_to_ng_wikidata import build_ng_wikidata_hdt
    from src.build_ng.post_filtering import apply_post_filtering
    from src.hdt_interface import HDTInterface
    from src.wikidata_subgraph_to_readable import get_single_label

    with open(config_path, "r", encoding="utf-8") as f:
        config_loaded = json.load(f)

    config_interface = config_loaded.get("type_interface", "sparql_endpoint").lower()
    final_interface = interface if interface else config_interface
    print(f"Configuration loaded. Interface: {final_interface.upper()}")

    HDTInterface()

    args_main = {
        "mode": mode,
        "node_selection": node_selection,
        "end_node": end_node,
        "walk": walk,
    }

    print("\n1. Running ChronoGrapher...")
    target_folder, subgraph_file = run_framework(args_main, config_loaded)

    output_ng = os.path.join(target_folder, "output_ng.ttl")
    hdt_folder = "/home/kallas/project/graph_search_framework/wikidata_dataset"

    print("\n2. Building narrative graph...")
    build_ng_wikidata_hdt(subgraph_file, hdt_folder, output_ng)

    main_event = config_loaded.get("start_name") or get_single_label(config_loaded["start"])
    apply_post_filtering(output_ng, config_loaded, main_event)

    print("\nGraph ready — waiting for event selection.")
    return target_folder, output_ng, main_event


# ── Step 1b: read event names from TTL ────────────────────────────────────────

def get_events_from_ttl(ttl_path):
    """Return a sorted list of event display names from the TTL."""
    from rdflib import Graph, Namespace, RDF
    SEM = Namespace("http://semanticweb.cs.vu.nl/2009/11/sem/")

    g = Graph()
    g.parse(ttl_path, format="turtle")

    names = []
    for ev in g.subjects(RDF.type, SEM.Event):
        name = unquote(str(ev).split("/")[-1]).replace("_", " ")
        names.append(name)

    return sorted(set(names))


# ── Step 2: build timeline from selected events ────────────────────────────────

def build_timeline_from_selection(ttl_path, selected_names, output_txt):
    """
    Write selected_names to selected_events_combined.txt (which parse_rdf already
    knows how to read), then call parse_rdf directly to build the timeline.
    """
    from src.amjad.parse_rdf import parse_rdf

    # parse_rdf filters by this file when it exists
    selected_file = os.path.join(os.path.dirname(ttl_path), "selected_events_combined.txt")
    with open(selected_file, "w", encoding="utf-8") as f:
        for name in selected_names:
            f.write(name + "\n")

    parse_rdf(ttl_path, output_txt)
    print(f"Timeline ({len(selected_names)} events selected) written to {output_txt}")


# ── Step 3: generate story from timeline ──────────────────────────────────────

def generate_story_manual(timeline_file, main_event, target_words=700):
    """
    Generate a story from the manually-built timeline.
    Returns (story_text, story_file_path).
    """
    from openai import OpenAI
    from src.amjad.config import EURECOM_URL, MY_API

    with open(timeline_file, "r", encoding="utf-8") as f:
        context = f.read()

    prompt = f"""You are a storytelling agent writing a narrative of {main_event} for a general audience.

Writing style:
- The primary goal is to be clear, accurate, and informative without losing engagement focus.
- Write in continuous paragraphs — no headers, bullet points, bold text, or markdown formatting.
- Keep an educational tone but go beyond a simple report of events. A light narrative quality is welcome (smooth transitions, causal explanations), but limit dramatic flourishes, literary scenes, and emotional language.
- Explain why events happened, not just what happened.

Use of provided events:
- The events below are your chronological guide. Follow their general sequence.
- You are free to skip events that do not serve your narrative goals.
- Add essential historical context where needed to keep the account coherent.

Length: Write approximately {target_words} words. The account must be complete — do not end mid-sentence.

Events (chronological guide):
{context}"""

    client = OpenAI(base_url=EURECOM_URL, api_key=MY_API)
    response = client.chat.completions.create(
        model="Qwen/Qwen3-30B-A3B-Thinking-2507",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6,
        max_tokens=int(target_words * 4),
    )
    story = response.choices[0].message.content

    folder = os.path.dirname(timeline_file)
    story_file = os.path.join(folder, "generated_story_manual.txt")
    with open(story_file, "w", encoding="utf-8") as f:
        f.write(story)

    print(f"Story saved to {story_file}")
    return story, story_file
