"""
Unit tests for BlockParser & Transaction Dissector.
Validates instruction decoding, compute budget extraction, and account write-lock status.
"""

import pytest
import struct
from analyzer.block_parser import (
    b58decode,
    parse_compute_budget_instruction,
    dissect_transaction,
    parse_block,
    COMPUTE_BUDGET_PROGRAM_ID,
    VOTE_PROGRAM_ID
)


def test_b58decode():
    # Test standard base58 decoding
    assert b58decode("") == b""
    # 1 in base58 is zero byte
    assert b58decode("1") == b"\x00"
    assert b58decode("11") == b"\x00\x00"
    # Known b58 vectors
    # "2g" -> 58 * 1 + 39 = 97 (0x61, ASCII 'a')
    assert b58decode("2g") == b"\x61"


def test_parse_compute_budget_instruction():
    # Tag 2: SetComputeUnitLimit (100,000 = 0x000186A0)
    raw_limit = bytes([2]) + struct.pack("<I", 100_000)
    lim, pr = parse_compute_budget_instruction(raw_limit)
    assert lim == 100_000
    assert pr is None

    # Tag 3: SetComputeUnitPrice (50,000 micro-lamports = 0x000000000000C350)
    raw_price = bytes([3]) + struct.pack("<Q", 50_000)
    lim2, pr2 = parse_compute_budget_instruction(raw_price)
    assert lim2 is None
    assert pr2 == 50_000

    # Unknown tag
    raw_unknown = bytes([99, 1, 2, 3])
    l3, p3 = parse_compute_budget_instruction(raw_unknown)
    assert l3 is None
    assert p3 is None


def test_dissect_transaction_with_priority_fee():
    # Encode compute budget instruction data in Base58
    # Tag 3, price 25,000
    cb_bytes = bytes([3]) + struct.pack("<Q", 25_000)
    # Simple manual base58 encoding of cb_bytes
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    acc = int.from_bytes(cb_bytes, "big")
    b58_str = ""
    while acc > 0:
        acc, rem = divmod(acc, 58)
        b58_str = alphabet[rem] + b58_str

    mock_tx = {
        "transaction": {
            "signatures": ["5Hkd97...sig1"],
            "message": {
                "header": {
                    "numRequiredSignatures": 1,
                    "numReadonlySignedAccounts": 0,
                    "numReadonlyUnsignedAccounts": 1
                },
                "accountKeys": [
                    "Sender11111111111111111111111111111111111",      # signed writable
                    "TargetPool1111111111111111111111111111111",     # unsigned writable
                    COMPUTE_BUDGET_PROGRAM_ID                         # unsigned readonly
                ],
                "instructions": [
                    {
                        "programIdIndex": 2,
                        "data": b58_str
                    }
                ]
            }
        },
        "meta": {
            "fee": 10000,
            "computeUnitsConsumed": 45000,
            "err": None,
            "loadedAddresses": {
                "writable": ["LoadedWritable111111111111111111111111111"],
                "readonly": []
            }
        }
    }

    ptx = dissect_transaction(mock_tx, position_index=4)
    assert ptx is not None
    assert ptx.signature == "5Hkd97...sig1"
    assert ptx.position_index == 4
    assert ptx.base_fee == 5000
    assert ptx.total_fee == 10000
    assert ptx.priority_fee == 5000
    assert ptx.compute_units_consumed == 45000
    assert ptx.compute_unit_price == 25_000
    assert ptx.is_vote is False
    assert ptx.is_successful is True

    # Account write locks
    assert "Sender11111111111111111111111111111111111" in ptx.writable_accounts
    assert "TargetPool1111111111111111111111111111111" in ptx.writable_accounts
    assert "LoadedWritable111111111111111111111111111" in ptx.writable_accounts
    assert COMPUTE_BUDGET_PROGRAM_ID in ptx.readonly_accounts


def test_dissect_vote_transaction():
    mock_tx = {
        "transaction": {
            "signatures": ["VoteSig111111111111111111111111111111111111111"],
            "message": {
                "header": {
                    "numRequiredSignatures": 1,
                    "numReadonlySignedAccounts": 0,
                    "numReadonlyUnsignedAccounts": 1
                },
                "accountKeys": [
                    "VoteAcc11111111111111111111111111111111111",
                    VOTE_PROGRAM_ID
                ],
                "instructions": [
                    {"programIdIndex": 1, "data": ""}
                ]
            }
        },
        "meta": {"fee": 5000, "computeUnitsConsumed": 2100, "err": None}
    }

    ptx = dissect_transaction(mock_tx, position_index=0)
    assert ptx is not None
    assert ptx.is_vote is True
    assert ptx.priority_fee == 0


def test_parse_block():
    raw_block = {
        "blockhash": "4uQeVj5tqViQh7yWWGStvfEG1Nmq6e86XG1dF49UcmwA",
        "parentSlot": 299999,
        "blockTime": 1729000000,
        "transactions": [
            {
                "transaction": {
                    "signatures": ["sig_vote"],
                    "message": {
                        "header": {"numRequiredSignatures": 1, "numReadonlySignedAccounts": 0, "numReadonlyUnsignedAccounts": 0},
                        "accountKeys": ["acc1", VOTE_PROGRAM_ID],
                        "instructions": [{"programIdIndex": 1, "data": ""}]
                    }
                },
                "meta": {"fee": 5000}
            },
            {
                "transaction": {
                    "signatures": ["sig_user"],
                    "message": {
                        "header": {"numRequiredSignatures": 1, "numReadonlySignedAccounts": 0, "numReadonlyUnsignedAccounts": 0},
                        "accountKeys": ["user1"],
                        "instructions": []
                    }
                },
                "meta": {"fee": 5000}
            }
        ]
    }

    parsed = parse_block(raw_block, slot=300000, leader_pubkey="Leader1111111111111111111111111111111111")
    assert parsed.slot == 300000
    assert parsed.total_transactions == 2
    assert parsed.non_vote_transactions == 1
    assert parsed.leader_pubkey == "Leader1111111111111111111111111111111111"
