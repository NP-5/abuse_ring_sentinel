"""
Converts a severity decision into the LEAST disruptive action available.
Deliberately bounded: this module can never freeze an account, block a
user, or take any offense-capable action. The strongest thing it can do
is hold a specific outgoing transfer for review.
"""


def recommend(severity, cluster_members, features, transactions_in_window):
    if severity == "HIGH":
        # Hold ONLY the outgoing transfers heading to the concentrated beneficiary --
        # not the accounts, not unrelated activity.
        top_ben = features.get("top_beneficiary")
        held_txn_ids = []
        if top_ben:
            held = transactions_in_window[
                (transactions_in_window["account_id"].isin(cluster_members)) &
                (transactions_in_window["type"] == "transfer") &
                (transactions_in_window["beneficiary_id"] == top_ben)
            ]
            held_txn_ids = held["txn_id"].tolist()
        return {
            "action": "HOLD_BENEFICIARY_TRANSFERS",
            "held_transaction_ids": held_txn_ids,
            "accounts_frozen": [],  # explicitly always empty -- bounded by design
            "note": "Only transfers toward the concentrated beneficiary are held for review. "
                    "Accounts remain active for unrelated activity.",
        }
    if severity == "MEDIUM":
        return {
            "action": "STEP_UP_VERIFICATION",
            "held_transaction_ids": [],
            "accounts_frozen": [],
            "note": "Next outgoing transfer from this group requires additional verification.",
        }
    return {
        "action": "MONITOR",
        "held_transaction_ids": [],
        "accounts_frozen": [],
        "note": "No action taken; group remains under passive observation.",
    }
