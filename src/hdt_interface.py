# -*- coding: utf-8 -*-
"""
Interface to query a KG - format compressed HDT
"""
import os
import fnmatch
import yaml
import rdflib



from hdt import HDTDocument


from src.interface import Interface
from settings import FOLDER_PATH

HDT_DBPEDIA = \
    os.path.join(FOLDER_PATH, "dbpedia_dataset")

DEFAULT_PRED = \
    ["http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
     "http://dbpedia.org/ontology/date",
     "http://dbpedia.org/ontology/startDate",
     "http://dbpedia.org/ontology/endDate",
     "http://dbpedia.org/property/birthDate",
     "http://dbpedia.org/property/deathDate"]

with open(os.path.join(FOLDER_PATH, "dataset-config", "dbpedia.yaml"),
          encoding='utf-8') as file:
    dbpedia_dataset_config = yaml.load(file, Loader=yaml.FullLoader)

class HDTInterface(Interface):
    """
    Format of dataset = HDT, where you can do "simple" queries only, but much faster
    """
    def __init__(self, dataset_config: dict = dbpedia_dataset_config,
                 dates: list[str] = [None, None], default_pred: list[str] = DEFAULT_PRED,
                 folder_hdt: str = HDT_DBPEDIA, nested_dataset: bool = True, filter_kb: bool = 1):
        """
        - `dataset_config`: dict, dataset config, example in `dataset-config` folder
        - `dates`: list of two strings, start and end dates of the event
        - `default_pred`: list of strings, predicates for rdf:type and dates
        - `folder_hdt`: string, path to the HDT dataset
        - `nested_dataset`: boolean, whether the dataset is chunked down in folders
        - `filter_kb`: boolean, whether to exclude some types of predicates or not
        """
        Interface.__init__(self, dataset_config=dataset_config, dates=dates,
                           default_pred=default_pred, filter_kb=filter_kb)

        # 1. Find the actual .hdt file instead of .ttl files
        hdt_files = [f for f in os.listdir(folder_hdt) if f.endswith(".hdt")]
        
        if not hdt_files:
            raise FileNotFoundError(f"No .hdt file found in {folder_hdt}. Make sure your dataset is actually converted to HDT format.")
            
        hdt_file_path = os.path.join(folder_hdt, hdt_files[0])
        print(f"Loading HDT Document: {hdt_file_path}")

        # 2. Load the HDT file using the C++ wrapper
        self.document = HDTDocument(hdt_file_path)


    def get_triples(self, **params: dict) -> list:
        subject_t = params.get("subject", "")
        predicate_t = params.get("predicate", "")
        object_t = params.get("object", "")

        results = []

        # handle list of predicates
        if isinstance(predicate_t, list):
            for p in predicate_t:
                triples_iterator, _ = self.document.search_triples(subject_t, p, object_t)
                results.extend(list(triples_iterator))
        else:
            triples_iterator, _ = self.document.search_triples(subject_t, predicate_t, object_t)
            results = list(triples_iterator)

        return results

    @staticmethod
    def clean_hdt_object(obj_str: str) -> str:
        """Strips datatypes from HDT literals to mimic SPARQL JSON output."""
        if obj_str.startswith('"'):
            return obj_str.split('"')[1]
        return obj_str

    def get_event_info(self, event_uri: str) -> tuple:
        """Fast binary search for actors, places, and dates."""
        actors, places, dates = [], [], []

        # 1. Get Commanders
        cmd_it, _ = self.document.search_triples(event_uri, "http://dbpedia.org/ontology/commander", "")
        for _, _, o in cmd_it:
            actors.append(self.clean_hdt_object(o))
            if len(actors) >= 20: break

        # 2. Get Places
        place_it, _ = self.document.search_triples(event_uri, "http://dbpedia.org/ontology/place", "")
        for _, _, o in place_it:
            places.append(self.clean_hdt_object(o))
            if len(places) >= 20: break

        # 3. Get Dates
        date_it, _ = self.document.search_triples(event_uri, "http://dbpedia.org/ontology/date", "")
        for _, _, o in date_it:
            dates.append(self.clean_hdt_object(o))
            if len(dates) >= 20: break

        return actors, places, dates



if __name__ == '__main__':
    NODE = "http://dbpedia.org/resource/André_Masséna"
    PREDICATE = ["http://dbpedia.org/ontology/wikiPageWikiLink",
                    "http://dbpedia.org/ontology/wikiPageRedirects",
                    "http://dbpedia.org/ontology/wikiPageDisambiguates",
                    "http://www.w3.org/2000/01/rdf-schema#seeAlso",
                    "http://xmlns.com/foaf/0.1/depiction",
                    "http://xmlns.com/foaf/0.1/isPrimaryTopicOf",
                    "http://dbpedia.org/ontology/thumbnail",
                    "http://dbpedia.org/ontology/wikiPageExternalLink",
                    "http://dbpedia.org/ontology/wikiPageID",
                    "http://dbpedia.org/ontology/wikiPageLength",
                    "http://dbpedia.org/ontology/wikiPageRevisionID",
                    "http://dbpedia.org/property/wikiPageUsesTemplate",
                    "http://www.w3.org/2002/07/owl#sameAs",
                    "http://www.w3.org/ns/prov#wasDerivedFrom",
                    "http://dbpedia.org/ontology/wikiPageWikiLinkText",
                    "http://dbpedia.org/ontology/wikiPageOutDegree",
                    "http://dbpedia.org/ontology/abstract",
                    "http://www.w3.org/2000/01/rdf-schema#comment",
                    "http://www.w3.org/2000/01/rdf-schema#label"]

    interface = HDTInterface()
    ingoing_test, outgoing_test, types_test = interface(node=NODE, predicate=PREDICATE)
    print(f"{ingoing_test}\n{outgoing_test}\n{types_test}")

    ingoing_test.to_csv(f"{FOLDER_PATH}/hdt_ingoing.csv")
    outgoing_test.to_csv(f"{FOLDER_PATH}/hdt_outgoing.csv")
    types_test.to_csv(f"{FOLDER_PATH}/hdt_types.csv")
