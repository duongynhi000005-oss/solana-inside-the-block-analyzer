"""
Unit tests for ProbeTransactionBuilder.
Validates instruction generation and mock probe fee calculations.
"""

import pytest
import struct
from analyzer.tx_builder import (
    create_compute_unit_limit_instruction,
    create_compute_unit_price_instruction,
    ProbeTransactionBuilder
)


def test_instruction_encoders():
    limit_ix = create_compute_unit_limit_instruction(150_000)
    assert limit_ix[0] == 2
    decoded_lim = struct.unpack("<I", limit_ix[1:5])[0]
    assert decoded_lim == 150_000

    price_ix = create_compute_unit_price_instruction(12_500)
    assert price_ix[0] == 3
    decoded_price = struct.unpack("<Q", price_ix[1:9])[0]
    assert decoded_price == 12_500


def test_probe_builder_mock():
    builder = ProbeTransactionBuilder()
    probe = builder.build_mock_probe(
        probe_id=1,
        target_validator="ValNode11111111111111111111111111111111111",
        target_slot=300050,
        cu_limit=100_000,
        cu_price_micro_lamports=50_000,  # 50,000 micro-lamports/CU
        recent_blockhash="RecentHash11111111111111111111111111111111"
    )

    # Base fee = 5000 lamports
    # Priority fee = (100,000 * 50,000) // 1,000,000 = 5000 lamports
    # Total fee = 10,000 lamports
    assert probe["base_fee"] == 5000
    assert probe["priority_fee"] == 5000
    assert probe["total_fee_lamports"] == 10000
    assert probe["is_dry_run"] is True
    assert "mock_probe_0001" in probe["mock_signature"]
