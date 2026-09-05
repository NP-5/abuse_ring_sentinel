"""
Scores the pipeline against the hidden ground truth. This file is the
only place ground_truth is allowed to touch the pipeline's output --
never fed forward into detection itself.

Reports exactly the five metrics the track asks for:
  1. Precision of ring detection
  2. Accuracy of next-action (cash-out) prediction
  3. Detection time (lead time) before cash-out
  4. False-positive rate
  5. Number of legitimate customers affected
"""
from collections import defaultdict

PREDICTION_WINDOW_HOURS = 6


def match_cluster_to_ring(members, ground_truth_df, min_overlap_frac=0.5):
    members_set = set(members)
    best_ring, best_overlap = None, 0
    for _, row in ground_truth_df.iterrows():
        ring_members = set(row["members"])
        overlap = len(members_set & ring_members)
        if overlap == 0:
            continue
        if overlap / len(members_set) >= min_overlap_frac and overlap > best_overlap:
            best_ring, best_overlap = row["ring_id"], overlap
    return best_ring


def evaluate(all_cycles, ground_truth_df, accounts_df):
    ring_lookup = {row["ring_id"]: set(row["members"]) for _, row in ground_truth_df.iterrows()}
    cash_out_time = {row["ring_id"]: row["cash_out_time"] for _, row in ground_truth_df.iterrows()}
    ring_accounts = set().union(*ring_lookup.values()) if ring_lookup else set()

    seen_clusters = set()          # dedup (ring_match_or_None, frozenset(members))
    cluster_matches = []           # (t, ring_id_or_None, severity, members)
    high_calls_matched = defaultdict(list)   # ring_id -> [t, t, ...] of HIGH calls matched to it
    legit_affected = set()

    for t, cycle_results in all_cycles:
        for r in cycle_results:
            members = r["members"]
            severity = r["verdict"]["severity"]
            matched_ring = match_cluster_to_ring(members, ground_truth_df)

            key = (matched_ring, frozenset(members))
            seen_clusters.add(key)
            cluster_matches.append((t, matched_ring, severity, members))

            if severity in ("HIGH", "MEDIUM"):
                for m in members:
                    if m not in ring_accounts:
                        legit_affected.add(m)

            if severity == "HIGH" and matched_ring:
                high_calls_matched[matched_ring].append(t)

    # ---- 1. ring detection precision / recall (structural) ----
    unique_clusters = seen_clusters
    matched_unique = [c for c in unique_clusters if c[0] is not None]
    detection_precision = len(matched_unique) / len(unique_clusters) if unique_clusters else 0.0
    rings_ever_detected = {c[0] for c in matched_unique}
    detection_recall = len(rings_ever_detected) / len(ring_lookup) if ring_lookup else 0.0

    # ---- 2. next-action (cash-out) prediction accuracy + 3. lead time ----
    correctly_predicted_rings = {}
    for ring_id, times in high_calls_matched.items():
        cot = cash_out_time[ring_id]
        valid_times = [t for t in times if 0 <= (cot - t) <= PREDICTION_WINDOW_HOURS]
        if valid_times:
            earliest = min(valid_times)
            correctly_predicted_rings[ring_id] = cot - earliest  # lead time

    next_action_recall = len(correctly_predicted_rings) / len(ring_lookup) if ring_lookup else 0.0

    total_high_matched_calls = sum(len(v) for v in high_calls_matched.values())
    correct_window_calls = sum(
        1 for ring_id, times in high_calls_matched.items()
        for t in times if 0 <= (cash_out_time[ring_id] - t) <= PREDICTION_WINDOW_HOURS
    )
    next_action_precision = (
        correct_window_calls / total_high_matched_calls if total_high_matched_calls else 0.0
    )

    avg_lead_time = (
        sum(correctly_predicted_rings.values()) / len(correctly_predicted_rings)
        if correctly_predicted_rings else None
    )

    # ---- 4. false positive rate ----
    unmatched_unique = [c for c in unique_clusters if c[0] is None]
    false_positive_rate = len(unmatched_unique) / len(unique_clusters) if unique_clusters else 0.0

    return {
        "rings_total": len(ring_lookup),
        "ring_detection_precision": round(detection_precision, 3),
        "ring_detection_recall": round(detection_recall, 3),
        "next_action_prediction_precision": round(next_action_precision, 3),
        "next_action_prediction_recall": round(next_action_recall, 3),
        "avg_detection_lead_time_hours": round(avg_lead_time, 2) if avg_lead_time is not None else None,
        "false_positive_rate": round(false_positive_rate, 3),
        "legitimate_customers_affected": len(legit_affected),
        "rings_correctly_predicted_before_cashout": sorted(correctly_predicted_rings.keys()),
    }
