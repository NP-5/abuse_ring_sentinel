"""
Synthetic data generator for the Ring Cash-Out Early Warning system.

Generates:
  - accounts:      one row per account (legit or ring member)
  - transactions:  purchase/topup/transfer events with timestamps (hours since start)
  - ground_truth:  ring_id -> member accounts + the TRUE cash-out time (hidden from the detector,
                    used only by evaluate.py to score predictions)

Everything is causal: the detector is only ever shown transactions/accounts with
timestamp <= observation_time. Ground truth is never fed into the detection pipeline.
"""
import random
import uuid
import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

HORIZON_HOURS = 480          # 20-day simulation window
N_LEGIT_ACCOUNTS = 300
N_RINGS = 12
RING_SIZE_RANGE = (4, 9)
N_LEGIT_SHARED_PAIRS = 15    # families/offices sharing a device -> false-positive stress test


def _new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _rand_ip():
    return f"10.{random.randint(0,50)}.{random.randint(0,255)}.{random.randint(1,254)}"


def _ip_prefix(ip):
    return ".".join(ip.split(".")[:3])


def generate():
    accounts = []
    transactions = []
    ground_truth = []

    # ---------- legit population ----------
    legit_ids = []
    for _ in range(N_LEGIT_ACCOUNTS):
        acc_id = _new_id("ACC")
        legit_ids.append(acc_id)
        created_at = random.uniform(0, HORIZON_HOURS - 24)
        accounts.append({
            "account_id": acc_id, "created_at": created_at,
            "device_id": _new_id("DEV"), "ip_address": _rand_ip(),
            "card_bin": f"{random.randint(400000,499999)}",
            "is_ring": False, "ring_id": None,
        })
        # sprinkle normal activity
        n_txns = random.randint(2, 20)
        for _ in range(n_txns):
            ts = random.uniform(created_at, HORIZON_HOURS)
            ttype = random.choices(["purchase", "topup", "transfer"], weights=[0.6, 0.25, 0.15])[0]
            transactions.append({
                "txn_id": _new_id("TXN"), "account_id": acc_id, "timestamp": ts,
                "amount": round(random.uniform(50, 5000), 2), "type": ttype,
                "beneficiary_id": _new_id("BEN") if ttype == "transfer" else None,
            })

    # ---------- legit shared-device/office pairs (false-positive stress test) ----------
    for _ in range(N_LEGIT_SHARED_PAIRS):
        shared_device = _new_id("DEV")
        shared_ip = _rand_ip()
        group_size = random.randint(2, 3)
        base_created = random.uniform(0, HORIZON_HOURS - 100)
        for _ in range(group_size):
            acc_id = _new_id("ACC")
            legit_ids.append(acc_id)
            accounts.append({
                "account_id": acc_id, "created_at": base_created + random.uniform(0, 200),
                "device_id": shared_device, "ip_address": shared_ip,
                "card_bin": f"{random.randint(400000,499999)}",
                "is_ring": False, "ring_id": None,
            })
            for _ in range(random.randint(3, 10)):
                ts = random.uniform(base_created, HORIZON_HOURS)
                ttype = random.choices(["purchase", "topup", "transfer"], weights=[0.6, 0.25, 0.15])[0]
                transactions.append({
                    "txn_id": _new_id("TXN"), "account_id": acc_id, "timestamp": ts,
                    "amount": round(random.uniform(50, 5000), 2), "type": ttype,
                    "beneficiary_id": _new_id("BEN") if ttype == "transfer" else None,
                })

    # ---------- fraud rings ----------
    for r in range(N_RINGS):
        ring_id = f"RING-{r:02d}"
        ring_size = random.randint(*RING_SIZE_RANGE)
        ring_start = random.uniform(20, HORIZON_HOURS - 100)
        cash_out_time = ring_start + random.uniform(12, 72)
        beneficiary_id = _new_id("BEN")

        shared_device = _new_id("DEV") if random.random() < 0.7 else None
        shared_ip = _rand_ip() if random.random() < 0.6 else None
        members = []

        for i in range(ring_size):
            acc_id = _new_id("ACC")
            members.append(acc_id)
            created_at = ring_start + random.uniform(0, 20)  # burst creation
            accounts.append({
                "account_id": acc_id, "created_at": created_at,
                "device_id": shared_device if (shared_device and random.random() < 0.8) else _new_id("DEV"),
                "ip_address": shared_ip if (shared_ip and random.random() < 0.7) else _rand_ip(),
                "card_bin": f"{random.randint(500000,509999)}",  # ring BIN cluster
                "is_ring": True, "ring_id": ring_id,
            })

            # "test" transactions: small, similar amounts, build history.
            # Real rings ramp UP activity as cash-out approaches rather than
            # transacting uniformly at random, so sample backward from
            # cash_out_time with exponential decay -- most test activity
            # clusters in the hours just before the event, with a long tail
            # further back.
            base_amount = random.uniform(80, 150)
            for _ in range(random.randint(2, 5)):
                hours_before = np.random.exponential(scale=10)
                ts = max(created_at, cash_out_time - 3 - hours_before)
                transactions.append({
                    "txn_id": _new_id("TXN"), "account_id": acc_id, "timestamp": ts,
                    "amount": round(base_amount * random.uniform(0.9, 1.1), 2), "type": "purchase",
                    "beneficiary_id": None,
                })

            # coordinated cash-out transfer, tight time window around cash_out_time
            if random.random() < 0.85:  # not every member necessarily participates
                ts = cash_out_time + random.uniform(-2, 2)
                transactions.append({
                    "txn_id": _new_id("TXN"), "account_id": acc_id, "timestamp": max(ts, created_at + 0.1),
                    "amount": round(random.uniform(3000, 15000), 2), "type": "transfer",
                    "beneficiary_id": beneficiary_id,
                })

        ground_truth.append({
            "ring_id": ring_id, "members": members,
            "cash_out_time": cash_out_time, "beneficiary_id": beneficiary_id,
        })

    accounts_df = pd.DataFrame(accounts)
    transactions_df = pd.DataFrame(transactions).sort_values("timestamp").reset_index(drop=True)
    gt_df = pd.DataFrame(ground_truth)

    accounts_df["ip_prefix"] = accounts_df["ip_address"].apply(_ip_prefix)
    return accounts_df, transactions_df, gt_df


if __name__ == "__main__":
    acc, txn, gt = generate()
    acc.to_csv("data_accounts.csv", index=False)
    txn.to_csv("data_transactions.csv", index=False)
    gt.to_csv("data_ground_truth.csv", index=False)
    print(f"accounts={len(acc)} transactions={len(txn)} rings={len(gt)}")
    print(gt[["ring_id", "cash_out_time"]])
