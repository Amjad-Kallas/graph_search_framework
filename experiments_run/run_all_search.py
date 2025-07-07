# -*- coding: utf-8 -*-
""" Script - Final experiments """
import os
import json
import time
import random
import psutil
import argparse

import pandas as pd
from datetime import datetime
from copy import deepcopy
from sklearn.model_selection import ParameterGrid

from src.framework import GraphSearchFramework
from settings import FOLDER_PATH

import multiprocessing as mp
import multiprocessing.queues as mpq
import functools
import dill
from typing import Tuple, Callable, Dict, Optional, Iterable, List

os.environ["RAY_OBJECT_STORE_ALLOW_SLOW_STORAGE"] = "1"

DATES = {
    "informed_epof": {"start": "2023-04-07-15:56:00", "end": "2023-04-12-12:03:05"},
    "informed_pof": {"start": "2023-04-13-10:28:24", "end": "2023-04-13-11:52:34"},
    "informed_pf": {"start": "2023-04-16-11:05:07", "end": "2023-04-16-12:31:39"},
    "informed_epf": {"start": "2023-04-16-22:18:45", "end": "2023-04-16:23:42:07"},
    "nautilod": {"start": str(datetime.now())[:19].replace(" ", "-"), "end": str(datetime.now())[:19].replace(" ", "-")},
    "ldspider": {"start": "2023-04-13-13:44:27", "end": str(datetime.now())[:19].replace(" ", "-")},
    "random_5": {"start": "2023-04-12-12:08:04", "end": "2023-04-12-16:26:44"},
    "random_10": {"start": "2023-04-12-18:00:36", "end": "2023-04-12-21:53:43"},
    "random_15": {"start": "2023-04-15-11:23:35", "end": "2023-04-15-15:50:23"},
}

PARAMS = {
    "informed_epof": {
        "type_ranking": ['entropy_pred_object_freq'],
        "ordering_domain_range": [1],
        "filtering_who": [1],
        "filtering_what": [1],
        "filtering_where": [1],
        "filtering_when": [1]
    },
    "informed_pof": {
        "type_ranking": ['pred_object_freq'],
        "ordering_domain_range": [1],
        "filtering_who": [1],
        "filtering_what": [1],
        "filtering_where": [1],
        "filtering_when": [1]
    },
    "informed_epf": {
        "type_ranking": ['entropy_pred_freq'],
        "ordering_domain_range": [1],
        "filtering_who": [1],
        "filtering_what": [1],
        "filtering_where": [1],
        "filtering_when": [1]
    },
    "informed_pf": {
        "type_ranking": ['pred_freq'],
        "ordering_domain_range": [1],
        "filtering_who": [1],
        "filtering_what": [1],
        "filtering_where": [1],
        "filtering_when": [1]
    },
    "nautilod": {
        "filtering_who": [1],
        "filtering_what": [1],
        "filtering_where": [1],
        "filtering_when": [1]
    },
    "ldspider": {
        "filtering_who": [0],
        "filtering_what": [0],
        "filtering_where": [0],
        "filtering_when": [0]
    },
    "random_5": {
        "filtering_who": [0],
        "filtering_what": [0],
        "filtering_where": [0],
        "filtering_when": [0],
        "uri_limit": [5],
    },
    "random_10": {
        "filtering_who": [0],
        "filtering_what": [0],
        "filtering_where": [0],
        "filtering_when": [0],
        "uri_limit": [10],
    },
    "random_15": {
        "filtering_who": [0],
        "filtering_what": [0],
        "filtering_where": [0],
        "filtering_when": [0],
        "uri_limit": [15],
    },
}

# Preparing MP SCRIPTS
class TimeoutError(Exception):

    def __init__(self, func, timeout):
        self.t = timeout
        self.fname = func.__name__

    def __str__(self):
            return f"function '{self.fname}' timed out after {self.t}s"


def _lemmiwinks(func: Callable, args: Tuple[object], kwargs: Dict[str, object], q: mp.Queue):
    """lemmiwinks crawls into the unknown"""
    q.put(dill.loads(func)(*args, **kwargs))


def killer_call(func: Callable = None, timeout: int = 10) -> Callable:
    """
    Single function call with a timeout

    Args:
        func: the function
        timeout: The timeout in seconds
    """

    if not isinstance(timeout, int):
        raise ValueError(f'timeout needs to be an int. Got: {timeout}')

    if func is None:
        return functools.partial(killer_call, timeout=timeout)

    @functools.wraps(killer_call)
    def _inners(*args, **kwargs) -> object:
        q_worker = mp.Queue()
        proc = mp.Process(target=_lemmiwinks, args=(dill.dumps(func), args, kwargs, q_worker))
        proc.start()
        try:
            return q_worker.get(timeout=timeout)
        except mpq.Empty:
            raise TimeoutError(func, timeout)
        finally:
            try:
                proc.terminate()
            except:
                pass
    return _inners


def _queue_mgr(func_str: str, q_in: mp.Queue, q_out: mp.Queue, timeout: int, pid: int) -> object:
    """
    Controls the main workflow of cancelling the function calls that take too long
    in the parallel map

    Args:
        func_str: The function, converted into a string via dill (more stable than pickle)
        q_in: The input queue
        q_out: The output queue
        timeout: The timeout in seconds
        pid: process id
    """
    while not q_in.empty():
        positioning, x  = q_in.get()
        q_worker = mp.Queue()
        proc = mp.Process(target=_lemmiwinks, args=(func_str, (x,), {}, q_worker,))
        proc.start()
        try:
            print(f'[{pid}]: {positioning}: getting')
            res = q_worker.get(timeout=timeout)
            print(f'[{pid}]: {positioning}: got')
            q_out.put((positioning, res))
        except mpq.Empty:
            q_out.put((positioning, None))
            print(f'[{pid}]: {positioning}: timed out ({timeout}s)')
        finally:
            try:
                proc.terminate()
                print(f'[{pid}]: {positioning}: terminated')
            except:
                pass
    print(f'[{pid}]: completed!')


def killer_pmap(func: Callable, iterable: Iterable, cpus: Optional[int] = None, timeout: int = 4):
    """
    Parallelisation of func across the iterable with a timeout at each evaluation

    Args:
        func: The function
        iterable: The iterable to map func over
        cpus: The number of cpus to use. Default is the use max - 2.
        timeout: kills the func calls if they take longer than this in seconds
    """

    if cpus is None:
        cpus = max(mp.cpu_count() - 2, 1)
        if cpus == 1:
            raise ValueError('Not enough CPUs to parallelise. You only have 1 CPU!')
        else:
            print(f'Optimising for {cpus} processors')

    q_in = mp.Queue()
    q_out = mp.Queue()
    sent = [q_in.put((i, x)) for i, x in enumerate(iterable)]

    processes = [
        mp.Process(target=_queue_mgr, args=(dill.dumps(func), q_in, q_out, timeout, pid))
        for pid in range(cpus)
    ]
    print(f'Started {len(processes)} processes')
    for proc in processes:
        proc.start()

    result = [q_out.get() for _ in sent]

    for proc in processes:
        proc.terminate()

    return [x for _, x, in sorted(result)]

# --------------------
# Preparing experiments

def update_config(config, args, iteration, dataset, type_system):
    """ Updating config for sweep (inline params) """

    # Common for all systems
    config = deepcopy(config)

    config["predicate_filter"] = config["predicate_filter"] + ["http://purl.org/linguistics/gold/hypernym"]
    config['iterations'] = int(iteration)

    if "filtering" not in config:
        config["filtering"] = {}
    
    for elt in ["what", "where", "when", "who"]:
        config["filtering"][elt] = int(args[f"filtering_{elt}"])
    
    config["gold_standard"] = os.path.join(FOLDER_PATH, "data-test", dataset, "gs_events", config["gold_standard"])
    config["referents"] = os.path.join(FOLDER_PATH, "data-test", dataset, "referents", config["referents"])

    max_uri = int(1.1 * pd.read_csv(config["gold_standard"]).shape[0])
    config["max_uri"] = max_uri

    # Only for informed method (ours) --> adding ranking
    if "informed" in type_system:
        config['type_ranking'] = args['type_ranking']
        if "ordering" not in config:
            config["ordering"] = {}
        config["ordering"]["domain_range"] = int(args['ordering_domain_range'])
    
    # Only for NautiLOD-like version, and LDSpider-like --> set uri_limit to 'all'
    if type_system in ['nautilod', 'ldspider']:
        config["uri_limit"] = "all"
        config["ordering"] = {}
        config["ordering"]["domain_range"] = 0

    # Only for random exploration  --> set uri_limit to 5
    if "random" in type_system:
        config["uri_limit"] = int(args["uri_limit"])
        config["ordering"] = {}
        config["ordering"]["domain_range"] = 0

    return config


def get_experiments(folder, date_start, date_end, name_exp, type_system):

    nb_files = 8 if "informed" in type_system else 7
    files = os.listdir(folder)
    files = [x for x in files if \
        x[:19] >= date_start and x[:19] <= date_end and \
            "_".join(x.split("_")[1:])[:1+len(name_exp)] == name_exp + "_" and \
                    len(os.listdir(os.path.join(folder, x))) == nb_files]
    
    if "informed" in type_system:
        files = [x for x in files if "informed" in x]
    if type_system == "nautilod":
        files = [x for x in files if "random" in x and "uri_iter_all" in x]
    if type_system == "ldspider":
        files = [x for x in files if "random" in x and "______" in x and "uri_iter_all" in x]
    if "random" in type_system:
        files = [x for x in files if "random" in x and "uri_iter_" in x and \
            x.split("uri_iter_")[1].split("_")[0].isdigit()]

    return files


def helper(pattern, x):
    return 1 if pattern in x else 0


def helper_ranking(file_name):
    for metric in ["entropy_pred_freq", "inverse_pred_freq",
                   "pred_freq",
                   "entropy_pred_object_freq", "inverse_pred_object_freq",
                   "pred_object_freq"]:
        if metric in file_name:
            return metric


def filter_params(folder, files, param_grid, type_system):
    """ Removing parameters that were already tested and finished """
    res = []
    for file in files:
        curr_dict = {
            "filtering_what": helper("what", file),
            "filtering_where": helper("where", file),
            "filtering_when": helper("when", file),
            "filtering_who": helper("who", file)
        }
        if "informed" in type_system:
            curr_dict["ordering_domain_range"] = helper("domain_range", file)
            curr_dict["type_ranking"] = helper_ranking(file_name=file)
        if "random" in type_system:
            cand = file.split("uri_iter_")[1].split("_")[0]
            if cand.isdigit():
                curr_dict["uri_limit"] = int(cand)
        res.append(curr_dict)
    return [x for x in param_grid if x not in res]


def get_args_grid_one_event(config, iteration, param_grid, date_start, date_end, name_exp, dataset, type_system):
    params = list(ParameterGrid(param_grid))
    files = get_experiments(folder=os.path.join(FOLDER_PATH, "experiments"),
                            date_start=date_start, date_end=date_end,
                            name_exp=name_exp,
                            type_system=type_system)
    params = filter_params(folder=os.path.join(FOLDER_PATH, "experiments"),
                           files=files, param_grid=params, type_system=type_system)
    return [update_config(config, param, iteration, dataset, type_system) for param in params]

# --------------------

if __name__ == '__main__':
    possible_systems = ["informed_epof", "informed_pof", "informed_epf", "informed_pf", "nautilod", "ldspider", "random_5", "random_10", "random_15"]

    ap = argparse.ArgumentParser()
    ap.add_argument("-t", "--type_system", required=True,
                    help=f"Type of system to run, must be in {possible_systems}")
    ap.add_argument("-e", "--experiments", required=True,
                    help="Path csv file containing the info for experiments to run\n" + \
                         "3 columns required: `event_name` (URI of starting event), `iterations` (int, # of iterations), `dataset` (either `wikidata` or `dbpedia`")
    args_main = vars(ap.parse_args())
    
    if not args_main["type_system"] in possible_systems:
        raise ValueError(f"`type_system` must be among values {possible_systems}")
    if not args_main["experiments"].endswith(".csv"):
        raise ValueError(f"`experiments` must be a .csv file")
                                        
    df = pd.read_csv(args_main["experiments"])
    args_grid = []
    for _, row in df.iterrows():
        event_name = row['event_name'].split('/')[-1].split(".")[0]
        if os.path.exists(os.path.join(FOLDER_PATH, "data-test", row["dataset"], "config", f"{event_name}.json")) and \
            os.path.exists(os.path.join(FOLDER_PATH, "data-test", row["dataset"], "referents", f"{event_name}.json")):
            with open(os.path.join(FOLDER_PATH, "data-test", row["dataset"], "config", f"{event_name}.json"), 'r', encoding="utf-8") as openfile:
                config = json.load(openfile)

            to_add = get_args_grid_one_event(config=config, iteration=row["iterations"],
                                             param_grid=PARAMS[args_main["type_system"]],
                                             date_start=DATES[args_main["type_system"]]["start"], date_end=DATES[args_main["type_system"]]["end"], name_exp=f"{row['dataset']}_{event_name}",
                                             dataset=row["dataset"], type_system=args_main["type_system"])
            args_grid += to_add
            print(event_name, len(to_add))
        else:
            print(event_name)
    
    @killer_call(timeout=36000)
    def main(config, type_system):
        config["rdf_type"] = list(config["rdf_type"].items())
        if "informed" in type_system:
            framework = GraphSearchFramework(config=config, walk="informed")
        else:
            framework = GraphSearchFramework(config=config, walk="random")
        framework()

    # killer_pmap(lambda config: main(config, type_system=args_main["type_system"]), args_grid, timeout=36000)

    helper = lambda k, v: k if v else ""
    from collections import Counter
    params = [v["filtering"] for v in args_grid]
    params = ["_".join([helper(y, x[y]) for y in ["what", "where", "when", "who"]]) for x in params]
    print(Counter(params))
    # for elt in args_grid:
    #     print(elt["name_exp"])
    print(len(args_grid))

    # f = open(f"experiments_swj/missing-21_{args_main['type_system']}.txt", "w+")
    # for i, v in enumerate(args_grid):
    #     f.write(f"{v['name_exp']}_{params[i]}\n")
    # f.close()

