import os
import argparse
import json

from src.framework import GraphSearchFramework

from src.build_ng.custom_generic_kb_to_ng import build_ng
from src.amjad.parse_rdf import parse_rdf
from src.amjad.generate_story import generate_story
from src.amjad.evaluate_story import evaluate_story

def run_framework():
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
    args_main = vars(ap.parse_args())

    compute_score = False
    if args_main["compute_score"]:
        compute_score = True

    with open(args_main["json"], "r", encoding="utf-8") as openfile_main:
        config_loaded = json.load(openfile_main)
    
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

    return target_folder, target_file, compute_score





def run_pipeline():

    temp_ground_truh = "/home/kallas/project/graph_search_framework/src/amjad/paper.txt"
    
    print("\n1. Running ChronoGrapher...")
    target_folder, subgraph_file, compute_score = run_framework()

    output_ng = target_folder + f"/output_ng.ttl"
    timeline_file = target_folder + f"/event_timeline.txt"
    
    print("\n2. Building narrative graph...")
    build_ng(subgraph_file, output_ng)

    print("\n3. Parsing RDF...")

    #output_ng = "/home/kallas/project/graph_search_framework/experiments/2026-03-21-20_12_42-informed_dbpedia_french_revolution_1_pred_object_freq_domain_range_what_where_when_who_wikilink_without_category_uri_iter__max_inf/output_ng.ttl"
    #timeline_file = "/home/kallas/project/graph_search_framework/experiments/2026-03-21-20_12_42-informed_dbpedia_french_revolution_1_pred_object_freq_domain_range_what_where_when_who_wikilink_without_category_uri_iter__max_inf/event_timeline.txt"

    parse_rdf(output_ng, timeline_file)

    print("\n4. Generating story...")
    story, story_file = generate_story(timeline_file)

    print("\n--- STORY ---")
    print(story)

    # delete me
    compute_score = True
    if compute_score:
        print("\n5. Computing story score...")
        evaluate_story(story_file, temp_ground_truh)
    

if __name__ == "__main__":
    run_pipeline()