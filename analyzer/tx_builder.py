"""
Probe Transaction Builder.
Constructs valid Solana wire transactions with Compute Budget priority fee ladders.
Supports dry-run mock generation and live signed transaction synthesis.
"""

from typing import Dict, Any, List, Optional, Tuple
import struct
import base64
import os
import logging
from .block_parser import b58decode

logger = logging.getLogger("solana_analyzer.tx_builder")

COMPUTE_BUDGET_ID = "ComputeBudget111111111111111111111111111111"
MEMO_PROGRAM_ID = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"
SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"


def create_compute_unit_limit_instruction(limit: int) -> bytes:
    """Encodes SetComputeUnitLimit instruction (tag 2, u32 little-endian)."""
    return bytes([2]) + struct.pack("<I", limit)


def create_compute_unit_price_instruction(micro_lamports: int) -> bytes:
    """Encodes SetComputeUnitPrice instruction (tag 3, u64 little-endian)."""
    return bytes([3]) + struct.pack("<Q", micro_lamports)


class ProbeTransactionBuilder:
    """Generates synthetic probe transactions with varying priority fee levels."""

    def __init__(self, keypair_path: Optional[str] = None):
        self.keypair_path = keypair_path
        self._keypair = None
        if keypair_path and os.path.exists(keypair_path):
            self._load_keypair(keypair_path)

    def _load_keypair(self, path: str) -> None:
        """Loads keypair securely from file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                # Store key safely without logging
                self._keypair = content
                logger.info("Loaded keypair from %s", path)
        except Exception as e:
            logger.error("Failed to load keypair from %s: %s", path, e)

    def build_mock_probe(
        self,
        probe_id: int,
        target_validator: str,
        target_slot: int,
        cu_limit: int,
        cu_price_micro_lamports: int,
        recent_blockhash: str
    ) -> Dict[str, Any]:
        """
        Builds a dry-run probe transaction descriptor.
        Calculates exact expected fee without spending real SOL.
        """
        base_fee = 5000  # standard 1-signature base fee
        priority_fee = (cu_limit * cu_price_micro_lamports) // 1_000_000
        total_fee = base_fee + priority_fee

        mock_signature = f"mock_probe_{probe_id:04d}_slot_{target_slot}_{cu_price_micro_lamports}microLamports"

        return {
            "probe_id": probe_id,
            "target_validator": target_validator,
            "target_slot": target_slot,
            "cu_limit": cu_limit,
            "cu_price": cu_price_micro_lamports,
            "base_fee": base_fee,
            "priority_fee": priority_fee,
            "total_fee_lamports": total_fee,
            "recent_blockhash": recent_blockhash,
            "mock_signature": mock_signature,
            "is_dry_run": True
        }
