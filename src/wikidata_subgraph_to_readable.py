import pandas as pd
import requests
import time
from typing import List, Dict
from tqdm import tqdm

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
HEADERS = {
    "User-Agent": "WikidataLabelFetcher/1.0 (your_email@example.com)"
}

def extract_id(uri: str) -> str:
    """Extract ID from Wikidata URI (Qxxx or Pxxx)."""
    if isinstance(uri, str) and "wikidata.org/" in uri:
        return uri.split("/")[-1]
    return None

def chunk_list(lst: List[str], chunk_size: int):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

def query_labels(ids: List[str], max_retries=5, sleep_base=2) -> Dict[str, str]:
    values = " ".join(f"wd:{i}" for i in ids)
    query = f"""
    SELECT ?item ?itemLabel WHERE {{
      VALUES ?item {{ {values} }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """

    for attempt in range(max_retries):
        try:
            r = requests.get(
                WIKIDATA_SPARQL_URL,
                params={"query": query, "format": "json"},
                headers=HEADERS,
                timeout=30
            )

            if r.status_code == 200:
                data = r.json()
                return {
                    b["item"]["value"].split("/")[-1]: b["itemLabel"]["value"]
                    for b in data["results"]["bindings"]
                }

            else:
                print(f"[WARN] HTTP {r.status_code}")

        except Exception as e:
            print(f"[ERROR] {e}")

        time.sleep(sleep_base ** attempt)

    return {}

def fetch_all_labels(input_csv: str, output_csv: str, batch_size=50):
    df = pd.read_csv(input_csv)

    # Extract IDs
    df["sub_id"] = df["subject"].apply(extract_id)
    df["pred_id"] = df["predicate"].apply(extract_id)
    df["obj_id"] = df["object"].apply(extract_id)

    # Collect all unique IDs
    all_ids = pd.concat([df["sub_id"], df["pred_id"], df["obj_id"]])
    unique_ids = all_ids.dropna().unique().tolist()

    label_map = {}

    batches = list(chunk_list(unique_ids, batch_size))
    for batch in tqdm(batches, desc="Resolving labels"):
        label_map.update(query_labels(batch))
        time.sleep(1)

    # Map back
    df["subject_label"] = df["sub_id"].map(label_map)
    df["predicate_label"] = df["pred_id"].map(label_map)
    df["object_label"] = df["obj_id"].map(label_map)

    # Keep only readable columns
    df_out = df[["subject_label", "predicate_label", "object_label"]]

    df_out.to_csv(output_csv, index=False)
    print(f"Saved to {output_csv}")



WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
HEADERS = {
    # Remember to swap in your actual email!
    "User-Agent": "WikidataLabelFetcher/1.0 (your_email@example.com)"
}

def get_single_label(uri: str, lang: str = "en") -> str:
    """
    Fetches the label for a single Wikidata URI or ID using SPARQL.
    """
    # Extract ID whether it's a full URI or just the Q-identifier
    entity_id = uri.split("/")[-1] if "wikidata.org/" in uri else uri
    
    # We don't need the VALUES block for just one item, 
    # we can just query its rdfs:label directly.
    query = f"""
    SELECT ?itemLabel WHERE {{
      wd:{entity_id} rdfs:label ?itemLabel.
      FILTER(LANG(?itemLabel) = "{lang}")
    }}
    """

    try:
        r = requests.get(
            WIKIDATA_SPARQL_URL,
            params={"query": query, "format": "json"},
            headers=HEADERS,
            timeout=10
        )
        r.raise_for_status() # Catch any 4xx or 5xx errors
        
        data = r.json()
        bindings = data.get("results", {}).get("bindings", [])
        
        if bindings:
            return bindings[0]["itemLabel"]["value"]
            
        return None # Return None if no label was found

    except Exception as e:
        print(f"[ERROR] fetching label for {entity_id}: {e}")
        return None


if __name__ == "__main__":
    input_file = "experiments/2026-04-24-16_38_31-informed_wikidata_french_revolution_2_pred_object_freq_domain_range__where_when__without_category_uri_iter__max_inf/2-subgraph.csv"
    output_file = "experiments/2026-04-24-16_38_31-informed_wikidata_french_revolution_2_pred_object_freq_domain_range__where_when__without_category_uri_iter__max_inf/readable_2-subgraph.csv"
    #fetch_all_labels(input_file, output_file)


