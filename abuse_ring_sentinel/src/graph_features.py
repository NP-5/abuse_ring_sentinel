"""
Builds an entity-link distance matrix between accounts that were active
(created, or transacted) within a lookback window ending at `observation_time`.

Two accounts are "close" (low distance) if they share a device_id, an IP /24
prefix, and/or a card BIN. This is fed to DBSCAN with metric='precomputed'
so DBSCAN clusters on shared identifiers rather than raw coordinates.

Only ever sees data with timestamp <= observation_time -- no lookahead.
"""
import numpy as np
import pandas as pd

W_DEVICE = 0.50
W_IP = 0.35
W_CARD = 0.15


def active_accounts(accounts_df, transactions_df, observation_time, lookback_hours):
    window_start = observation_time - lookback_hours
    created_recent = accounts_df[
        (accounts_df["created_at"] <= observation_time) &
        (accounts_df["created_at"] >= window_start)
    ]["account_id"]

    txns_in_window = transactions_df[
        (transactions_df["timestamp"] <= observation_time) &
        (transactions_df["timestamp"] >= window_start)
    ]
    txn_active = txns_in_window["account_id"]

    active_ids = pd.unique(pd.concat([created_recent, txn_active]))
    return accounts_df[accounts_df["account_id"].isin(active_ids)].reset_index(drop=True)


def build_distance_matrix(active_df):
    n = len(active_df)
    dist = np.ones((n, n))
    np.fill_diagonal(dist, 0.0)

    device = active_df["device_id"].values
    ip_prefix = active_df["ip_prefix"].values
    card = active_df["card_bin"].values

    for i in range(n):
        for j in range(i + 1, n):
            score = 0.0
            if device[i] == device[j]:
                score += W_DEVICE
            if ip_prefix[i] == ip_prefix[j]:
                score += W_IP
            if card[i] == card[j]:
                score += W_CARD
            d = 1.0 - min(score, 1.0)
            dist[i, j] = d
            dist[j, i] = d

    return dist
