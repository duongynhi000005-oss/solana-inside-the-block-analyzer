"""
Scheduler Analyzer & Transaction Ordering Engine.
Calculates statistical metrics (Spearman rho, Kendall tau, Inversion Ratios,
Conflict-Cluster Partitions) to uncover the underlying transaction ordering rules
of Solana validator clients (Agave, Jito, Firedancer).
"""

from typing import Dict, Any, List, Set, Tuple, Optional
from dataclasses import dataclass, field
import math
import logging
from collections import defaultdict
import numpy as np
from scipy import stats

from .block_parser import ParsedBlock, ParsedTransaction

logger = logging.getLogger("solana_analyzer.scheduler_analyzer")


@dataclass
class ConflictClusterMetrics:
    """Metrics calculated within a single account write-lock contention cluster."""
    account_pubkey: str
    transaction_count: int
    spearman_rho: float
    kendall_tau: float
    inversion_ratio: float
    p_value: float


@dataclass
class BlockOrderingAnalysis:
    """Complete ordering analysis for a parsed block."""
    slot: int
    leader_pubkey: str
    client_family: str
    client_version: str
    total_txs: int
    non_vote_txs: int
    txs_with_priority_fee: int
    pct_with_priority_fee: float

    # Global metrics (all non-vote transactions)
    global_spearman_rho: float
    global_spearman_pvalue: float
    global_kendall_tau: float
    global_inversion_ratio: float
    top_decile_head_concentration: float  # % of top 10% fee txs in first 25% of block

    # Conflict-partitioned metrics (within accounts having write contention >= 3 txs)
    contended_accounts_count: int
    mean_conflict_spearman_rho: float
    mean_conflict_inversion_ratio: float
    top_conflict_clusters: List[ConflictClusterMetrics] = field(default_factory=list)

    # Diagnostic verdict
    scheduler_verdict: str = "INCONCLUSIVE"
    verdict_confidence: float = 0.0
    rationale: str = ""


def compute_inversions(ranks: List[float]) -> Tuple[int, int, float]:
    """
    Computes pairwise inversions where an item with lower priority lands before an item with higher priority.
    Higher rank value means higher priority.
    If i < j and rank[i] < rank[j], this is an inversion (rule violation).
    Returns: (inversions, total_pairs, inversion_ratio)
    """
    n = len(ranks)
    if n <= 1:
        return 0, 0, 0.0

    total_pairs = n * (n - 1) // 2
    inversions = 0

    for i in range(n):
        for j in range(i + 1, n):
            if ranks[i] < ranks[j]:
                inversions += 1

    ratio = inversions / total_pairs if total_pairs > 0 else 0.0
    return inversions, total_pairs, ratio


def analyze_block_ordering(
    block: ParsedBlock,
    client_family: str = "Unknown",
    client_version: str = "Unknown"
) -> BlockOrderingAnalysis:
    """
    Performs comprehensive statistical analysis of transaction positions vs priority fee rates.
    Disentangles parallel execution noise from true scheduler priority rules by separating
    global order from account-lock conflict clusters.
    """
    non_vote_txs = [tx for tx in block.transactions if not tx.is_vote]
    n = len(non_vote_txs)

    if n < 5:
        return BlockOrderingAnalysis(
            slot=block.slot,
            leader_pubkey=block.leader_pubkey,
            client_family=client_family,
            client_version=client_version,
            total_txs=block.total_transactions,
            non_vote_txs=n,
            txs_with_priority_fee=0,
            pct_with_priority_fee=0.0,
            global_spearman_rho=0.0,
            global_spearman_pvalue=1.0,
            global_kendall_tau=0.0,
            global_inversion_ratio=0.5,
            top_decile_head_concentration=0.0,
            contended_accounts_count=0,
            mean_conflict_spearman_rho=0.0,
            mean_conflict_inversion_ratio=0.5,
            scheduler_verdict="INSUFFICIENT_DATA",
            verdict_confidence=0.0,
            rationale="Too few non-vote transactions in slot to measure scheduler ordering."
        )

    # 1. Global priority fee metrics
    positions = np.array([tx.position_index for tx in non_vote_txs], dtype=float)
    cu_prices = np.array([tx.compute_unit_price for tx in non_vote_txs], dtype=float)
    priority_fees = np.array([tx.priority_fee for tx in non_vote_txs], dtype=float)

    txs_with_fee = int(np.sum(cu_prices > 0))
    pct_with_fee = (txs_with_fee / n) * 100.0

    # Spearman rank correlation between position and cu_price
    # If scheduler places highest CU price first, position (0..N) is negatively correlated with cu_price.
    if np.all(cu_prices == cu_prices[0]):
        global_rho, global_p = 0.0, 1.0
        global_tau = 0.0
        global_inv_ratio = 0.0
    else:
        # We compute correlation with -position so that positive correlation means higher fee -> earlier position
        res_spearman = stats.spearmanr(-positions, cu_prices)
        global_rho = float(res_spearman.statistic) if not math.isnan(res_spearman.statistic) else 0.0
        global_p = float(res_spearman.pvalue) if not math.isnan(res_spearman.pvalue) else 1.0

        res_kendall = stats.kendalltau(-positions, cu_prices)
        global_tau = float(res_kendall.statistic) if not math.isnan(res_kendall.statistic) else 0.0

        # Sample inversion ratio (limit sample to 300 for efficiency if block is huge)
        sample_cu = cu_prices[:300].tolist()
        _, _, global_inv_ratio = compute_inversions(sample_cu)

    # 2. Top-decile concentration at head
    top_10_pct_count = max(1, int(n * 0.10))
    head_25_pct_cutoff = int(n * 0.25)
    sorted_indices_by_fee = np.argsort(-cu_prices)
    top_fee_indices = sorted_indices_by_fee[:top_10_pct_count]
    in_head_count = sum(1 for idx in top_fee_indices if non_vote_txs[idx].position_index < head_25_pct_cutoff)
    top_decile_concentration = (in_head_count / top_10_pct_count) * 100.0

    # 3. Account write-lock conflict cluster partitioning
    account_write_map: Dict[str, List[ParsedTransaction]] = defaultdict(list)
    for tx in non_vote_txs:
        for acc in tx.writable_accounts:
            account_write_map[acc].append(tx)

    conflict_clusters: List[ConflictClusterMetrics] = []
    conflict_rhos: List[float] = []
    conflict_invs: List[float] = []

    for acc, tx_list in account_write_map.items():
        if len(tx_list) >= 4:
            # Sort by position in block
            tx_list_sorted = sorted(tx_list, key=lambda x: x.position_index)
            c_pos = np.array([t.position_index for t in tx_list_sorted], dtype=float)
            c_fee = np.array([t.compute_unit_price for t in tx_list_sorted], dtype=float)

            if not np.all(c_fee == c_fee[0]):
                c_sp = stats.spearmanr(-c_pos, c_fee)
                c_rho = float(c_sp.statistic) if not math.isnan(c_sp.statistic) else 0.0
                c_pval = float(c_sp.pvalue) if not math.isnan(c_sp.pvalue) else 1.0

                c_kd = stats.kendalltau(-c_pos, c_fee)
                c_tau = float(c_kd.statistic) if not math.isnan(c_kd.statistic) else 0.0

                _, _, c_inv = compute_inversions(c_fee.tolist())

                conflict_rhos.append(c_rho)
                conflict_invs.append(c_inv)

                conflict_clusters.append(ConflictClusterMetrics(
                    account_pubkey=acc,
                    transaction_count=len(tx_list),
                    spearman_rho=c_rho,
                    kendall_tau=c_tau,
                    inversion_ratio=c_inv,
                    p_value=c_pval
                ))

    # Sort conflict clusters by transaction count descending
    conflict_clusters.sort(key=lambda x: -x.transaction_count)
    top_clusters = conflict_clusters[:5]

    mean_c_rho = float(np.mean(conflict_rhos)) if conflict_rhos else global_rho
    mean_c_inv = float(np.mean(conflict_invs)) if conflict_invs else global_inv_ratio

    # 4. Formulate empirical rule verdict
    verdict, confidence, rationale = formulate_verdict(
        client_family=client_family,
        global_rho=global_rho,
        mean_conflict_rho=mean_c_rho,
        inversion_ratio=global_inv_ratio,
        top_decile_conc=top_decile_concentration,
        pct_with_fee=pct_with_fee,
        contended_count=len(conflict_clusters)
    )

    return BlockOrderingAnalysis(
        slot=block.slot,
        leader_pubkey=block.leader_pubkey,
        client_family=client_family,
        client_version=client_version,
        total_txs=block.total_transactions,
        non_vote_txs=n,
        txs_with_priority_fee=txs_with_fee,
        pct_with_priority_fee=round(pct_with_fee, 2),
        global_spearman_rho=round(global_rho, 4),
        global_spearman_pvalue=round(global_p, 6),
        global_kendall_tau=round(global_tau, 4),
        global_inversion_ratio=round(global_inv_ratio, 4),
        top_decile_head_concentration=round(top_decile_concentration, 2),
        contended_accounts_count=len(conflict_clusters),
        mean_conflict_spearman_rho=round(mean_c_rho, 4),
        mean_conflict_inversion_ratio=round(mean_c_inv, 4),
        top_conflict_clusters=top_clusters,
        scheduler_verdict=verdict,
        verdict_confidence=round(confidence, 2),
        rationale=rationale
    )


def formulate_verdict(
    client_family: str,
    global_rho: float,
    mean_conflict_rho: float,
    inversion_ratio: float,
    top_decile_conc: float,
    pct_with_fee: float,
    contended_count: int
) -> Tuple[str, float, str]:
    """
    Classifies scheduler behavior based on multi-dimensional empirical signals.
    """
    if pct_with_fee < 15.0:
        return (
            "LOW_FEE_ACTIVITY",
            0.65,
            f"Only {pct_with_fee:.1f}% of transactions specify priority fees. Scheduler is mostly operating in FIFO mode."
        )

    # Signal 1: Firedancer strict knapsack
    if global_rho > 0.45 and mean_conflict_rho > 0.55 and inversion_ratio < 0.28:
        return (
            "STRICT_PRIORITY_KNAPSACK",
            0.92,
            f"High global rank correlation (rho={global_rho:.2f}) and strong conflict-cluster ordering (rho={mean_conflict_rho:.2f}) with low inversion ratio ({inversion_ratio:.2f}). Typical of Firedancer fd_pack binning knapsack."
        )

    # Signal 2: Jito bundle-first & priority packing
    if top_decile_conc >= 55.0 and (global_rho > 0.25 or mean_conflict_rho > 0.35):
        return (
            "BUNDLE_AUCTION_PRIORITY_HEAD",
            0.88,
            f"Top-decile priority concentration is high ({top_decile_conc:.1f}% in head 25% of block) with moderate cluster correlation (rho={mean_conflict_rho:.2f}). Typical of Jito-Solana bundle insertion + priority scheduler."
        )

    # Signal 3: Agave Multi-Threaded Prio-Graph
    if mean_conflict_rho > 0.20 and global_rho < mean_conflict_rho:
        return (
            "PARALLEL_PRIO_GRAPH_WORKERS",
            0.85,
            f"Conflict-cluster ordering (rho={mean_conflict_rho:.2f}) significantly outperforms global ordering (rho={global_rho:.2f}). Reflects Agave multi-threaded banking stage interleaving parallel non-conflicting batches."
        )

    # Signal 4: Arrival Time / Network Jitter Dominated
    if abs(global_rho) < 0.15 and abs(mean_conflict_rho) < 0.20 and inversion_ratio > 0.40:
        return (
            "ARRIVAL_ORDER_JITTER_DOMINATED",
            0.80,
            f"Near-zero correlation (global rho={global_rho:.2f}, cluster rho={mean_conflict_rho:.2f}) with high inversion ratio ({inversion_ratio:.2f}). Network transit time and QUIC packet arrivals dominate over priority fees."
        )

    # Default fallback
    return (
        "HYBRID_PARTIAL_ORDERING",
        0.70,
        f"Hybrid behavior with global rho={global_rho:.2f}, conflict rho={mean_conflict_rho:.2f}, inversion ratio={inversion_ratio:.2f}."
    )
