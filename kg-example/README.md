# **kg-example**

This file provides an overview of the contents of each file in the folder, which includes materials related to examples on the French Revolution.

* `config.json`: This file is a configuration file that can be used as input to the search module. The main Python file for the search module can be found [here](https://github.com/SonyCSLParis/graph_search_framework/blob/main/src/framework.py).
<details>
<summary>Click here to know more about the config file</summary>

##

Parameters that don't require additional data to be downloaded:
* `rdf_type`: the type of nodes you want to retrieve. Keys should be a string, and values the string URI of that node type. In our experiments, we are mainly interested about events.
* `predicate_filter`: list of predicates that are not taken into account for the search
* `start`: node to start the search from
* `start_date`: starting date of that `start` node
* `end_date`: ending date of that `start` node
* `iterations`: number of iterations for the search. The higher the number, the longer it will take to run.
* `type_ranking`: the type of ranking to use for paths.
* `type_interface`: type of interface used, in practice `hdt` only.
* `type_metrics`: the metrics that are computed, should be a sub-list of `["precision", "recall", "f1"]`
* `ordering` and `domain_range`: boolean, to activate or not this parameter
* `filtering`: same than above
* `name_exp`: name of your experiment, for the saving folder
* `dataset_type`: type of dataset, depending on the one you have
* `dataset_path`: path the the dataset folder 
* `nested_dataset`: boolean, whether your dataset is nested (decomposed in smaller chunks) or not

Parameters that require additional data to be downloaded - c.f. section 4 of the main README for further details:
* `gold_standard`: .csv path to the gold standard events
* `referents`: .json path to the URI referents
</details>

####
* `eventkg_ng.ttl`: This file is a KG built from EventKG using SPARQL CONSTRUCT queries. To compare EventKG's triples to ours, we replaced EventKG IRIs with the original DBpedia/Wikidata instances and aligned the predicates to SEM. More details can be found in [this Python file](https://github.com/SonyCSLParis/graph_search_framework/blob/main/src/build_ng/eventkg_to_ng.py).

* `eventkg_vs_generation.json`: This file contains metrics comparing the adapted SEM triples from EventKG on the French Revolution to those produced by our KG construction module only. The Python file to get the metrics can be found [here](https://github.com/SonyCSLParis/graph_search_framework/blob/main/experiments_run/get_metrics.py), and examples of command [here](https://github.com/SonyCSLParis/graph_search_framework/blob/main/experiments_run/README.md)
* `eventkg_vs_search.json`: This file contains metrics comparing the adapted SEM triples from EventKG on the French Revolution to those produced by our combined search and KG construction module. The Python file to get the metrics can be found [here](https://github.com/SonyCSLParis/graph_search_framework/blob/main/experiments_run/get_metrics.py).
* `frame_ng.ttl`: This file contains the constructed KG built from the abstract-based component of the KG construction module (cf. Section 3.2 in the paper). The main related Python file can be found [here](https://github.com/SonyCSLParis/graph_search_framework/blob/main/experiments_run/build_kg_with_frames.py).
* `generation_ng.ttl`: This file contains the KG constructed from all ground truth events from the IRI-based component of the KG construction module (cf. Section 3.2 in the paper).  The main related Python file can be found [here](https://github.com/SonyCSLParis/graph_search_framework/blob/main/experiments_run/build_ng_from_search.py).
* `gs_events.csv`: This file contains the sub-events of the French Revolution extracted from EventKG. The main related Python notebook can be found [here](https://github.com/SonyCSLParis/graph_search_framework/blob/main/notebooks/eventkg-retrieving-events.ipynb).
* `metadata.json`: This file contains metadata about the search module applied to the French Revolution. It is added automatically in the [search module](https://github.com/SonyCSLParis/graph_search_framework/blob/main/src/framework.py).
* `ng_build.txt`: This file contains metadata about the KG construction module applied to the French Revolution. It is built in this [Python file](https://github.com/SonyCSLParis/graph_search_framework/blob/main/experiments_run/build_ng_from_search.py).
* `output_search.csv`: This file contains the output of the search module applied to the French Revolution. The subraph can be extracted by selecting the "subject", "predicate" "object" columns in the csv. It is added automatically in the [search module](https://github.com/SonyCSLParis/graph_search_framework/blob/main/src/framework.py).
* `search_ng.ttl`: This file contains the KG built from the sub-events retrieved by the search module, after applying the IRI-based component of the KG construction module. The main related Python file can be found [here](https://github.com/SonyCSLParis/graph_search_framework/blob/main/experiments_run/build_ng_from_search.py).
