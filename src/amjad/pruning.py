import pandas as pd
import networkx as nx
import os
import json

class StoryCentralityPruner:
    def __init__(self, damping_factor=0.85):
        self.alpha = damping_factor

    def build_graph(self, df: pd.DataFrame):
        # Use DiGraph to respect subject → object directionality
        return nx.from_pandas_edgelist(
            df,
            source='subject',
            target='object',
            create_using=nx.DiGraph()
        )

    def compute_pagerank(self, G, seed_topic):
        if seed_topic not in G.nodes():
            print(f"WARNING: Seed topic '{seed_topic}' not found in graph. Falling back to standard PageRank.")
            return nx.pagerank(G, alpha=self.alpha)

        epsilon = 1e-6
        personalization = {node: epsilon for node in G.nodes()}
        personalization[seed_topic] = 1.0

        total = sum(personalization.values())
        personalization = {k: v / total for k, v in personalization.items()}

        return nx.pagerank(G, alpha=self.alpha, personalization=personalization)

    def get_pagerank_scores(self, df: pd.DataFrame, seed_topic):
        # Don't filter by type_df here — keep full graph for topology
        G = self.build_graph(df)
        pagerank_dict = self.compute_pagerank(G, seed_topic)

        nodes_df = pd.DataFrame(
            list(pagerank_dict.items()),
            columns=['node_uri', 'pagerank_score']
        ).sort_values(by='pagerank_score', ascending=False)

        return nodes_df

    def analyze_graph(self, df):
        G = nx.from_pandas_edgelist(df, 'subject', 'object', create_using=nx.DiGraph())
        num_nodes = G.number_of_nodes()

        print("\n----- GRAPH METRICS -----")
        print(f"Nodes: {num_nodes}")
        print(f"Edges: {G.number_of_edges()}")

        if num_nodes > 0:
            avg_degree = sum(dict(G.degree()).values()) / num_nodes
            print(f"Average degree: {avg_degree:.2f}")

        # Use weakly connected components for DiGraph
        components = list(nx.weakly_connected_components(G))
        print(f"Weakly connected components: {len(components)}")

        if components:
            largest_size = len(max(components, key=len))
            print(f"Largest component size: {largest_size}")
            print(f"% in largest component: {100 * largest_size / num_nodes:.2f}%")
        print("--------------------------")

    def save_subgraph(self, df, path="pruned_subgraph.csv"):
        df.to_csv(path, index=False)
        print(f"\nSaved pruned subgraph to: {path}")

    def keep_seed_component(self, df, seed_topic):
        G = nx.from_pandas_edgelist(df, 'subject', 'object', create_using=nx.DiGraph())

        if not G.nodes() or seed_topic not in G.nodes():
            print(f"WARNING: Seed '{seed_topic}' lost before component filtering.")
            return df

        # Use weakly_connected_components for DiGraph
        for component in nx.weakly_connected_components(G):
            if seed_topic in component:
                # Fix: use & not | — both endpoints must be in the component
                seed_cc_df = df[
                    df['subject'].isin(component) & df['object'].isin(component)
                ].copy()
                print(f"Seed component found. Size: {len(component)} nodes.")
                return seed_cc_df

        return df
    
    def keep_high_level_nodes(self, df, seed_topic):
        from collections import defaultdict

        children_count = defaultdict(int)

        # count how many times a node is a parent
        for _, row in df.iterrows():
            parent = row["object"]
            children_count[parent] += 1

        # filter: iteration=1 AND has children
        filtered_df = df[
            (df["iteration"] == 1) &
            (df["subject"].map(lambda x: children_count.get(x, 0) > 0))
        ].copy()

        # always keep seed
        seed_rows = df[df["subject"] == seed_topic]
        filtered_df = pd.concat([filtered_df, seed_rows]).drop_duplicates()

        print(f"\n[High-level filter] kept {len(filtered_df)} edges")

        return filtered_df

    def topk_with_neighbors(self, df, nodes_df, k, seed_topic):

        top_k_nodes = set(nodes_df.head(k)['node_uri'].tolist())

        above_threshold = set(nodes_df.head(max(k*3, 50))['node_uri'])
        print("\n--- TOP 30 PAGERANK SCORES ---")
        print(nodes_df.head(30))

        combined = top_k_nodes | above_threshold
        combined.add(seed_topic)

        # Soft pass: 1-hop neighbor expansion from combined
        neighbors_expanded = df[
            df['subject'].isin(combined) | df['object'].isin(combined)
        ]
        expanded_nodes = set(neighbors_expanded['subject']) | set(neighbors_expanded['object'])

        # Strict second pass: expanded neighbors must also be above threshold
        final_nodes = (expanded_nodes & above_threshold) | top_k_nodes
        final_nodes.add(seed_topic)

        pruned = df[
            df['subject'].isin(final_nodes) & df['object'].isin(final_nodes)
        ].copy()

        '''print(f"Top-K nodes:                {len(top_k_nodes)}")
        print(f"Above-threshold nodes:      {len(above_threshold)}")
        print(f"Combined anchor nodes:      {len(combined)}")
        print(f"After neighbor expansion:   {len(expanded_nodes)}")
        print(f"After strict second pass:   {len(final_nodes)}")'''

        return pruned, list(final_nodes)


    def get_important_edges(self, df, subgraph_path):
        """
        Extracts edges involving important nodes so they can be injected 
        back into the graph after pruning is complete.
        """
        base_dir = os.path.dirname(subgraph_path)
        important_nodes_path = os.path.join(base_dir, "important_nodes.json")


        if not os.path.exists(important_nodes_path):
            print("No important_nodes.json file found. Skipping important nodes retention.")
            return pd.DataFrame() # Return empty dataframe

        with open(important_nodes_path, "r") as f:
            important_nodes = set(json.load(f))

        # Grab all edges where the subject or object is an important node
        important_edges_df = df[
            df['subject'].isin(important_nodes) | df['object'].isin(important_nodes)
        ].copy()

        print(f"Secured {len(important_edges_df)} edges involving important nodes for final injection.")
        return important_edges_df


    def run_pruning(self, subgraph_path, seed_topic, k=20):
        step1_df = pd.read_csv(subgraph_path)

        # Retain important edges
        important_edges_df = self.get_important_edges(step1_df, subgraph_path)

        nodes_df = self.get_pagerank_scores(step1_df, seed_topic)

        pruned_subgraph, top_k_nodes = self.topk_with_neighbors(
            step1_df, nodes_df, k=k, seed_topic=seed_topic
        )

        pruned_subgraph = self.keep_seed_component(pruned_subgraph, seed_topic=seed_topic)  # fixed

        if not important_edges_df.empty:
            pruned_subgraph = pd.concat([pruned_subgraph, important_edges_df]).drop_duplicates()

        print("\n--- COUNTS ---")
        print(f"Original edges:          {len(step1_df)}")
        print(f"Core nodes (combined):   {len(top_k_nodes)}")
        print(f"Total nodes after prune: {len(set(pruned_subgraph['subject']).union(set(pruned_subgraph['object'])))}")
        print(f"Edges after prune:       {len(pruned_subgraph)}")

        self.analyze_graph(pruned_subgraph)

        base_dir = os.path.dirname(subgraph_path)
        original_name = os.path.basename(subgraph_path)
        output_path = os.path.join(base_dir, f"pruned-{original_name}")

        self.save_subgraph(pruned_subgraph, output_path)
        return output_path

# --- Example usage ---
if __name__ == "__main__":

    #subgraph_path = "/home/kallas/project/graph_search_framework/french_revolution_triples.csv"

    subgraph_path = "/home/kallas/project/graph_search_framework/experiments/2026-04-28-10_21_51-informed_wikidata_french_revolution_2_pred_object_freq_domain_range__where_when__without_category_uri_iter__max_inf/2-subgraph.csv"

    seed_topic = "http://www.wikidata.org/entity/Q36w1"

    pruner = StoryCentralityPruner()

    pruner.run_pruning(subgraph_path, seed_topic)

