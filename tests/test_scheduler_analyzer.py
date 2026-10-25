"""
Unit tests for SchedulerAnalyzer.
Validates statistical metric calculations (Spearman rho, Kendall tau, Inversions)
and empirical verdict classification across Agave, Jito, and Firedancer.
"""

import pytest
from analyzer.block_parser import ParsedBlock, ParsedTransaction
from analyzer.scheduler_analyzer import (
    compute_inversions,
    analyze_block_ordering,
    formulate_verdict,
    BlockOrderingAnalysis
)


def test_compute_inversions_monotonic():
    # Strictly descending ranks (e.g. highest priority first: [100, 50, 10, 0])
    # Inversions = 0 (perfect priority order)
    inv, total, ratio = compute_inversions([100.0, 50.0, 10.0, 0.0])
    assert inv == 0
    assert total == 6
    assert ratio == 0.0

    # Strictly ascending ranks (e.g. lowest priority first: [0, 10, 50, 100])
    # Inversions = total (worst order)
    inv2, total2, ratio2 = compute_inversions([0.0, 10.0, 50.0, 100.0])
    assert inv2 == 6
    assert ratio2 == 1.0


def test_analyze_block_ordering_firedancer_pattern():
    # Construct synthetic transactions mimicking Firedancer greedy knapsack:
    # High fee transactions placed strictly near the head
    txs = []
    fees = [500_000, 450_000, 300_000, 200_000, 100_000, 50_000, 10_000, 0, 0, 0]
    for idx, f in enumerate(fees):
        txs.append(ParsedTransaction(
            signature=f"sig_{idx}",
            position_index=idx,
            base_fee=5000,
            priority_fee=f,
            total_fee=5000 + f,
            compute_units_consumed=20_000,
            compute_unit_limit=200_000,
            compute_unit_price=f,
            effective_priority_rate=float(f),
            writable_accounts=["SharedHotPool11111111111111111111111111111"],
            is_vote=False,
            is_successful=True
        ))

    block = ParsedBlock(
        slot=300120620,
        blockhash="hash_firedancer",
        parent_slot=300120619,
        block_time=1729001000,
        leader_pubkey="JumpCrypto111111111111111111111111111111111",
        total_transactions=len(txs),
        non_vote_transactions=len(txs),
        transactions=txs
    )

    analysis = analyze_block_ordering(block, client_family="Firedancer", client_version="0.114")
    assert analysis.global_spearman_rho > 0.8
    assert analysis.global_inversion_ratio < 0.1
    assert analysis.top_decile_head_concentration == 100.0
    assert "STRICT_PRIORITY_KNAPSACK" in analysis.scheduler_verdict


def test_analyze_block_ordering_agave_multi_threaded_pattern():
    # Agave pattern: parallel non-conflicting batches interleave, so global correlation is lower,
    # but within a conflict cluster (e.g. AccountA), priority ordering is respected.
    txs = []
    # Interleaved 2 threads:
    # Thread 1 accesses AccA (fee 100k, 50k, 10k)
    # Thread 2 accesses AccB (fee 80k, 40k, 5k)
    # Interleaved positions:
    # pos 0: AccA (100k)
    # pos 1: AccB (80k)
    # pos 2: AccA (50k)
    # pos 3: AccB (40k)
    # pos 4: AccA (10k)
    # pos 5: AccB (5k)
    pattern = [
        ("AccA", 100_000),
        ("AccB", 80_000),
        ("AccA", 50_000),
        ("AccB", 40_000),
        ("AccA", 10_000),
        ("AccB", 5_000),
        ("AccA", 1_000),
        ("AccB", 1_000),
    ]

    for idx, (acc, fee) in enumerate(pattern):
        txs.append(ParsedTransaction(
            signature=f"sig_{idx}",
            position_index=idx,
            base_fee=5000,
            priority_fee=fee,
            total_fee=5000 + fee,
            compute_units_consumed=20_000,
            compute_unit_limit=200_000,
            compute_unit_price=fee,
            effective_priority_rate=float(fee),
            writable_accounts=[acc],
            is_vote=False,
            is_successful=True
        ))

    block = ParsedBlock(
        slot=300120401,
        blockhash="hash_agave",
        parent_slot=300120400,
        block_time=1729002000,
        leader_pubkey="AgaveValidator11111111111111111111111111111",
        total_transactions=len(txs),
        non_vote_transactions=len(txs),
        transactions=txs
    )

    analysis = analyze_block_ordering(block, client_family="Agave", client_version="2.0.15")
    assert analysis.contended_accounts_count >= 2
    assert analysis.mean_conflict_spearman_rho > 0.8
    assert analysis.scheduler_verdict in ["PARALLEL_PRIO_GRAPH_WORKERS", "STRICT_PRIORITY_KNAPSACK", "HYBRID_PARTIAL_ORDERING"]


def test_formulate_verdict_low_fee():
    verdict, conf, desc = formulate_verdict(
        client_family="Agave",
        global_rho=0.05,
        mean_conflict_rho=0.08,
        inversion_ratio=0.48,
        top_decile_conc=10.0,
        pct_with_fee=5.0,
        contended_count=1
    )
    assert verdict == "LOW_FEE_ACTIVITY"
    assert conf == 0.65
