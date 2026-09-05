"""
Turns temporal features into a risk score, a plain-English explanation,
and a bounded decision. Deliberately rule-based and transparent rather
than a black-box model, so every flag traces to specific, inspectable
feature values -- an analyst (or a panel) can see exactly why a group
was flagged.

Two-stage design:

  STRUCTURAL score = "is this a ring at all" (device/IP/account-burst/amount
  similarity). Persistent -- a real ring stays structurally suspicious for
  its whole lifetime, before and after it acts.

  ESCALATION signal = "is something happening RIGHT NOW" (a recent burst of
  activity, or transfers starting to concentrate on one beneficiary).
  This is what turns "known ring, nothing new" into "predicted cash-out
  within 6h" -- gating on both conditions (still structurally a ring, AND
  showing fresh activity) keeps that specific claim meaningful rather than
  firing continuously on old suspicion.
"""

STRUCTURAL_WEIGHTS = {
    "device_reuse_ratio": 0.40,
    "ip_overlap_ratio": 0.35,
    "accounts_created_ratio": 0.20,
    "amount_similarity": 0.05,
}

STRUCTURAL_HIGH = 0.55     # "this is a ring" bar
STRUCTURAL_MEDIUM = 0.40
ESCALATION_TRIGGER = 0.15  # any fresh recent activity or early beneficiary concentration


def structural_score(features):
    return sum(STRUCTURAL_WEIGHTS[k] * features[k] for k in STRUCTURAL_WEIGHTS)


def escalation_signal(features):
    return max(features["time_clustering_ratio"], features["beneficiary_concentration"])


def score(features):
    struct = structural_score(features)
    esc = escalation_signal(features)
    # escalation acts as a 0.5x-1.0x multiplier: a structurally-confirmed ring
    # with zero fresh activity is reported at half its structural score, not
    # zero -- it's still worth a MEDIUM/monitor entry in the audit trail.
    risk = struct * (0.5 + 0.5 * min(esc, 1.0))
    return round(min(risk, 1.0), 4)


def decide(features):
    struct = structural_score(features)
    esc = escalation_signal(features)

    if struct >= STRUCTURAL_HIGH and esc >= ESCALATION_TRIGGER:
        return "HIGH", "predicted_cashout_within_6h"
    if struct >= STRUCTURAL_MEDIUM:
        return "MEDIUM", "step_up_verification"
    return "LOW", "monitor"


def explain(features):
    parts = []
    if features["accounts_created_within_24h"] >= 3:
        parts.append(f"{features['accounts_created_within_24h']} accounts were created within 24 hours")
    if features["device_reuse_ratio"] >= 0.5:
        parts.append(f"{features['device_reuse_count']} accounts share the same device")
    if features["ip_overlap_ratio"] >= 0.5:
        parts.append(f"{features['ip_overlap_count']} accounts share the same IP range")
    if features["amount_similarity"] >= 0.6:
        parts.append("transaction amounts are unusually similar across the group")
    if features["beneficiary_concentration"] > 0:
        parts.append(
            f"{features['beneficiary_senders']} account(s) are already sending funds toward one "
            f"beneficiary ({features['beneficiary_concentration']*100:.0f}% of the group so far)"
        )
    if features["time_clustering_ratio"] >= 0.4:
        parts.append("the group has shown a burst of activity in the last few hours")

    if not parts:
        return "No strong coordinated-behaviour signal detected."
    return "Predicted because " + ", ".join(parts) + "."


def evaluate_cluster(features):
    risk_score = score(features)
    severity, action_code = decide(features)
    explanation = explain(features)
    return {
        "risk_score": risk_score,
        "severity": severity,
        "action_code": action_code,
        "explanation": explanation,
    }
