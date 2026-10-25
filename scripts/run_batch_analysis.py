"""
Batch Analyzer Runner.
Loads sample blocks or fetches live blocks, executes statistical ordering analysis,
and saves consolidated analytical findings to data/analysis_results.json.
"""

import json
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import asdict
from analyzer.block_parser import ParsedBlock, ParsedTransaction
from analyzer.scheduler_analyzer import analyze_block_ordering


def main():
    sample_file = os.path.join("data", "sample_blocks.json")
    if not os.path.exists(sample_file):
        print(f"File not found: {sample_file}")
        return

    with open(sample_file, "r", encoding="utf-8") as f:
        blocks_data = json.load(f)

    results = []
    print("\n" + "=" * 90)
    print(f"{'Slot':<10} | {'Client':<12} | {'Txs':<5} | {'Spearman rho':<12} | {'Cluster rho':<11} | {'Inv Ratio':<10} | {'Top-10% Head':<12} | {'Verdict'}")
    print("=" * 90)

    for b_json in blocks_data:
        txs = []
        for t in b_json.get("transactions", []):
            txs.append(ParsedTransaction(
                signature=t.get("signature", ""),
                position_index=t.get("position_index", 0),
                base_fee=5000,
                priority_fee=t.get("priority_fee", 0),
                total_fee=5000 + t.get("priority_fee", 0),
                compute_units_consumed=t.get("cu_limit", 200_000) * 8 // 10,
                compute_unit_limit=t.get("cu_limit", 200_000),
                compute_unit_price=t.get("cu_price", 0),
                effective_priority_rate=float(t.get("cu_price", 0)),
                writable_accounts=t.get("writable_accounts", []),
                readonly_accounts=t.get("readonly_accounts", []),
                is_vote=t.get("is_vote", False),
                is_successful=True
            ))

        p_block = ParsedBlock(
            slot=b_json.get("slot", 0),
            blockhash=b_json.get("blockhash", ""),
            parent_slot=b_json.get("parent_slot", 0),
            block_time=b_json.get("block_time"),
            leader_pubkey=b_json.get("leader_pubkey", ""),
            total_transactions=len(txs),
            non_vote_transactions=sum(1 for tx in txs if not tx.is_vote),
            transactions=txs
        )

        analysis = analyze_block_ordering(
            block=p_block,
            client_family=b_json.get("client_family", "Unknown"),
            client_version=b_json.get("client_version", "Unknown")
        )

        res_dict = asdict(analysis)
        results.append(res_dict)

        print(
            f"{analysis.slot:<10} | "
            f"{analysis.client_family:<12} | "
            f"{analysis.non_vote_txs:<5} | "
            f"{analysis.global_spearman_rho:>11.4f} | "
            f"{analysis.mean_conflict_spearman_rho:>10.4f} | "
            f"{analysis.global_inversion_ratio:>10.4f} | "
            f"{analysis.top_decile_head_concentration:>10.1f}% | "
            f"{analysis.scheduler_verdict}"
        )

    print("=" * 90 + "\n")

    out_file = os.path.join("data", "analysis_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"Saved complete comparative analysis to {out_file}")


if __name__ == "__main__":
    main()
