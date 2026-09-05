"""
Runs DBSCAN on the precomputed entity-link distance matrix to find
candidate rings: dense groups of accounts connected by shared device /
IP-prefix / card BIN. This is the same clustering technique used for
sensor-anomaly grouping in CLARO, retargeted from sensor readings to
account entity-links.

Noise points (label -1) are ordinary, unconnected customers and are dropped.
"""
from sklearn.cluster import DBSCAN


def detect_candidate_clusters(active_df, dist_matrix, eps=0.5, min_samples=3):
    if len(active_df) < min_samples:
        return []

    labels = DBSCAN(eps=eps, min_samples=min_samples, metric="precomputed").fit_predict(dist_matrix)

    clusters = []
    for label in set(labels):
        if label == -1:
            continue
        member_idx = [i for i, l in enumerate(labels) if l == label]
        if len(member_idx) < min_samples:
            continue
        member_ids = active_df.iloc[member_idx]["account_id"].tolist()
        clusters.append({
            "cluster_label": int(label),
            "members": member_ids,
        })
    return clusters
