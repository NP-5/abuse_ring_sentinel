"""Append-only audit trail. Every decision this system makes is logged --
including LOW/MONITOR outcomes -- so the full reasoning history is
reconstructable after the fact."""
import json
import os

AUDIT_LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "audit_log.jsonl")


def log_decision(observation_time, cluster, features, verdict, intervention):
    record = {
        "observation_time_hr": round(observation_time, 3),
        "cluster_members": cluster["members"],
        "cluster_size": features["cluster_size"],
        "features": {k: v for k, v in features.items() if not k.startswith("top_")},
        "shared_attributes": {
            "device": features.get("top_device"),
            "ip_prefix": features.get("top_ip_prefix"),
            "beneficiary": features.get("top_beneficiary"),
        },
        "risk_score": verdict["risk_score"],
        "severity": verdict["severity"],
        "explanation": verdict["explanation"],
        "intervention": intervention,
    }
    with open(AUDIT_LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")
    return record


def reset_log():
    if os.path.exists(AUDIT_LOG_PATH):
        os.remove(AUDIT_LOG_PATH)


def read_log():
    if not os.path.exists(AUDIT_LOG_PATH):
        return []
    with open(AUDIT_LOG_PATH) as f:
        return [json.loads(line) for line in f]
