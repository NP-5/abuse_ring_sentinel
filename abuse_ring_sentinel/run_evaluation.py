import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from data_gen import generate, HORIZON_HOURS
from pipeline import run_simulation
from evaluate import evaluate
from audit import reset_log, AUDIT_LOG_PATH

def main():
    print("Generating synthetic accounts/transactions/rings...")
    accounts_df, transactions_df, gt_df = generate()
    print(f"  accounts={len(accounts_df)}  transactions={len(transactions_df)}  rings={len(gt_df)}")

    reset_log()
    print("\nRunning detection pipeline across the simulated timeline "
          "(checkpoint every 6h, causal -- no lookahead)...")
    all_cycles = run_simulation(accounts_df, transactions_df, HORIZON_HOURS, checkpoint_every=6)

    print("\nScoring against hidden ground truth...")
    metrics = evaluate(all_cycles, gt_df, accounts_df)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    for k, v in metrics.items():
        print(f"{k:40s}: {v}")
    print("=" * 60)
    print(f"\nFull audit trail written to: {os.path.abspath(AUDIT_LOG_PATH)}")

    with open("metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    print("Metrics saved to metrics.json")

if __name__ == "__main__":
    main()
