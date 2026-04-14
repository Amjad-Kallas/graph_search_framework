import pandas as pd
import networkx as nx
import os

class StoryCentralityPruner:
    def __init__(self, damping_factor=0.85):
        self.alpha = damping_factor

    def build_graph(self, df: pd.DataFrame):
        G = nx.from_pandas_edgelist(
            df,
            source='object',   # reversed for PageRank ONLY
            target='subject',
            create_using=nx.DiGraph()
        )
        return G

    '''def compute_pagerank(self, G):
        return nx.pagerank(G, alpha=self.alpha)'''

    # PPR instead of a standard PageRank
    def compute_pagerank(self, G, seed_topic):
        # Safety check: ensure the exact DBpedia URI exists in the graph
        if seed_topic not in G.nodes():
            print(f"WARNING: Seed topic '{seed_topic}' not found in graph nodes. Falling back to standard PageRank.")
            return nx.pagerank(G, alpha=self.alpha)
            
        # Create a bias dictionary: 1.0 for our seed, 0 for everything else
        personalization = {node: 0 for node in G.nodes()}
        personalization[seed_topic] = 1.0
        
        return nx.pagerank(G, alpha=self.alpha, personalization=personalization)

    def prune_by_percentile(self, df: pd.DataFrame, seed_topic, keep_top_percent=0.5):

        if 'type_df' in df.columns:
            df = df[df['type_df'] == 'ingoing'].copy()

        G = self.build_graph(df)
        pagerank_scores = self.compute_pagerank(G, seed_topic)

        nodes_df = pd.DataFrame(
            list(pagerank_scores.items()),
            columns=['node_uri', 'pagerank_score']
        )

        # Normalize
        min_score = nodes_df['pagerank_score'].min()
        max_score = nodes_df['pagerank_score'].max()

        if max_score != min_score:
            nodes_df['pagerank_score'] = (
                (nodes_df['pagerank_score'] - min_score) /
                (max_score - min_score)
            )
        else:
            nodes_df['pagerank_score'] = 0

        threshold = nodes_df['pagerank_score'].quantile(1.0 - keep_top_percent)

        top_nodes = nodes_df[
            nodes_df['pagerank_score'] >= threshold
        ]['node_uri'].tolist()

        # Hard-anchor the required seed topic
        if seed_topic not in top_nodes:
            top_nodes.append(seed_topic)

        nodes_df_sorted = nodes_df[
            nodes_df['node_uri'].isin(top_nodes)
        ].sort_values(by='pagerank_score', ascending=False)

        return nodes_df_sorted



    def analyze_graph(self, df):
        G = nx.from_pandas_edgelist(df, 'subject', 'object', create_using=nx.Graph())

        num_nodes = G.number_of_nodes()
        num_edges = G.number_of_edges()

        print("\n----- GRAPH METRICS -----")
        print(f"Nodes: {num_nodes}")
        print(f"Edges: {num_edges}")

        # Average degree
        avg_degree = sum(dict(G.degree()).values()) / num_nodes if num_nodes > 0 else 0
        print(f"Average degree: {avg_degree:.2f}")

        # Connected components
        components = list(nx.connected_components(G))
        num_components = len(components)

        print(f"Connected components: {num_components}")

        if components:
            largest_cc = max(components, key=len)
            largest_size = len(largest_cc)

            print(f"Largest component size: {largest_size}")
            print(f"% in largest component: {100 * largest_size / num_nodes:.2f}%")


        print("--------------------------")


    '''def topk_with_neighbors(self, df, node_scores, k):
        top_k_nodes = node_scores.nlargest(k, 'pagerank_score')['node_uri'].tolist()

        pruned = df[
            df['subject'].isin(top_k_nodes) | df['object'].isin(top_k_nodes)
        ].copy()
        return pruned, top_k_nodes'''

    def topk_with_neighbors(self, df, node_scores, k, seed_topic):
        top_k_nodes = node_scores.nlargest(k, 'pagerank_score')['node_uri'].tolist()
        
        # Hard-anchor the required seed topic into the Top K list
        if seed_topic not in top_k_nodes:
            top_k_nodes.append(seed_topic)

        pruned = df[
            df['subject'].isin(top_k_nodes) | df['object'].isin(top_k_nodes)
        ].copy()
        return pruned, top_k_nodes


    def save_subgraph(self, df, path="pruned_subgraph.csv"):
        """
        Saves the DataFrame EXACTLY as input format.
        No edge direction changes are applied here.
        """
        df.to_csv(path, index=False)
        print(f"\nSaved pruned subgraph to: {path}")


    def keep_largest_component(self, df):
        """
        Keeps only edges that belong to the largest connected component
        """
        # Build undirected graph for connectivity
        G = nx.from_pandas_edgelist(df, 'subject', 'object', create_using=nx.Graph())

        # Find largest component
        largest_cc = max(nx.connected_components(G), key=len)

        # Filter dataframe: keep edges where subject OR object is in largest CC
        filtered_df = df[
            df['subject'].isin(largest_cc) |
            df['object'].isin(largest_cc)
        ].copy()

        return filtered_df


    def run_pruning(self, subgraph_path, seed_topic, keep_top_percent=0.4, k=20):

        step1_df = pd.read_csv(subgraph_path)

        # Step 1: PageRank to get node scores
        node_scores = self.prune_by_percentile(
            step1_df,
            seed_topic=seed_topic,
            keep_top_percent=keep_top_percent
        )

        # Step 2: Apply Top-K + neighbors
        pruned_subgraph, top_k_nodes = self.topk_with_neighbors(
            step1_df,
            node_scores,
            seed_topic=seed_topic,
            k=k
        )

        # Step 3: Keep largest connected component
        pruned_subgraph = self.keep_largest_component(pruned_subgraph)


        print("\n--- COUNTS ---")
        print(f"Original edges: {len(step1_df)}")
        num_core_nodes = len(node_scores)
        num_graph_nodes = len(set(pruned_subgraph['subject']).union(set(pruned_subgraph['object'])))

        print(f"Top-K core nodes: {len(top_k_nodes)}")
        print(f"Total nodes in pruned graph: {num_graph_nodes}")
        
        #print(f"Pruned edges (connections) kept: {len(pruned_subgraph)}")


        self.analyze_graph(pruned_subgraph)


        base_dir = os.path.dirname(subgraph_path)
        original_name = os.path.basename(subgraph_path)

        new_name = f"pruned-{original_name}"
        output_path = os.path.join(base_dir, new_name)

        self.save_subgraph(pruned_subgraph, output_path)

        return output_path




# --- Example usage ---
if __name__ == "__main__":

    #step1_df = pd.read_csv("/home/kallas/project/graph_search_framework/sample-data/French_Revolution_subgraph.csv")
    #step1_df = pd.read_csv("/home/kallas/project/graph_search_framework/experiments/2026-03-28-18_21_41-informed_dbpedia_french_revolution_10_pred_object_freq_domain_range_what_where_when_who_wikilink_without_category_uri_iter__max_inf/10-subgraph.csv")
    step1_df = pd.read_csv("/home/kallas/project/graph_search_framework/experiments/2026-03-29-11_28_57-informed_dbpedia_french_revolution_50_pred_object_freq_domain_range_what_where_when_who_wikilink_without_category_uri_iter__max_inf/50-subgraph.csv")

    subgraph_path = "/home/kallas/project/graph_search_framework/experiments/2026-03-29-11_28_57-informed_dbpedia_french_revolution_50_pred_object_freq_domain_range_what_where_when_who_wikilink_without_category_uri_iter__max_inf/50-subgraph.csv"

    seed_topic = "http://dbpedia.org/resource/French_Revolution"

    pruner = StoryCentralityPruner()

    pruner.run_pruning(subgraph_path, seed_topic)

    exit()

    pruned_subgraph, node_scores = pruner.prune_by_percentile(
        step1_df,
        keep_top_percent=0.4
    )

    print("\nBefore LCC filtering:", len(pruned_subgraph))


    pruned_subgraph = pruner.keep_largest_component(pruned_subgraph)
    print("After LCC filtering:", len(pruned_subgraph))

    #print("\n--- Top Nodes by PageRank ---")
    #print(node_scores.head())

    #print("\n--- Pruned Step 1 Subgraph ---")
    #print(pruned_subgraph.head())

    # Basic counts
    print("\n--- COUNTS ---")
    print(f"Original edges: {len(step1_df)}")
    num_core_nodes = len(node_scores)
    num_graph_nodes = len(set(pruned_subgraph['subject']).union(set(pruned_subgraph['object'])))

    print(f"Core nodes (top PageRank): {num_core_nodes}")
    print(f"Total nodes in pruned graph: {num_graph_nodes}")
    
    #print(f"Pruned edges (connections) kept: {len(pruned_subgraph)}")


    pruner.analyze_graph(pruned_subgraph)


    pruner.save_subgraph(pruned_subgraph, "pruned_subgraph.csv")