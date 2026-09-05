"""
For a candidate cluster (from ring_detector.py), computes the temporal /
behavioural signals that separate "just a few accounts that happen to
share a device" from "a group actively converging on a coordinated
cash-out". All features are computed only from data with
timestamp <= observation_time.
"""
import numpy as np
from collections import Counter

RECENT_WINDOW_HOURS = 6  # "is this group active RIGHT NOW" -- matches checkpoint cadence
                          # so there's no gap between what one cycle checks and the next


def compute_features(cluster_members, accounts_df, transactions_df, observation_time, lookback_hours):
    window_start = observation_time - lookback_hours
    acc_rows = accounts_df[accounts_df["account_id"].isin(cluster_members)]
    txn_rows = transactions_df[
        (transactions_df["account_id"].isin(cluster_members)) &
        (transactions_df["timestamp"] <= observation_time) &
        (transactions_df["timestamp"] >= window_start)
    ]

    n = len(cluster_members)

    # 1. burst account creation
    created = acc_rows["created_at"].values
    if len(created) > 0:
        earliest = created.min()
        created_within_24h = int(np.sum(created - earliest <= 24))
    else:
        created_within_24h = 0
    accounts_created_ratio = created_within_24h / max(n, 1)

    # 2. device reuse
    device_counts = Counter(acc_rows["device_id"])
    top_device, top_device_count = (device_counts.most_common(1) or [(None, 0)])[0]
    device_reuse_ratio = top_device_count / max(n, 1)

    # 3. ip overlap
    ip_counts = Counter(acc_rows["ip_prefix"])
    top_ip, top_ip_count = (ip_counts.most_common(1) or [(None, 0)])[0]
    ip_overlap_ratio = top_ip_count / max(n, 1)

    # 4. amount similarity on 'purchase' txns (low variance = suspiciously uniform)
    purchase_amounts = txn_rows[txn_rows["type"] == "purchase"]["amount"].values
    if len(purchase_amounts) >= 3:
        cv = np.std(purchase_amounts) / (np.mean(purchase_amounts) + 1e-9)
        amount_similarity = float(max(0.0, 1.0 - min(cv, 1.0)))
    else:
        amount_similarity = 0.0

    # 5. beneficiary concentration on 'transfer' txns -- the key cash-out signal.
    # Scoped to the RECENT window only, not the full lookback: a transfer
    # that happened 2 days ago is evidence the group already cashed out, not
    # evidence it is ABOUT TO -- using the full lookback would keep the
    # signal "hot" long after the event and cause the system to keep
    # predicting a cash-out that already happened.
    recent_start_for_ben = observation_time - RECENT_WINDOW_HOURS
    transfer_rows = txn_rows[
        (txn_rows["type"] == "transfer") & (txn_rows["timestamp"] >= recent_start_for_ben)
    ]
    if len(transfer_rows) > 0:
        ben_counts = Counter(transfer_rows["beneficiary_id"])
        top_ben, top_ben_count = ben_counts.most_common(1)[0]
        distinct_senders = transfer_rows[transfer_rows["beneficiary_id"] == top_ben]["account_id"].nunique()
        beneficiary_concentration = distinct_senders / max(n, 1)
    else:
        top_ben, distinct_senders = None, 0
        beneficiary_concentration = 0.0

    # 6. right-now activity burst (precursor signal)
    recent_start = observation_time - RECENT_WINDOW_HOURS
    recent_active = txn_rows[txn_rows["timestamp"] >= recent_start]["account_id"].nunique()
    time_clustering_ratio = recent_active / max(n, 1)

    return {
        "cluster_size": n,
        "accounts_created_within_24h": created_within_24h,
        "accounts_created_ratio": accounts_created_ratio,
        "top_device": top_device, "device_reuse_count": top_device_count,
        "device_reuse_ratio": device_reuse_ratio,
        "top_ip_prefix": top_ip, "ip_overlap_count": top_ip_count,
        "ip_overlap_ratio": ip_overlap_ratio,
        "amount_similarity": amount_similarity,
        "top_beneficiary": top_ben, "beneficiary_senders": distinct_senders,
        "beneficiary_concentration": beneficiary_concentration,
        "time_clustering_ratio": time_clustering_ratio,
    }
