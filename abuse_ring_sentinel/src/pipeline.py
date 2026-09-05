"""
Orchestrates one full detection cycle at a given observation_time:
  active accounts -> distance matrix -> DBSCAN clusters -> temporal features
  -> risk score + explanation -> bounded intervention -> audit log.

Also provides run_simulation() which steps this across the whole timeline
at fixed checkpoints, for evaluate.py to score against ground truth.
"""
import pandas as pd
from graph_features import active_accounts, build_distance_matrix
from ring_detector import detect_candidate_clusters
from temporal_features import compute_features
from predictor import evaluate_cluster
from intervention import recommend
from audit import log_decision

LOOKBACK_HOURS = 72
MIN_CLUSTER_SIZE = 3


def run_cycle(observation_time, accounts_df, transactions_df, log=True):
    active_df = active_accounts(accounts_df, transactions_df, observation_time, LOOKBACK_HOURS)
    if len(active_df) < MIN_CLUSTER_SIZE:
        return []

    dist = build_distance_matrix(active_df)
    clusters = detect_candidate_clusters(active_df, dist, min_samples=MIN_CLUSTER_SIZE)

    window_txns = transactions_df[
        (transactions_df["timestamp"] <= observation_time) &
        (transactions_df["timestamp"] >= observation_time - LOOKBACK_HOURS)
    ]

    results = []
    for cluster in clusters:
        features = compute_features(cluster["members"], accounts_df, transactions_df,
                                      observation_time, LOOKBACK_HOURS)
        verdict = evaluate_cluster(features)
        action = recommend(verdict["severity"], cluster["members"], features, window_txns)
        record = {
            "observation_time": observation_time,
            "members": cluster["members"],
            "features": features,
            "verdict": verdict,
            "intervention": action,
        }
        if log:
            log_decision(observation_time, cluster, features, verdict, action)
        results.append(record)
    return results


def run_simulation(accounts_df, transactions_df, horizon_hours, checkpoint_every=6, log=True):
    all_cycles = []
    t = 24  # give the system a day of history before it starts predicting
    while t <= horizon_hours:
        cycle_results = run_cycle(t, accounts_df, transactions_df, log=log)
        all_cycles.append((t, cycle_results))
        t += checkpoint_every
    return all_cycles
