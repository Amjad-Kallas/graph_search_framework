# -*- coding: utf-8 -*-
"""
Filtering class: Filtering out certain types of nodes
- Given a specific narrative dimension (who/where/when)
- Two types of filtering can be applied
    - Filtering on subgraph: node that matches the node type to be searched,
    but some properties don't match
        --> filtered out from subgraph, and removed from expandable nodes space
    - Filtering on pending nodes (nodes that could be expanded): same than above but for expansion
        --> removed from expandable nodes space
"""
import re
from pandas.core.frame import DataFrame

class Filtering:
    """
    Main Filtering class for subgraph and pending nodes

    """
    def __init__(self, args: dict):
        """
        - `args`: dict, keys = narrative dimensions, value = boolean
        """
        self._check_args(args=args)
        self.where = args["where"] if "where" in args else 0
        self.when = args["when"] if "when" in args else 0
        self.who = args["who"] if "who" in args else 0

        if all(x in args for x in ["point_in_time", "start_dates", "end_dates"]):
            if all(args[x] for x in ["point_in_time", "start_dates", "end_dates"]):
                self.time = {
                    "point_in_time": args["point_in_time"],
                    "start_dates": args["start_dates"],
                    "end_dates": args["end_dates"],
                    "temporal": args["point_in_time"] + args["start_dates"] + args["end_dates"]
                }
        else:
            self.time = None

        self.places = args["places"]
        self.people = args["people"]

        self.dataset_type = args["dataset_type"]

    @staticmethod
    def _check_args(args: dict):
        """ Check arguments when instantiating """
        for val in ["where", "when"]:
            if val in args and args[val] not in [0, 1]:
                raise ValueError(f"`{val}` value from args should be 0 or 1 (int)")

    def get_to_discard_date(self, date_df: DataFrame, dates: list[str]) -> DataFrame:
        """ Filtering on temporal dimension
        - checking date/start date/end date """

        return list(date_df[((date_df.predicate.isin(self.time["end_dates"])) & \
                             (date_df.object < dates[0])) | \
                            ((date_df.predicate.isin(self.time["start_dates"])) & \
                             (date_df.object > dates[1])) | \
                            ((date_df.predicate.isin(self.time["point_in_time"])) & \
                             (date_df.object < dates[0])) | \
                            ((date_df.predicate.isin(self.time["point_in_time"])) & \
                             (date_df.object > dates[1]))].subject.unique())

    @staticmethod
    def regex_helper(val: str, default_return_val: str) -> str:
        """ Finding regex column name in subject str uri """
        pattern = "\\d{4}"
        matches = re.findall(pattern, val)
        if matches:
            return str(matches[0])
        return default_return_val


    def get_to_discard_regex(self, ingoing: DataFrame,
                             outgoing: DataFrame, dates: list[str]) \
                                -> list[str]:
        """ Filtering on string uri
        - temporal dimension: regex on the URL (and therefore name of the events,
            e.g. 1997_National_Championships > non relevant """
        if ingoing.shape[0] > 0:
            ingoing['regex_helper']= ingoing["subject"].apply(
                lambda x: self.regex_helper(x, dates[0][:4]))
            ingoing_discard = list(ingoing[(ingoing.regex_helper < dates[0][:4]) | \
                                       (ingoing.regex_helper > dates[1][:4])].subject.unique())
        else:
            ingoing_discard = []

        if outgoing.shape[0] > 0:
            outgoing['regex_helper']= outgoing["object"].apply(
                lambda x: self.regex_helper(x, dates[0][:4]))
            outgoing_discard = list(outgoing[(outgoing.regex_helper < dates[0][:4]) | \
                                         (outgoing.regex_helper > dates[1][:4])].object.unique())
        else:
            outgoing_discard = []

        return ingoing_discard + outgoing_discard

    def get_to_discard_location(self, df_pd: DataFrame) -> list[str]:
        """ Location filter: retrieving nodes that correspond to locations
        (would be too broad for the search, hence later discarded """
        return list(df_pd[df_pd.object.isin(self.places)].subject.unique())

    def get_to_discard_entity(self, df_pd: DataFrame, filter_type: list[str]) \
        -> list[str]:
        """ Entity-based filter: retrieving nodes corresponding to any of the
        types in filter. Applicable for:
        WHERE-filter: locations
        WHO-filter: people """
        return list(df_pd[df_pd.object.isin(filter_type)].subject.unique())

    def __call__(self, ingoing: DataFrame, outgoing: DataFrame,
                 type_date: DataFrame, dates: list[str]) -> list[str]:
        """
        Extracting list of nodes to discard from search space
        """
        date_df = type_date[type_date.predicate.isin(self.time["temporal"])].copy()
        date_df.object = date_df.object.astype(str)

        to_discard = []

        if self.where:
            to_discard += list(set(self.get_to_discard_entity(
                df_pd=type_date, filter_type=self.places)))

        if self.who:
            to_discard += list(set(self.get_to_discard_entity(
                df_pd=type_date, filter_type=self.people)))

        if dates:
            if self.when and self.time:
                to_discard += list(set(self.get_to_discard_date(date_df=date_df, dates=dates)))

            if self.when and self.dataset_type in ["dbpedia"]:
                to_discard += list(set(self.get_to_discard_regex(ingoing=ingoing, outgoing=outgoing,
                                                                dates=dates)))

        return to_discard
