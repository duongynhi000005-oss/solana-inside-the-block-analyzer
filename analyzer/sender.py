"""
Probe Dispatcher & Sender Module.
Coordinates the timing and injection of priority fee ladder probes
into target validator leader windows with strict spend-cap enforcement.
"""

from typing import Dict, Any, List, Optional
import time
import logging
from .rpc import SolanaRpcClient
from .spend_cap import SpendCapManager, SpendCapExceededError
from .tx_builder import ProbeTransactionBuilder
from .leader_tracker import LeaderTracker, ValidatorNodeInfo

logger = logging.getLogger("solana_analyzer.sender")

DEFAULT_FEE_LADDER = [
    0,            # Base fee only (0 micro-lamports/CU)
    1_000,        # 1k micro-lamports/CU (low priority)
    5_000,        # 5k micro-lamports/CU (standard priority)
    25_000,       # 25k micro-lamports/CU (elevated priority)
    100_000,      # 100k micro-lamports/CU (high priority)
    500_000       # 500k micro-lamports/CU (ultra-high priority)
]


class ProbeSender:
    """Manages probe dispatches into validator leader slots."""

    def __init__(
        self,
        rpc: SolanaRpcClient,
        leader_tracker: LeaderTracker,
        spend_cap: SpendCapManager,
        tx_builder: ProbeTransactionBuilder,
        dry_run: bool = True
    ):
        self.rpc = rpc
        self.leader_tracker = leader_tracker
        self.spend_cap = spend_cap
        self.tx_builder = tx_builder
        self.dry_run = dry_run
        self.dispatch_log: List[Dict[str, Any]] = []

    def run_dry_run_ladder(
        self,
        target_validator: ValidatorNodeInfo,
        target_slots: List[int],
        cu_limit: int = 10_000,
        fee_ladder: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes a dry-run probe ladder simulation for a validator across scheduled slots.
        Verifies fee calculations and spend cap ledger without sending real transactions.
        """
        ladder = fee_ladder or DEFAULT_FEE_LADDER
        logger.info(
            "Running DRY-RUN probe ladder for %s (%s %s) across %d slots.",
            target_validator.node_pubkey[:8],
            target_validator.client_family,
            target_validator.version,
            len(target_slots)
        )

        results = []
        blockhash_info = self.rpc.get_latest_blockhash()
        blockhash = blockhash_info.get("blockhash", "DryRunBlockhash111111111111111111111111111")

        probe_counter = len(self.dispatch_log) + 1

        for slot in target_slots:
            for cu_price in ladder:
                probe = self.tx_builder.build_mock_probe(
                    probe_id=probe_counter,
                    target_validator=target_validator.node_pubkey,
                    target_slot=slot,
                    cu_limit=cu_limit,
                    cu_price_micro_lamports=cu_price,
                    recent_blockhash=blockhash
                )

                fee_lamports = probe["total_fee_lamports"]
                # Commit to spend cap ledger
                self.spend_cap.commit_spend(
                    amount_lamports=fee_lamports,
                    context=f"Dry-run probe {probe_counter} for slot {slot} (validator {target_validator.node_pubkey[:8]})"
                )

                probe["client_family"] = target_validator.client_family
                probe["client_version"] = target_validator.version
                results.append(probe)
                self.dispatch_log.append(probe)
                probe_counter += 1

        return results
