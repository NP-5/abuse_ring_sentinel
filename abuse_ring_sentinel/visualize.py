"""Renders the entity-link graph for one flagged HIGH cluster from the audit
log, colouring shared-attribute edges, for use in the pitch video / README."""
import json
import sys
import os
import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


def load_high_record(path="audit_log.jsonl", index=0):
    with open(path) as f:
        records = [json.loads(l) for l in f]
    high = [r for r in records if r["severity"] == "HIGH"]
    return high[index]


def render(record, out_path="ring_graph.png"):
    G = nx.Graph()
    members = record["cluster_members"]
    shared = record["shared_attributes"]
    for m in members:
        G.add_node(m)
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            G.add_edge(members[i], members[j])

    plt.figure(figsize=(8, 6))
    pos = nx.spring_layout(G, seed=1)
    nx.draw_networkx_nodes(G, pos, node_color="#d64550", node_size=900)
    nx.draw_networkx_edges(G, pos, edge_color="#f0a6a6", width=1.5)
    nx.draw_networkx_labels(G, pos, font_size=7, font_color="white")

    title = (f"Flagged ring: {len(members)} accounts | risk={record['risk_score']} "
              f"| shared device={shared.get('device')}")
    plt.title(title, fontsize=10)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    print(f"Saved {out_path}")
    print("Explanation:", record["explanation"])


if __name__ == "__main__":
    rec = load_high_record()
    render(rec)
