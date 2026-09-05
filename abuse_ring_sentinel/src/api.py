"""
FastAPI wrapper around the detection pipeline.

On startup: generates one synthetic dataset and runs the full simulation
once, standing in for a recent window of production data. In a live
deployment this would run incrementally against a streaming transaction
feed instead of a precomputed batch.

Exposes a replay playhead that advances on its own, so the dashboard can
poll it the same way it would poll a live system. /verification only
reveals a ring's true cash-out time once the playhead has already passed
it, so the dashboard is never shown the future -- the same constraint the
detector itself operates under.

Endpoints:
  GET  /rings/current    -> clusters flagged at the latest checkpoint
  GET  /rings/playhead    -> clusters at the current live-ticking position
  GET  /rings/timeline     -> every checkpoint's results
  GET  /verification        -> predicted-vs-actual, revealed as events resolve
  GET  /audit                -> full audit trail
  GET  /metrics                -> evaluation vs hidden ground truth
  POST /replay/speed            -> change playback speed (seconds per checkpoint)
"""
import os
import sys
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(__file__))

from data_gen import generate, HORIZON_HOURS
from pipeline import run_simulation
from evaluate import evaluate, match_cluster_to_ring, PREDICTION_WINDOW_HOURS
from audit import reset_log, read_log

app = FastAPI(title="Ring Cash-Out Early Warning API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STATE = {
    "cycles": [], "metrics": {}, "ground_truth": None,
    "playhead_index": 0, "seconds_per_checkpoint": 1.5,
    "resolution": {},  # ring_id -> {cash_out_time, first_high_time, members}
}


def _build_resolution_table(cycles, gt_df):
    """Precompute, for every ring, the earliest HIGH call that correctly
    matched it -- used only to reveal prediction-vs-actual progressively as
    the replay clock passes each ring's real cash-out time. Never fed back
    into detection."""
    table = {}
    for _, row in gt_df.iterrows():
        ring_id = row["ring_id"]
        first_high = None
        for t, results in cycles:
            for r in results:
                if r["verdict"]["severity"] != "HIGH":
                    continue
                if match_cluster_to_ring(r["members"], gt_df) != ring_id:
                    continue
                if first_high is None or t < first_high:
                    first_high = t
        table[ring_id] = {
            "cash_out_time": round(float(row["cash_out_time"]), 2),
            "first_high_time": first_high,
            "members": row["members"],
        }
    return table


@app.on_event("startup")
async def startup():
    accounts_df, transactions_df, gt_df = generate()
    reset_log()
    cycles = run_simulation(accounts_df, transactions_df, HORIZON_HOURS, checkpoint_every=6)
    STATE["cycles"] = cycles
    STATE["ground_truth"] = gt_df
    STATE["metrics"] = evaluate(cycles, gt_df, accounts_df)
    STATE["resolution"] = _build_resolution_table(cycles, gt_df)
    asyncio.create_task(_tick_playhead())


async def _tick_playhead():
    """Advances the replay clock on its own, looping once it reaches the end
    of the simulated timeline -- this is what makes the dashboard feel live
    without needing a real payment stream behind it."""
    while True:
        await asyncio.sleep(STATE["seconds_per_checkpoint"])
        if STATE["cycles"]:
            STATE["playhead_index"] = (STATE["playhead_index"] + 1) % len(STATE["cycles"])


def _serialize_cycle(t, results):
    return {
        "observation_time": t,
        "clusters": [
            {
                "members": r["members"],
                "cluster_size": r["features"]["cluster_size"],
                "risk_score": r["verdict"]["risk_score"],
                "severity": r["verdict"]["severity"],
                "explanation": r["verdict"]["explanation"],
                "intervention": r["intervention"],
            }
            for r in results
        ],
    }


@app.get("/rings/current")
def rings_current():
    if not STATE["cycles"]:
        return {"observation_time": None, "clusters": []}
    t, results = STATE["cycles"][-1]
    return _serialize_cycle(t, results)


@app.get("/rings/playhead")
def rings_playhead():
    if not STATE["cycles"]:
        return {"observation_time": None, "clusters": [], "playhead_index": 0, "total": 0}
    idx = STATE["playhead_index"]
    t, results = STATE["cycles"][idx]
    out = _serialize_cycle(t, results)
    out["playhead_index"] = idx
    out["total"] = len(STATE["cycles"])
    return out


@app.get("/rings/timeline")
def rings_timeline():
    return [_serialize_cycle(t, r) for t, r in STATE["cycles"]]


@app.get("/verification")
def verification():
    """Reveals prediction-vs-actual only for rings whose real cash-out time
    the replay clock has already passed -- the dashboard's proof panel."""
    if not STATE["cycles"]:
        return []
    idx = STATE["playhead_index"]
    now, _ = STATE["cycles"][idx]
    out = []
    for ring_id, info in STATE["resolution"].items():
        if info["cash_out_time"] > now:
            continue  # hasn't happened yet in the replay -- don't reveal it
        first_high = info["first_high_time"]
        if first_high is not None and 0 <= (info["cash_out_time"] - first_high) <= PREDICTION_WINDOW_HOURS:
            lead_time = round(info["cash_out_time"] - first_high, 2)
            status = "predicted"
        elif first_high is not None:
            lead_time = round(info["cash_out_time"] - first_high, 2)
            status = "flagged_outside_window"
        else:
            lead_time = None
            status = "missed"
        out.append({
            "ring_id": ring_id,
            "cluster_size": len(info["members"]),
            "cash_out_time": info["cash_out_time"],
            "first_predicted_time": first_high,
            "lead_time_hours": lead_time,
            "status": status,
        })
    return sorted(out, key=lambda r: r["cash_out_time"])


@app.get("/audit")
def audit():
    return read_log()


@app.get("/metrics")
def metrics():
    return STATE["metrics"]


@app.post("/replay/speed")
def set_speed(seconds_per_checkpoint: float):
    STATE["seconds_per_checkpoint"] = max(0.2, seconds_per_checkpoint)
    return {"seconds_per_checkpoint": STATE["seconds_per_checkpoint"]}


static_dir = os.path.join(os.path.dirname(__file__), "..", "dashboard")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="dashboard")
