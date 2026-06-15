# KG-to-Story: Narrative Generation from Knowledge Graphs

This repository contains the code for the KG-to-Story pipeline — a system that transforms an event-centric subgraph extracted from a large Knowledge Graph (Wikidata) into a coherent, human-readable historical narrative using a Large Language Model.

The pipeline takes the output of [ChronoGrapher](https://github.com/SonyCSLParis/graph_search_framework) (an informed graph traversal framework) and converts it into a structured story through six sequential stages.

---

## Setup

**Python 3.10.6** is required. Clone the repo and install dependencies:

```bash
git clone <repo-url>
cd graph_search_framework
pip install -r requirements.txt
```

Additional packages used by the story pipeline that are not yet in `requirements.txt`:

```bash
pip install openai sentence-transformers textstat
```

Create `src/settings/private.py` with the following variables:

```python
FOLDER_PATH = "/path/to/graph_search_framework"   # absolute path to repo root
```

Set the LLM endpoint and API key in [src/kg_to_story/config.py](src/kg_to_story/config.py):

```python
EURECOM_URL = "https://your-llm-endpoint/v1"
MY_API      = "your-api-key"
```

The pipeline queries Wikidata HDT files for label resolution. Set the HDT folder path inside [src/kg_to_story/run_pipeline.py](src/kg_to_story/run_pipeline.py):

```python
hdt_folder = "/path/to/wikidata_dataset"
```

---

## Running the Pipeline

The full pipeline is launched from the root directory with a JSON config file:

```bash
python src/kg_to_story/run_pipeline.py \
    -j sample-data/French_Revolution_config_wikidata.json \
    -m search_type_node_metrics \
    -w informed
```

**Arguments:**

| Argument | Default | Description |
|---|---|---|
| `-j` / `--json` | required | Path to the JSON config file |
| `-m` / `--mode` | `search_type_node_metrics` | Search mode |
| `-w` / `--walk` | `informed` | Walk type: `informed` or `random` |
| `-n` / `--node_selection` | `all` | Node selection strategy |
| `-i` / `--interface` | from config | Override interface: `hdt` or `sparql_endpoint` |
| `--compute_score` | off | Evaluate generated story if flag is present |

To run only story generation and scoring over a set of pre-built experiment folders (no graph search):

```bash
python src/kg_to_story/run_generation.py event   # for historical events
python src/kg_to_story/run_generation.py person  # for persons
```

---

## Configuration

Each run is driven by a JSON config file (examples in `sample-data/`). Key fields relevant to the story pipeline:

| Field | Purpose |
|---|---|
| `start` | Seed entity URI (e.g., Wikidata URI of the French Revolution) |
| `start_name` | Human-readable name for the seed (used as the story topic) |
| `start_date` / `end_date` | Temporal scope for event filtering (`YYYY-MM-DD`) |
| `iterations` | Number of graph traversal iterations |
| `type_interface` | `"hdt"` or `"sparql_endpoint"` |
| `dataset_type` | `"wikidata"`, `"dbpedia"`, or `"yago"` |
| `dataset_path` | Path to `.hdt` file or SPARQL endpoint URL |
| `filtering` | `{"when": 1, "where": 0, "who": 0}` — narrative dimension filters |
| `rdf_type.event` | URI of the event class used during traversal |

---

## Pipeline Stages

The pipeline consists of six sequential stages.

### Stage 1 — Event-Oriented Subgraph Extraction

**Code:** [src/framework.py](src/framework.py)

Starting from a seed entity (e.g., the French Revolution), the `GraphSearchFramework` performs an informed BFS-like traversal over the Wikidata KG. It expands nodes iteratively, applying narrative dimension filters (`when`, `where`, `who`) and predicate-frequency ranking to focus on event-relevant triples. The output is a raw subgraph saved as a CSV file (`{iter}-subgraph.csv`).

### Stage 2 — Event Filtering and Graph Construction

**Code:** [src/build_ng/post_filtering.py](src/build_ng/post_filtering.py)

The raw subgraph is filtered to remove noise before narrative graph construction:
- Unresolved Wikidata Q-nodes (entities with no resolved label) are removed.
- Events whose timestamps fall outside the seed event's temporal window (±1 year slack) are discarded.
- Events missing an `rdfs:comment` (textual description) are excluded.
- Important nodes listed in `important_nodes.json` are always retained.
- The event set is capped at a configurable `max_events` (default: 200).

### Stage 3 — Narrative Graph Construction and Semantic Enrichment

**Code:** [src/build_ng/custom_generic_kb_to_ng_wikidata.py](src/build_ng/custom_generic_kb_to_ng_wikidata.py)

The filtered subgraph CSV is converted into a structured **narrative graph** serialised as Turtle RDF using the [SEM (Semantic Event Model)](http://semanticweb.cs.vu.nl/2009/11/sem/) ontology. Each event node is annotated with:
- `sem:hasTimeStamp` — the event date
- `sem:hasPlace` — location(s)
- `sem:hasActor` — participant entities
- `rdfs:comment` — a human-readable description

Wikidata URIs are resolved to human-readable labels by querying the HDT dataset, enriching the graph semantically. The output is saved as `output_ng.ttl`.

### Stage 4 — Dual-Score Event Ranking and Top-*k* Selection

**Code:** [src/kg_to_story/llm_pruning.py](src/kg_to_story/llm_pruning.py)

Events are ranked by relevance to the main topic using a dual scoring system:

1. **Wikipedia Similarity Score** — the `rdfs:comment` of each event is embedded using a [sentence-transformers](https://www.sbert.net/) model and compared (cosine similarity) against the Wikipedia introduction of the main event (fetched via the Wikipedia REST API). Scores are min-max normalised to [0, 1].

2. **LLM Relevance Score** *(optional)* — the LLM (Qwen3-30B) is prompted to assign a relevance score (0–10) to each event in batches, given its description and the main topic. Scores are normalised to [0, 1].

The final combined score is a weighted sum:

```
combined = wiki_weight × wiki_score + llm_weight × llm_score
```

Default weights: `wiki_weight=1.0, llm_weight=0.0` (LLM scoring is optional and can be enabled with `use_llm=True`). The top *k* events (default: `k=35`) are written to `selected_events_combined.txt`.

### Stage 5 — Post-Processing and Timeline Extraction

**Code:** [src/kg_to_story/parse_rdf.py](src/kg_to_story/parse_rdf.py)

The narrative graph TTL is parsed with [rdflib](https://rdflib.readthedocs.io). Events are filtered to only those selected in Stage 4 (via `selected_events_combined.txt`), then sorted chronologically by `sem:hasTimeStamp`. Each event is formatted as a single line:

```
YYYY-MM-DD — Event Name — Place — Description (truncated at sentence boundary, ≤30 words).
```

Unknown dates are placed at the end. The result is saved as `event_timeline.txt`, which serves as the structured context for story generation.

### Stage 6 — LLM-Based Story Generation

**Code:** [src/kg_to_story/generate_story.py](src/kg_to_story/generate_story.py)

The event timeline is passed to **Qwen3-30B** (via an OpenAI-compatible API endpoint) with a carefully designed prompt that instructs the model to:
- Write a continuous prose narrative (~700 words) without headers or bullet points.
- Follow the chronological event sequence, skipping events that do not serve the narrative.
- Add historical context where needed for coherence.
- Explain *why* events happened, not just *what* happened.

Two story variants are generated:
- **Event-driven story** — grounded in the extracted event timeline.
- **Baseline story** — generated from the LLM's parametric knowledge alone (no events provided), used as a comparison baseline.

The story is saved as `generated_story.txt` and the baseline as `generated_story_baseline.txt`.

---

## Evaluation

**Code:** [src/kg_to_story/evaluate_story.py](src/kg_to_story/evaluate_story.py), [src/kg_to_story/metrics/](src/kg_to_story/metrics/)

Stories are evaluated against the Wikipedia introduction of the main event using multiple automatic metrics:
- **Semantic similarity** (sentence-transformers cosine similarity)
- **Readability** (Flesch–Kincaid, Dale–Chall via `textstat`)
- **Lexical diversity** (TTR, MTLD via `diversity_model.py`)
- **LLM-based scoring** (`metrics/run_llm_benchmark.py`)

For batch evaluation across multiple subjects, `run_generation.py` generates 5 story runs per subject per modality and averages the scores, saving per-subject and global averages to `summary_avg_scores.json`.

---

## Output Structure

```
experiments/<timestamp>-<name>/
├── config.json
├── {iter}-subgraph.csv              # raw extracted subgraph (Stage 1)
├── output_ng.ttl                    # SEM narrative graph (Stages 2–3)
├── selected_events_combined.txt     # top-k selected events (Stage 4)
├── scores_all.txt                   # full event ranking with scores (Stage 4)
├── event_timeline.txt               # sorted event timeline (Stage 5)
├── generated_story.txt              # LLM narrative (Stage 6)
├── generated_story_baseline.txt     # LLM baseline narrative (Stage 6)
├── score_event_driven.json          # evaluation scores — event-driven story
└── score_baseline.json              # evaluation scores — baseline story
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `rdflib` | Parsing and serialising Turtle RDF narrative graphs |
| `pandas` | Subgraph CSV handling and pruning |
| `networkx` | PageRank-based subgraph pruning (`pruning.py`) |
| `openai` | LLM API calls (story generation and LLM scoring) |
| `sentence-transformers` | Wikipedia similarity scoring |
| `tqdm` | Progress bars |
| `spacy` | NLP utilities in build_ng modules |
| `textstat` | Readability metrics |

Install all project dependencies:

```bash
pip install -r requirements.txt
pip install openai sentence-transformers textstat
```
