import os
import argparse
import json

from src.framework import GraphSearchFramework

from src.build_ng.custom_generic_kb_to_ng_hdt import build_ng as build_ng_hdt
from src.build_ng.custom_generic_kb_to_ng import build_ng as build_ng_sparql
from src.amjad.parse_rdf import parse_rdf
from src.amjad.generate_story import generate_story
from src.amjad.evaluate_story import evaluate_story

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
    ap.add_argument("-i", "--interface", choices=["hdt", "sparql"], default=None,
                    help="Override type_interface from config (choices: hdt, sparql)")

    args_main = vars(ap.parse_args())
    compute_score = args_main["compute_score"]

    with open(args_main["json"], "r", encoding="utf-8") as openfile_main:
        config_loaded = json.load(openfile_main)
    
    config_interface = config_loaded.get("type_interface", "sparql").lower()
    
    final_interface = args_main["interface"] if args_main["interface"] else config_interface
    
    use_hdt = (final_interface == "hdt")
    
    print(f"Configuration loaded. Interface set to: {final_interface.upper()}")

    """
    interface type is made such that the value (potentially) specified by the user dominates
    the value in the configuration file
    """


    temp_ground_truh = "/home/kallas/project/graph_search_framework/src/amjad/paper.txt"
    
    print("\n1. Running ChronoGrapher...")
    target_folder, subgraph_file = run_framework(args_main, config_loaded)

    output_ng = target_folder + f"/output_ng.ttl"
    timeline_file = target_folder + f"/event_timeline.txt"
        
    print("\n2. Building narrative graph...")
    if use_hdt:
        from src.hdt_interface import HDTInterface

        interface = HDTInterface()
        build_ng_hdt(subgraph_file, output_ng, interface)

    else: # use SPARQL
        build_ng_sparql(subgraph_file, output_ng)


    
    print("\n3. Parsing RDF...")


    parse_rdf(output_ng, timeline_file)


    print("\n4. Generating story...")
    story, story_file = generate_story(timeline_file)

    print("\n--- STORY ---")
    print(story)

    # compute story score if needed
    if compute_score:
        print("\n5. Computing story score...")
        evaluate_story(story_file, temp_ground_truh)
    

if __name__ == "__main__":
    run_pipeline()