import os
import argparse
import json

from src.framework import GraphSearchFramework

from src.build_ng.custom_generic_kb_to_ng_hdt import build_ng as build_ng_hdt
from src.build_ng.custom_generic_kb_to_ng import build_ng as build_ng_sparql
from src.build_ng.custom_generic_kb_to_ng_wikidata import build_ng_wikidata_hdt
from src.build_ng.custom_generic_kb_to_ng_wikidata_online import build_ng_wikidata_online
from src.amjad.parse_rdf import parse_rdf
from src.amjad.generate_story import generate_story, generate_story_baseline
from src.amjad.evaluate_story import evaluate_story
from src.amjad.pruning import StoryCentralityPruner
from src.build_ng.post_filtering import apply_post_filtering
from src.hdt_interface import HDTInterface

from src.wikidata_subgraph_to_readable import fetch_all_labels, get_single_label

from src.amjad.llm_pruning import rerank_events_combined

def run_framework(args_main, config_loaded):

    num_iterations = config_loaded.get("iterations")

    if "rdf_type" in config_loaded:
        config_loaded["rdf_type"] = list(config_loaded["rdf_type"].items())

    framework = GraphSearchFramework(
        config=config_loaded,
        mode=args_main["mode"],
        node_selection=args_main["node_selection"],
        walk=args_main["walk"]
    )

    print("Executing Graph Search Framework via new pipeline script...")

    target_folder = framework(end_node=args_main["end_node"])

    print(f"Framework finished successfully!\n")
    print(f"Data is saved in: {target_folder}")


    target_file = os.path.join(target_folder, f"{num_iterations}-subgraph.csv")

    return target_folder, target_file


def run_pipeline_direct(
    config_path,
    mode="search_type_node_metrics",
    node_selection="all",
    end_node="",
    walk="informed",
    interface=None,
):
    """
    Importable, exit()-free version of the pipeline for use in the Streamlit app.
    Returns (target_folder, timeline_file).
    """
    with open(config_path, "r", encoding="utf-8") as f:
        config_loaded = json.load(f)

    config_interface = config_loaded.get("type_interface", "sparql_endpoint").lower()
    final_interface = interface if interface else config_interface

    print(f"Configuration loaded. Interface set to: {final_interface.upper()}")

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
    timeline_file = os.path.join(target_folder, "event_timeline.txt")
    hdt_folder = "/home/kallas/project/graph_search_framework/wikidata_dataset"

    print("\n2. Building narrative graph...")
    build_ng_wikidata_hdt(subgraph_file, hdt_folder, output_ng)

    main_event = config_loaded.get("start_name") or get_single_label(config_loaded["start"])

    apply_post_filtering(output_ng, config_loaded, main_event)

    print("\n3. Wikipedia + LLM Filtering...")
    rerank_events_combined(output_ng, main_event, target_k=35)

    print("\n4. Parsing RDF...")
    parse_rdf(output_ng, timeline_file)

    return target_folder, timeline_file


def run_pipeline():

    ap = argparse.ArgumentParser()
    ap.add_argument("-j", "--json", required=True,
                    help="Path to json file containing configuration file")
    ap.add_argument("-m", "--mode", default="search_type_node_metrics",
                    help="mode for the search")
    ap.add_argument("-n", "--node_selection", default="all",
                    help="node selection for the search")
    ap.add_argument("-e", "--end_node", default="",
                    help="node to look for in search (only if mode == 'search_specific_node'")
    ap.add_argument("-w", "--walk", default="informed",
                    help="type of walk in the graph: `random` or `informed`")
    ap.add_argument("--compute_score", action="store_true",
                    help="Evaluate story if flag is present")
    ap.add_argument("-i", "--interface", choices=["hdt", "sparql_endpoint"], default=None,
                    help="Override type_interface from config (choices: hdt, sparql_endpoint)")

    args_main = vars(ap.parse_args())
    compute_score = args_main["compute_score"]

    with open(args_main["json"], "r", encoding="utf-8") as openfile_main:
        config_loaded = json.load(openfile_main)

    config_interface = config_loaded.get("type_interface", "sparql_endpoint").lower()

    final_interface = args_main["interface"] if args_main["interface"] else config_interface

    use_hdt = (final_interface == "hdt")

    print(f"Configuration loaded. Interface set to: {final_interface.upper()}")

    """
    interface type is made such that the value (potentially) specified by the user dominates
    the value in the configuration file
    """


    interface = HDTInterface()

    print("\n1. Running ChronoGrapher...")
    target_folder, subgraph_file = run_framework(args_main, config_loaded)

    #fetch_all_labels(subgraph_file , subgraph_file[:-4]+"_readable.csv")


    '''# Pruning
    seed_topic = config_loaded["start"]
    pruner = StoryCentralityPruner()
    pruned_subgraph_file = pruner.run_pruning(subgraph_file, seed_topic=seed_topic)

    fetch_all_labels(pruned_subgraph_file , pruned_subgraph_file[:-4]+"_readable.csv")'''


    output_ng = target_folder + f"/output_ng.ttl"
    timeline_file = target_folder + f"/event_timeline.txt"

    hdt_folder = "/home/kallas/project/graph_search_framework/wikidata_dataset"

    print("\n2. Building narrative graph...")
    #build_ng_wikidata_online(subgraph_file, output_ng)
    build_ng_wikidata_hdt(subgraph_file, hdt_folder, output_ng)

    main_event = config_loaded.get("start_name") or get_single_label(config_loaded["start"])

    # Apply post filtering: remove events of "Q...", and the ones very outside the range, and without comment
    apply_post_filtering(output_ng, config_loaded, main_event)

    print("\n3. Wikipedia + LLM Filtering")

    rerank_events_combined(output_ng, main_event, target_k=35)

    print("\n3. Parsing RDF...")

    parse_rdf(output_ng, timeline_file)

    exit()
    print("\n4. Generating stories...")
    _, story_file    = generate_story(timeline_file, main_event)
    _, baseline_file = generate_story_baseline(target_folder, main_event)

    # compute story score if needed
    if compute_score:
        print("\n5. Computing story scores...")
        evaluate_story(story_file,    wiki_intro_file, output_path=os.path.join(target_folder, "score_event_driven.json"))
        wiki_intro_file = os.path.join(target_folder, f"wikipedia_intro_{main_event.replace(' ', '_')}.txt")
        evaluate_story(baseline_file, wiki_intro_file, output_path=os.path.join(target_folder, "score_baseline.json"))


if __name__ == "__main__":
    run_pipeline()
