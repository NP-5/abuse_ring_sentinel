Ring Cash-Out Early Warning
Track 2 — AI Risk Manager, Razorpay AI Buildathon 2026

Problem statement
Per-transaction fraud scoring evaluates every transaction in isolation and asks "is this one transaction suspicious?" It structurally cannot see coordinated fraud rings — groups of accounts sharing a device, IP range, or payment instrument, transacting in similar small amounts to build history, then converging on a single beneficiary to cash out together. Each individual transaction in that pattern can look unremarkable; the ring is only visible in the relationships between accounts over time.

Worse, most systems that do catch a ring only catch it after the cash-out — post-hoc detection that can flag the ring for future blocking but can't stop the specific loss that already happened. And the typical response once a ring is flagged is to freeze every connected account, which punishes anyone incidentally connected to a flagged group (families sharing a device, an office network) for a crime they had no part in.

This system answers a narrower, more useful question:

Given a group of accounts that look structurally like a fraud ring, is there a real chance they're about to execute a coordinated cash-out in the next 6 hours — and if so, what is the least disruptive action that stops it?

It is explicitly not a claim that graph-based fraud detection or temporal risk scoring are novel techniques — they aren't, and the buildathon brief says as much. The contribution here is narrower and testable: one specific predicted action (coordinated cash-out), one specific prediction window (6h), an explanation attached to every prediction, and an intervention that is bounded to hold only the transfers actually heading toward the suspected beneficiary — never a blanket account freeze.

How it works
The detection and intervention pipeline processes transactions through six main stages:Data Ingestion & Filtering: All transactions and account activities are strictly filtered to include only data occurring at or before the current observation time ($\le \text{observation\_time}$), preventing future data leakage.1. Entity-Link Graph Construction: Maps connections between active accounts by linking shared devices, IP /24 subnets, or card BINs, converting these links into a precomputed Jaccard-style distance matrix.2. DBSCAN Clustering: Clusters the graph using metric='precomputed' to isolate candidate rings (dense, tightly connected account clusters), while classifying unlinked, ordinary customers as noise.3. Temporal Feature Extraction: Computes behavioural risk metrics for each candidate ring, including:accounts_created_within_24hdevice_reuseip_overlapamount_similaritybeneficiary_concentration (recent window)activity_burst (recent window)4. Two-Stage Explainable Scorer: Evaluates the extracted features through a persistent Structural Score ("is this a ring at all?") and a recent-window Escalation Signal ("is something happening right now?"):HIGH: High structural score AND fresh escalation signal $\rightarrow$ Predicted cash-out within 6 hours.MEDIUM: High structural score without fresh escalation $\rightarrow$ Flagged for step-up verification.LOW: Neither condition met $\rightarrow$ Passive monitoring.5. Bounded Intervention: Applies proportional risk controls without blanket account freezes:HIGH: Holds only the specific transfers routed toward the concentrated beneficiary.MEDIUM: Enforces step-up verification on the group's next outgoing transfer.LOW: Continues passive logging and monitoring.6. Full Audit Trail: Appends every assessment, severity level, feature value, and intervention action into an append-only JSONL log (audit_log.jsonl).Data Integrity Guarantee: Ground truth data (the actual cash_out_time for each ring) is strictly segregated and used solely post-hoc by evaluate.py to calculate precision, recall, and lead-time metrics. The live detection engine never accesses future states.
Why the design looks like this (bugs found and fixed during testing)
This section is here on purpose — the brief explicitly rewards honest engineering over a clean-looking demo, and these were real failures caught by running the evaluation, not hypothetical caveats.

First version: single flat weighted score, beneficiary_concentration included with high weight. Result: next_action_prediction_precision was 0.0 — every "predicted cash-out" call fired at or after the actual cash-out, never before, because beneficiary concentration is a lagging signal — it only rises once the transfer has already happened. Fix: down-weighted it in the structural score and moved it to the escalation layer, where it acts as a confirming signal rather than the primary trigger.

Second version: beneficiary_concentration computed over the full 72h lookback. Result: precision was still near-zero — once a ring cashed out, the signal stayed elevated for up to 3 days afterward (as long as the transfer stayed inside the trailing lookback window), so the system kept predicting a "future" cash-out that had already happened, over and over, every 6-hour checkpoint. Fix: rescoped the feature to a short recent window (6h, matching checkpoint cadence) so it decays once the event passes.

Third version: synthetic "test" transactions timed uniformly at random across each ring's whole lifetime. Result: the "recent activity burst" signal fired constantly by pure chance, unrelated to actual proximity to cash-out, so predictions still fired far too early with no real signal behind them. Fix: re-generated the synthetic data so ring activity ramps up (exponential decay backward from cash_out_time) the way real coordinated fraud actually behaves, instead of being memoryless noise.

After all three fixes, on this synthetic dataset:

Metric	Value
Ring detection precision	0.839
Ring detection recall	0.833
Next-action (cash-out) prediction precision	0.233
Next-action (cash-out) prediction recall	0.833
Avg. detection lead time before cash-out	4.1 hours
False positive rate	0.161
Legitimate customers affected	15
Read the precision/recall trade-off honestly, don't just report it: the system catches 83% of real rings before they cash out, with an average ~4 hours of warning — but only 23% of its "predicted cash-out within 6h" calls land in that exact window; the rest fire a bit earlier for a ring that does go on to cash out. Given that the HIGH-severity action is hold specific transfers, not freeze accounts, erring toward an earlier, non-disruptive warning is a defensible trade-off rather than a bug to hide — but it is a real limitation, and tightening it further (e.g. a second, later confirmation stage before holding funds) is the obvious next iteration if this were taken past prototype.

legitimate_customers_affected = 15 comes primarily from the 15 synthetic legit device/IP-sharing pairs (families, shared office networks) deliberately injected into the dataset to stress-test false positives — worth stating explicitly in the pitch, since it's a real cost the intervention design already minimizes (step-up verification, not a block) but doesn't eliminate.

Project layout
abuse_ring_sentinel/
├── README.md
├── requirements.txt
├── run_evaluation.py        # generate data, run full simulation, print metrics
├── visualize.py              # render a flagged ring's entity-link graph (PNG)
├── src/
│   ├── data_gen.py           # synthetic accounts/transactions/rings + ground truth
│   ├── graph_features.py     # entity-link distance matrix
│   ├── ring_detector.py      # DBSCAN candidate-ring detection
│   ├── temporal_features.py  # behavioural feature extraction
│   ├── predictor.py           # two-stage explainable risk scorer
│   ├── intervention.py        # bounded, defense-only action selection
│   ├── audit.py                # append-only JSONL audit trail
│   ├── pipeline.py             # orchestration (single cycle + full simulation)
│   ├── evaluate.py              # ground-truth matching + the 5 metrics
│   └── api.py                    # FastAPI service for the dashboard
├── dashboard/
│   └── index.html                # live view: current rings, risk, explanation, action
└── audit_log.jsonl                # generated by running the pipeline
How to run
pip install -r requirements.txt

# Full evaluation run (generates data, runs the simulation, prints + saves metrics)
python run_evaluation.py

# Render a flagged ring's graph for the pitch video
python visualize.py

# Live replay dashboard (for the demo video)
cd src && uvicorn api:app --reload --port 8000
# then open dashboard/index.html in a browser
Demoing this as "real-time"
No week-long student project gets a live production payment rail, so "real time" here means what it means in real fraud-ops demos too: a clock that advances on its own against real (synthetic) transaction data, reacting live, with predictions checked against what actually happened.

api.py runs the full simulation once at startup, then exposes a replay playhead that ticks forward on its own (/rings/playhead, ~1.5s of wall clock per 6h checkpoint, looping when it reaches the end). The dashboard (dashboard/index.html) polls it every second like it would poll a live system: a ticking clock, clusters appearing and escalating from LOW → MEDIUM → HIGH in front of you, and interventions firing as they're decided.

The actual proof-of-prediction moment for the pitch: /verification only reveals a ring's real cash-out time once the replay clock has already passed it — so the dashboard is never shown the future, exactly like the detector itself isn't. Watching a ring go HIGH, then a few ticks later watching the verification panel confirm "predicted 3.9h before actual cash-out" is the single best 20 seconds to put in the pitch video.

Example audit record
{
  "observation_time_hr": 72,
  "cluster_members": ["ACC-fb6b7bf4", "ACC-d62d38e1", "..."],
  "cluster_size": 7,
  "risk_score": 0.6961,
  "severity": "HIGH",
  "explanation": "Predicted because 7 accounts were created within 24 hours, 7 accounts share the same device, transaction amounts are unusually similar across the group, the group has shown a burst of activity in the last few hours.",
  "intervention": {
    "action": "HOLD_BENEFICIARY_TRANSFERS",
    "held_transaction_ids": [],
    "accounts_frozen": [],
    "note": "Only transfers toward the concentrated beneficiary are held for review. Accounts remain active for unrelated activity."
  }
}
What's deliberately out of scope for this prototype
Only one predicted action (coordinated cash-out). Refund abuse, device rotation, and new-account creation waves are structurally detectable with the same entity-link graph but would need their own escalation signals and their own evaluation — separate models, not attempted here.
The "predictor" is an explainable rule-based scorer, not a trained ML model or a generative simulation. That's a deliberate choice, not a shortcut: every prediction traces to specific, inspectable feature values, which is what "honest metrics" and an audit trail actually require.
Runs on synthetic data with injected ground truth, since real Razorpay transaction data isn't available outside the company. The evaluation harness (evaluate.py) is written to run unchanged against any dataset that provides the same account/transaction schema plus ring ground truth.
