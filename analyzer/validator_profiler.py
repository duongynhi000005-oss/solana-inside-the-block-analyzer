"""
Validator Profiler & Cohort Selector.
Selects representative validators across distinct client software families,
collects their recent production blocks, and aggregates empirical ordering metrics.
"""

from typing import Dict, Any, List, Optional
import logging
from dataclasses import asdict
from .rpc import SolanaRpcClient
from .leader_tracker import LeaderTracker, ValidatorNodeInfo
from .block_parser import parse_block
from .scheduler_analyzer import analyze_block_ordering, BlockOrderingAnalysis

logger = logging.getLogger("solana_analyzer.validator_profiler")


class ValidatorProfiler:
    """Selects and analyzes representative validators across diverse client architectures."""

    def __init__(self, rpc: SolanaRpcClient, tracker: LeaderTracker):
        self.rpc = rpc
        self.tracker = tracker

    def select_diverse_cohort(
        self,
        min_stake_lamports: int = 10_000_000_000,
        target_per_family: int = 2
    ) -> List[ValidatorNodeInfo]:
        """
        Selects at least 6 validators spanning >= 3 distinct client families.
        Families prioritized: Agave, Jito, Firedancer, Rakurai.
        """
        families = self.tracker.find_validators_by_family(min_stake=min_stake_lamports)
        cohort: List[ValidatorNodeInfo] = []

        # Required core families
        for fam_name in ["Firedancer", "Jito", "Agave", "Rakurai"]:
            nodes = families.get(fam_name, [])
            selected = nodes[:target_per_family]
            cohort.extend(selected)
            logger.info("Selected %d validators from family %s", len(selected), fam_name)

        logger.info("Total cohort size: %d validators across %d client families.", len(cohort), len(set(n.client_family for n in cohort)))
        return cohort

    def profile_validator_blocks(
        self,
        validator: ValidatorNodeInfo,
        slots: List[int]
    ) -> List[BlockOrderingAnalysis]:
        """
        Downloads and analyzes blocks produced by a specific validator.
        """
        analyses: List[BlockOrderingAnalysis] = []

        for slot in slots:
            try:
                raw_block = self.rpc.get_block(slot, max_supported_tx_version=1, tx_details="full")
                if not raw_block:
                    logger.warning("Slot %d skipped or empty.", slot)
                    continue

                parsed_block = parse_block(raw_block, slot=slot, leader_pubkey=validator.node_pubkey)
                analysis = analyze_block_ordering(
                    block=parsed_block,
                    client_family=validator.client_family,
                    client_version=validator.version
                )
                analyses.append(analysis)
                logger.info(
                    "Slot %d analyzed (%s %s): %d txs, rho=%.3f, inversion_ratio=%.3f -> %s",
                    slot, validator.client_family, validator.version,
                    analysis.non_vote_txs, analysis.global_spearman_rho,
                    analysis.global_inversion_ratio, analysis.scheduler_verdict
                )
            except Exception as e:
                logger.error("Failed to analyze slot %d: %s", slot, e)

        return analyses
