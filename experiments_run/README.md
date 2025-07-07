# **Experiments for the SWJ (2024)**

This README describes and details the experiments that were run for the SWJ submission.

### 5.1 Relevant Event Retrieval
For the search experiments, we created a main folder with the data in the root directory: `data-test`, with two sub-folders: `dbpedia` and `wikidata`. Each sub-folder had three folders: `config`, `gs_events` and `referents`.

All scripts are in this folder. All example commands are run from root directory of the repo.

* Parameter selection for the search (subset of 12 events)
    * Python script: `run_all_grid_search.py`
    * Example command:
        ```bash
        python experiments_run/run_all_grid_search.py -t <type-system> -e experiments_run/grid-search-events.csv 
        ```
* Main results for the search (all events)
    * Python script: `run_all_search.py`
    * Example command:
        ```bash
        python experiments_run/run_all_search.py -t <type-system> -e experiments_run/all-search-events.csv 
        ```

The following table shows information on events and their sub-events across datasets. All types of events are taken into account, which include mainly historical events, sports events and political events such as elections.

| Dataset  | Nb. of sub-events = 1 | Nb. of sub-events > 1 | Nb. of sub-events > 10 | Final |
|----------|------------------------|------------------------|-------------------------|-------|
| Wikidata | 203,988                | 238,094                | 2,408                   | 341   |
| DBpedia  | 84,599                 | 95,504                 | 1,333                   | 250   |
| YAGO4    | 70,738                 | 76,682                 | 993                     | 306   |

The following 12 events were used for parameter selection for the search:
* World War I 
* American Indian Wars
* Mediterranean and Middle East Theatre of World War II
* French RevolutionCold War
* European Theatre of World War II
* Napoleonic Wars
* Coalition Wars
* European Theatre of World War I
* Pacific War
* Russian Civil War
* Yugoslav Wars

### 5.2 Event-centric KG Population

The following table shows the labels that were used to retrieve information from triples. If a predicate contained any of the labels, it would add information in the graph based on its narrative dimension and SEM predicate. As an example, let us take an input triple `(s, p, o)`. If the string of `p` contains the substring `"person"`, then a triple `(s, sem:hasActor, o)` is added to the output graph.

| Narrative dimension | SEM predicate         | Labels                                           |
|---------------------|-----------------------|--------------------------------------------------|
| Who                 | `sem:hasActor`       | person, combatant, commander, participant        |
| When (begin)        | `sem:hasBeginTimeStamp` | start time, date, point in time               |
| When (end)          | `sem:hasEndTimeStamp`   | end time                                         |
| Where               | `sem:hasPlace`       | place, location, country                         |
| Part of             | `sem:subEventOf`     | partof, part of                                  |
| Part of (inverse)   | `sem:hasSubEvent`    | has part, significant event                      |



For the event-centric KG generation experiments, we extracted the data that we needed from the search experiments, and created a new folder, `data_ng_building`.

* Extracting data
    * Python script: `get_data_ng_building.py`. There are some parameters to change in PARAMS (start and end date of experiments, folder_gs if different)
    * Example command:
        ```bash
        python experiments_run/get_data_ng_building.py 
        ```
    * The data was saved in a new folder: `data_ng_building`

* Event-centric KG population (EC-KG-P) from KG
    * This includes EC-KG-P from the output of graph search, EC-KG-P with our system from ground truth events, EC-KG-P from EventKG
    * Python script: `build_ng_from_search.py`
    * Example command:
        ```bash
        python experiments_run/build_ng_from_search.py --folder data_ng_building/ 
        ``` 
* Metrics for EC-KG-P from KG
    * Python script: `get_metrics.py`
    * Example command (comparing with all ground truth events):
        ```bash
        python experiments_run/get_metrics.py --folder data_ng_building/ --output_name eventkg_vs_generation.json --graph_c_path generation_ng.ttl --graph_gs_path eventkg_ng.ttl
        ```
    * Example command (comparing with output of graph search):
        ```bash
        python experiments_run/get_metrics.py --folder data_ng_building/ --output_name eventkg_vs_search.json --graph_c_path search_ng.ttl --graph_gs_path eventkg_ng.ttl
        ``` 

* Aggregating results (as in the paper):
    * Python script: `get_table_results.py`
    * Example command (comparing with all ground truth events):
        ```bash
        python experiments_run/get_table_results.py --folder data_ng_building/ --metric eventkg_vs_generation.json --label <label>
        ```
    * Example command (comparing with output of graph search):
        ```bash
        python experiments_run/get_table_results.py --folder data_ng_building/ --metric eventkg_vs_search.json --label <label>
        ```

* Event-centric KG Population from text
    * These are the experiments to generate KGs from the DBpedia abstracts
    * First you need to set up a local DBpedia, you can follow the steps on this link: <https://github.com/MartinoMensio/spacy-dbpedia-spotlight>
    * Python script: `build_kg_with_frames.py`
    * Example command:
        ```bash
        python experiments_run/build_kg_with_frames.py --folder data_ng_building/dbpedia/
        ```

* Annotating and analysing (causation) frames
    * Analysing
        * Python script: `get_csv_analyse_frame.py`
        * Example command
            ```bash
            python experiments_run/get_csv_analyse_frame.py --folder_input data_ng_building/dbpedia/ --folder_output experiments_run/ng_analysis
            ```
    * Extracting causation frames for manual annotation
        * Python script: `extract_causation_for_annot.py`
        * Example command
            ```bash
            python experiments_run/extract_causation_for_annot.py --csv experiments_run/ng_analysis/df_causation.csv --folder experiments_run/ng_analysis/
            ```

Furthermore, the manually annotated causation frames can be found in the `experiments_run/annotated` folder.

The following table shows the F1, Precision and Recall scores of the narrative graphs generated from the output of the search algorithm. Our end-to-end system achieves an overall (for all predicates) F1 score of 51.7% and 49.2% respectively. APrecision is higher for DBpedia, while recall tends to be higher for Wikidata. The results are furthermore lower than those in the paper, which is expected since the output of the search also contains events that are not in the ground truth events. Consequently, for each of such event, all generated triples will not be in the ground truth from EventKG.

| Pred                         | F1 (DB) | F1 (WD) | Precision (DB) | Precision (WD) | Recall (DB) | Recall (WD) |
|-----------------------------|---------|---------|----------------|----------------|-------------|-------------|
| `all`                       | 51.7    | 49.2    | 79.3           | 41.1           | 38.4        | 61.4        |
| `sem:hasActor`              | 48.5    | 27.6    | 76.5           | 35.1           | 35.5        | 22.8        |
| `sem:hasBeginTimeStamp`     | 62.6    | 50.3    | 79.5           | 38.0           | 51.6        | 74.4        |
| `sem:hasEndTimeStamp`       | 62.7    | 48.3    | 79.5           | 38.1           | 51.7        | 65.9        |
| `sem:hasPlace`              | 48.2    | 59.2    | 81.6           | 50.7           | 34.2        | 71.2        |


### 5.3 User study

All the content related to the user studies are in the `experiments_run/usage_ng` folder:
* The scripts permit to get the prompts, the answers, and the grounding triples, for all types of prompting.
* `experiments_run/usage_ng/human_evaluation` contains the final results from the forms, and a notebook to analyse the results.
* `experiments_run/usage_ng/qa_prompt_answer` contains the saved prompts and answers for the three prompting techniques.
* The triples used from the event-centric KG are in the `french_rev_frame_generation_all.ttl` file. To query it, we set up a local GraphDB repository. 

Link to the forms:
* [https://forms.gle/1SJTtTMUUM4uh7KT6](https://forms.gle/1SJTtTMUUM4uh7KT6)
* [https://forms.gle/Rtgj7ucpdC1jm3tc6](https://forms.gle/Rtgj7ucpdC1jm3tc6)