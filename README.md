# Ring Cash-Out Early Warning (Abuse Ring Sentinel)
**Track 2 — AI Risk Manager | Razorpay AI Buildathon 2026**

---

## 📌 Executive Summary
Per-transaction fraud scoring models evaluate transactions in isolation, asking: *"Is this specific transaction suspicious?"* This creates a systemic blind spot for **coordinated fraud rings**—groups of accounts sharing devices, IP ranges, or payment instruments that transact in small, unremarkable amounts to build trust before converging on a single beneficiary to cash out together.

Traditional ring-detection systems suffer from two fatal design flaws:
1. **Post-Hoc Detection:** They catch fraud rings *after* the cash-out occurs, logging the event for future blocking while failing to prevent the immediate loss.
2. **Punitive Interventions:** When a ring is identified, systems typically execute blanket account freezes, penalizing legitimate users incidentally linked to shared resources (e.g., families on one device, office networks).

**Abuse Ring Sentinel** answers a targeted operational question:
> *Given a cluster of accounts that structurally resembles a fraud ring, is there a high probability of a coordinated cash-out within the next 6 hours—and what is the least disruptive intervention to stop it?*

Instead of claiming novelty in graph-based or temporal modeling, this system delivers a testable operational contribution: **a single predicted action (coordinated cash-out), a tight prediction window (6h), inspectable natural-language explanations, and a bounded intervention that halts transfers to the target beneficiary without freezing underlying accounts.**

---

## 🏗️ Architecture & Pipeline

The end-to-end detection, scoring, and intervention path processes historical logs up to the exact observation time ($\le \text{observation\_time}$) to eliminate future data leakage.

```text
[ Transactions & Account Logs ] (Causal Filter: t ≤ observation_time)
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. Entity-Link Graph Construction                           │
│    Shared Device / IP Subnet (/24) / Card BIN                │
│    └──> Precomputed Jaccard-style Distance Matrix           │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. DBSCAN Clustering (`metric='precomputed'`)               │
│    └──> Extracts Dense Account Clusters (Candidate Rings)   │
│    └──> Unlinked Users Categorized as Noise                 │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Temporal Feature Extraction                              │
│    • Accounts created within 24h   • Device reuse           │
│    • IP subnet overlap             • Amount similarity      │
│    • Beneficiary concentration (6h)• Activity burst (6h)   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Two-Stage Explainable Scorer                             │
│    • STRUCTURAL Score (Persistent): "Is this a ring?"       │
│    • ESCALATION Signal (6h Window): "Is cash-out imminent?" │
│                                                             │
│    [HIGH]   = Structural Ring + Fresh Escalation            │
│               └──> "Predicted cash-out within 6h"           │
│    [MEDIUM] = Structural Ring + No Escalation               │
│               └──> "Step-up verification required"          │
│    [LOW]    = Low Structural Confidence                     │
│               └──> "Passive monitoring"                     │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Bounded Defense-Only Intervention                        │
│    [HIGH]   ──> Hold ONLY transfers to target beneficiary   │
│    [MEDIUM] ──> Enforce step-up verification on next transfer│
│    [LOW]    ──> Maintain passive logging                    │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Append-Only Audit Trail                                  │
│    └──> JSONL log documenting scores, features & actions    │
└──────────────────────────────┴──────────────────────────────┘
