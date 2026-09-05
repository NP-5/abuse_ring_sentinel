# Ring Cash-Out Early Warning (Abuse Ring Sentinel)
**Track 2 — AI Risk Manager | Razorpay AI Buildathon 2026**

---

## Problem Statement

Per-transaction fraud scoring evaluates every transaction in isolation and asks *"is this one transaction suspicious?"* It structurally cannot see **coordinated fraud rings**—groups of accounts sharing a device, IP range, or payment instrument, transacting in similar small amounts to build history, then converging on a single beneficiary to cash out together. Each individual transaction in that pattern can look unremarkable; the ring is only visible in the relationships between accounts over time.

Worse, most systems that do catch a ring only catch it *after* the cash-out—post-hoc detection that can flag the ring for future blocking but cannot stop the specific loss that already happened. And the typical response once a ring is flagged is to execute a blanket freeze on every connected account, which punishes anyone incidentally connected to a flagged group (families sharing a device, an office network) for a crime they had no part in.

This system answers a narrower, more useful question:

> **Given a group of accounts that look structurally like a fraud ring, is there a real chance they are about to execute a coordinated cash-out in the next 6 hours—and if so, what is the least disruptive action that stops it?**

It is explicitly not a claim that graph-based fraud detection or temporal risk scoring are novel techniques—they are not. The contribution here is narrower and testable: **one specific predicted action (coordinated cash-out), one specific prediction window (6h), an explanation attached to every prediction, and an intervention bounded to hold only the transfers actually heading toward the suspected beneficiary—never a blanket account freeze.**

---

## How It Works

The end-to-end detection, scoring, and intervention path processes historical logs up to the exact observation time (timestamp <= observation_time) to eliminate future data leakage.

```text
transactions/accounts (causal, timestamp <= observation_time)
        │
        ▼
1. Entity-link graph over active accounts
   (shared device / IP-/24 / card BIN → precomputed Jaccard-style distance)
        │
        ▼
2. DBSCAN clustering (metric='precomputed')
   → candidate rings (dense, connected groups; noise = ordinary customers)
        │
        ▼
3. Temporal feature extraction per candidate ring
   accounts_created_within_24h · device_reuse · ip_overlap ·
   amount_similarity · beneficiary_concentration (recent) · activity_burst (recent)
        │
        ▼
4. Two-stage explainable scorer
   STRUCTURAL score  = "is this a ring at all" (persistent)
   ESCALATION signal = "is something happening right now" (recent-window only)
   HIGH   = structural ring AND fresh escalation  → "predicted cash-out within 6h"
   MEDIUM = structural ring, no fresh escalation → "step-up verification"
   LOW    = neither                              → monitor
        │
        ▼
5. Bounded intervention (never freezes an account)
   HIGH   → hold only the transfers heading to the concentrated beneficiary
   MEDIUM → require step-up verification on the group's next transfer
   LOW    → passive monitoring only
        │
        ▼
6. Full audit trail (every decision, every cycle, JSONL, append-only)
Everything upstream of step 6 only ever sees data with timestamp <= observation_time—there is no lookahead into the future anywhere in the detection path. Ground truth (the real cash_out_time for each ring) is used only by evaluate.py, after the fact, to score predictions. The detector never sees it.Engineering Retrospective: Bugs Found & Fixed During TestingThis section documents real failures caught by running the evaluation harness during testing, highlighting the architectural fixes required:v1.0 (Lagging Signal Bug): The first version used a single flat weighted score with beneficiary_concentration included at high weight. Result: next_action_prediction_precision was 0.0—every "predicted cash-out" call fired at or after the actual cash-out, never before, because beneficiary concentration is a lagging signal that only rises once transfers begin.Fix: Down-weighted beneficiary_concentration in the structural score and moved it to the escalation layer as a confirming signal rather than a primary trigger.v2.0 (Stale State Persistence Bug): The second version computed beneficiary_concentration over the full 72h lookback. Result: Precision remained near zero—once a ring cashed out, the signal stayed elevated for up to 3 days, causing repeated "future cash-out" predictions for an event that had already passed.Fix: Rescoped the feature to a rolling 6-hour window (matching checkpoint cadence) so the signal decays rapidly post-event.v3.0 (Synthetic Distribution Flaw): The third version generated test transactions uniformly at random across ring lifetimes. Result: The activity_burst signal fired constantly by chance, causing predictions to trigger far too early without genuine signal.Fix: Re-engineered synthetic generation so ring activity exponentially ramps up backward from cash_out_time, reflecting actual coordinated fraud behavior.Performance Metrics & Trade-off AnalysisEvaluated against a synthetic dataset containing injected fraud rings and deliberate false-positive control groups:MetricValueRing detection precision0.839Ring detection recall0.833Next-action (cash-out) prediction precision0.233Next-action (cash-out) prediction recall0.833Avg. detection lead time before cash-out4.1 hoursFalse positive rate0.161Legitimate customers affected15Trade-off EvaluationPrecision vs. Lead Time: The system catches 83.3% of real rings before they cash out, offering an average warning lead time of 4.1 hours. The lower next-action precision (0.233) means several predictions fire early during a ring's escalation phase. Because the HIGH-severity action holds specific beneficiary transfers rather than freezing customer accounts, erring toward an earlier, non-disruptive warning represents a defensible operational trade-off.Legitimate Impact: The 15 affected legitimate customers originate from 15 synthetic device/IP-sharing pairs (families, shared office networks) injected into the dataset to stress-test false positives. The non-blocking intervention policy (step-up verification rather than suspension) minimizes disruption for these users.Project LayoutPlaintextabuse_ring_sentinel/
├── README.md                 # System documentation
├── requirements.txt          # Python dependencies
├── run_evaluation.py         # Generate data, run full simulation, print metrics
├── visualize.py              # Render a flagged ring's entity-link graph (PNG)
├── src/
│   ├── data_gen.py           # Synthetic accounts/transactions/rings + ground truth
│   ├── graph_features.py     # Entity-link distance matrix
│   ├── ring_detector.py      # DBSCAN candidate-ring detection
│   ├── temporal_features.py  # Behavioural feature extraction
│   ├── predictor.py          # Two-stage explainable risk scorer
│   ├── intervention.py       # Bounded, defense-only action selection
│   ├── audit.py              # Append-only JSONL audit trail
│   ├── pipeline.py           # Orchestration (single cycle + full simulation)
│   ├── evaluate.py           # Ground-truth matching + evaluation metrics
│   └── api.py                # FastAPI service for dashboard replay
├── dashboard/
│   └── index.html            # Live view: current rings, risk, explanation, action
└── audit_log.jsonl           # Execution audit output
How to RunBash# 1. Install dependencies
pip install -r requirements.txt

# 2. Run full evaluation harness (generates data, simulates pipeline, outputs metrics)
python run_evaluation.py

# 3. Render a flagged ring's entity-link graph
python visualize.py

# 4. Launch live replay dashboard backend
cd src && uvicorn api:app --reload --port 8000
# Then open dashboard/index.html in a web browser
Demoing as "Real-Time"Real-time processing in this implementation uses an advancing simulation playhead against pre-generated transaction timelines:api.py runs the full simulation at startup and exposes a replay playhead (/rings/playhead) that advances automatically (~1.5s wall-clock per 6h checkpoint).dashboard/index.html polls the API every second, displaying updating clusters escalating from LOW -> MEDIUM -> HIGH and rendering active interventions.The /verification endpoint only reveals a ring's true cash_out_time after the replay clock has passed it, proving that the detector operates without lookahead bias.Example Audit RecordEvery scoring cycle appends structured records to audit_log.jsonl:JSON{
  "observation_time_hr": 72,
  "cluster_members": ["ACC-fb6b7bf4", "ACC-d62d38e1", "ACC-9c41f0a8", "ACC-e52b11d4"],
  "cluster_size": 4,
  "risk_score": 0.6961,
  "severity": "HIGH",
  "explanation": "Predicted because 4 accounts were created within 24 hours, 4 accounts share the same device, transaction amounts are unusually similar across the group, the group has shown a burst of activity in the last few hours.",
  "intervention": {
    "action": "HOLD_BENEFICIARY_TRANSFERS",
    "held_transaction_ids": [],
    "accounts_frozen": [],
    "note": "Only transfers toward the concentrated beneficiary are held for review. Accounts remain active for unrelated activity."
  }
}
Out of Scope for PrototypeSingle Target Action: Focuses strictly on predicting coordinated cash-outs. Other topologies (refund abuse, device rotation) require distinct feature sets and escalation models.Rule-Based Scorer: Uses an explainable rule-based scorer rather than a black-box model to ensure direct feature inspectability and audit trail traceability.Synthetic Benchmarking: Operates on synthetic transaction data due to production privacy boundaries. The evaluation framework (evaluate.py) remains decoupled for drop-in use against real transaction schemas.
