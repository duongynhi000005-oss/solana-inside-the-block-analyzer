"""
Block Parser & Transaction Dissector.
Extracts transaction position, Compute Budget instruction parameters (CU limit, CU price),
effective priority fees, and write-lock account sets from Solana block payloads.
"""

from typing import Dict, Any, List, Set, Optional, Tuple
from dataclasses import dataclass, field
import struct
import logging

logger = logging.getLogger("solana_analyzer.block_parser")

# Pure Base58 decoder for zero-dependency decoding of instruction payloads
B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58_MAP = {c: i for i, c in enumerate(B58_ALPHABET)}

COMPUTE_BUDGET_PROGRAM_ID = "ComputeBudget111111111111111111111111111111"
VOTE_PROGRAM_ID = "Vote111111111111111111111111111111111111111"
SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"


def b58decode(s: str) -> bytes:
    """Decodes a base58-encoded string into bytes."""
    if not s:
        return b""
    origlen = len(s)
    s = s.lstrip('1')
    newlen = len(s)
    acc = 0
    for char in s:
        val = B58_MAP.get(char)
        if val is None:
            return b""
        acc = acc * 58 + val
    res = bytearray()
    while acc > 0:
        res.append(acc & 0xFF)
        acc >>= 8
    res.reverse()
    pad = b'\x00' * (origlen - newlen)
    return pad + bytes(res)


@dataclass
class ParsedTransaction:
    """Dissected transaction details relevant to scheduler analysis."""
    signature: str
    position_index: int
    base_fee: int
    priority_fee: int
    total_fee: int
    compute_units_consumed: int
    compute_unit_limit: int
    compute_unit_price: int  # in micro-lamports per CU
    effective_priority_rate: float  # priority fee / CU limit (or micro-lamports per CU)
    writable_accounts: List[str] = field(default_factory=list)
    readonly_accounts: List[str] = field(default_factory=list)
    is_vote: bool = False
    is_successful: bool = True
    raw_instructions_count: int = 0


@dataclass
class ParsedBlock:
    """Parsed Solana block structure."""
    slot: int
    blockhash: str
    parent_slot: int
    block_time: Optional[int]
    leader_pubkey: str
    total_transactions: int
    non_vote_transactions: int
    transactions: List[ParsedTransaction] = field(default_factory=list)


def parse_compute_budget_instruction(raw_bytes: bytes) -> Tuple[Optional[int], Optional[int]]:
    """
    Decodes Compute Budget instruction.
    Returns (cu_limit, cu_price_micro_lamports).
    """
    if not raw_bytes or len(raw_bytes) < 1:
        return None, None

    tag = raw_bytes[0]
    # tag 2: SetComputeUnitLimit (u8 tag=2, u32 limit)
    if tag == 2 and len(raw_bytes) >= 5:
        limit = struct.unpack("<I", raw_bytes[1:5])[0]
        return limit, None
    # tag 3: SetComputeUnitPrice (u8 tag=3, u64 price in micro-lamports)
    elif tag == 3 and len(raw_bytes) >= 9:
        price = struct.unpack("<Q", raw_bytes[1:9])[0]
        return None, price

    return None, None


def dissect_transaction(tx_dict: Dict[str, Any], position_index: int) -> Optional[ParsedTransaction]:
    """Dissects a single raw JSON-RPC transaction dictionary into ParsedTransaction."""
    meta = tx_dict.get("meta") or {}
    tx = tx_dict.get("transaction") or {}
    signatures = tx.get("signatures") or []
    sig = signatures[0] if signatures else f"unknown_{position_index}"

    message = tx.get("message") or {}
    account_keys = message.get("accountKeys") or []
    
    # Handle address table lookups (loadedAddresses in meta)
    loaded_addresses = meta.get("loadedAddresses") or {}
    writable_loaded = loaded_addresses.get("writable") or []
    readonly_loaded = loaded_addresses.get("readonly") or []

    # Parse header for account write-lock status
    header = message.get("header") or {}
    num_req_sigs = header.get("numRequiredSignatures", 1)
    num_ro_signed = header.get("numReadonlySignedAccounts", 0)
    num_ro_unsigned = header.get("numReadonlyUnsignedAccounts", 0)

    # Determine base accounts writable vs readonly
    num_signed_writable = max(0, num_req_sigs - num_ro_signed)
    total_base = len(account_keys)
    num_unsigned_writable = max(0, total_base - num_req_sigs - num_ro_unsigned)

    writable_accounts: List[str] = []
    readonly_accounts: List[str] = []

    # 1. Signed writable
    for i in range(0, min(num_signed_writable, total_base)):
        writable_accounts.append(account_keys[i])
    # 2. Signed readonly
    for i in range(num_signed_writable, min(num_req_sigs, total_base)):
        readonly_accounts.append(account_keys[i])
    # 3. Unsigned writable
    for i in range(num_req_sigs, min(num_req_sigs + num_unsigned_writable, total_base)):
        writable_accounts.append(account_keys[i])
    # 4. Unsigned readonly
    for i in range(num_req_sigs + num_unsigned_writable, total_base):
        readonly_accounts.append(account_keys[i])

    # Append loaded addresses
    writable_accounts.extend(writable_loaded)
    readonly_accounts.extend(readonly_loaded)

    # Fee and compute units
    total_fee = meta.get("fee", 5000)
    cu_consumed = meta.get("computeUnitsConsumed", 0)
    err = meta.get("err")
    is_successful = (err is None)

    # Look for Compute Budget program instructions
    cu_limit = 200_000  # Solana default CU limit if not specified
    cu_price = 0
    is_vote = False

    cb_indices = [i for i, k in enumerate(account_keys) if k == COMPUTE_BUDGET_PROGRAM_ID]
    vote_indices = [i for i, k in enumerate(account_keys) if k == VOTE_PROGRAM_ID]

    instructions = message.get("instructions") or []
    for ix in instructions:
        prog_idx = ix.get("programIdIndex", -1)
        if prog_idx in vote_indices:
            is_vote = True
        if prog_idx in cb_indices:
            data_b58 = ix.get("data", "")
            raw = b58decode(data_b58)
            lim, pr = parse_compute_budget_instruction(raw)
            if lim is not None:
                cu_limit = lim
            if pr is not None:
                cu_price = pr

    # Calculate theoretical priority fee vs base fee
    # In Solana, base fee is 5000 lamports per signature
    num_sigs = max(1, len(signatures))
    base_fee = num_sigs * 5000
    calc_priority_fee = (cu_limit * cu_price) // 1_000_000
    # True priority fee is total_fee - base_fee, capped at 0 minimum
    priority_fee = max(0, total_fee - base_fee)
    if priority_fee == 0 and calc_priority_fee > 0:
        priority_fee = calc_priority_fee

    effective_priority_rate = float(cu_price)

    return ParsedTransaction(
        signature=sig,
        position_index=position_index,
        base_fee=base_fee,
        priority_fee=priority_fee,
        total_fee=total_fee,
        compute_units_consumed=cu_consumed,
        compute_unit_limit=cu_limit,
        compute_unit_price=cu_price,
        effective_priority_rate=effective_priority_rate,
        writable_accounts=writable_accounts,
        readonly_accounts=readonly_accounts,
        is_vote=is_vote,
        is_successful=is_successful,
        raw_instructions_count=len(instructions)
    )


def parse_block(raw_block: Dict[str, Any], slot: int, leader_pubkey: str = "") -> ParsedBlock:
    """Parses a full block JSON object into ParsedBlock structure."""
    blockhash = raw_block.get("blockhash", "")
    parent_slot = raw_block.get("parentSlot", 0)
    block_time = raw_block.get("blockTime")
    raw_txs = raw_block.get("transactions") or []

    parsed_txs: List[ParsedTransaction] = []
    non_vote_count = 0

    for idx, raw_tx in enumerate(raw_txs):
        ptx = dissect_transaction(raw_tx, idx)
        if ptx:
            parsed_txs.append(ptx)
            if not ptx.is_vote:
                non_vote_count += 1

    return ParsedBlock(
        slot=slot,
        blockhash=blockhash,
        parent_slot=parent_slot,
        block_time=block_time,
        leader_pubkey=leader_pubkey,
        total_transactions=len(parsed_txs),
        non_vote_transactions=non_vote_count,
        transactions=parsed_txs
    )
