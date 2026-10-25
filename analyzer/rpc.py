"""
Solana JSON-RPC 2.0 client module.
Implements robust HTTP communication with exponential backoff and rate-limit handling.
"""

from typing import Any, Dict, List, Optional
import json
import logging
import time
import requests

logger = logging.getLogger("solana_analyzer.rpc")

DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"


class SolanaRpcClient:
    """Production-grade Solana JSON-RPC client with exponential backoff."""

    def __init__(self, endpoint: str = DEFAULT_RPC_URL, timeout: float = 30.0, max_retries: int = 5):
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "SolanaInsideTheBlockAnalyzer/1.0"
        })
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def call(self, method: str, params: Optional[List[Any]] = None) -> Any:
        """Executes a JSON-RPC method with retry and exponential backoff."""
        req_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or []
        }

        delay = 1.0
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.post(
                    self.endpoint,
                    json=payload,
                    timeout=self.timeout
                )

                if response.status_code == 429:
                    logger.warning("RPC returned 429 Too Many Requests (attempt %d/%d). Backing off %.1fs", attempt, self.max_retries, delay)
                    time.sleep(delay)
                    delay = min(delay * 2.0, 16.0)
                    continue

                if response.status_code != 200:
                    logger.warning("HTTP %d error on RPC call %s: %s", response.status_code, method, response.text[:200])
                    time.sleep(delay)
                    delay = min(delay * 1.5, 10.0)
                    continue

                data = response.json()
                if "error" in data:
                    err = data["error"]
                    # If block was skipped or cleaned up, return None or raise
                    if err.get("code") in (-32004, -32007, -32009):
                        logger.debug("Slot skipped or not available: %s", err)
                        return None
                    last_error = RuntimeError(f"RPC Error ({err.get('code')}): {err.get('message')}")
                    logger.warning("RPC error response on %s: %s", method, err)
                    time.sleep(delay)
                    delay = min(delay * 1.5, 10.0)
                    continue

                return data.get("result")

            except (requests.RequestException, json.JSONDecodeError) as e:
                last_error = e
                logger.warning("Network error on %s attempt %d/%d: %s", method, attempt, self.max_retries, e)
                time.sleep(delay)
                delay = min(delay * 2.0, 16.0)

        if last_error:
            raise last_error
        raise RuntimeError(f"Failed RPC request {method} after {self.max_retries} retries")

    def get_slot(self) -> int:
        """Returns the current slot."""
        res = self.call("getSlot", [{"commitment": "confirmed"}])
        return int(res)

    def get_cluster_nodes(self) -> List[Dict[str, Any]]:
        """Returns information about all nodes currently in the gossip cluster."""
        res = self.call("getClusterNodes")
        return res or []

    def get_vote_accounts(self) -> Dict[str, Any]:
        """Returns current and delinquent vote accounts with activated stake."""
        res = self.call("getVoteAccounts")
        return res or {"current": [], "delinquent": []}

    def get_slot_leaders(self, start_slot: int, limit: int = 100) -> List[str]:
        """Returns the leader identity pubkeys for the given slot range."""
        res = self.call("getSlotLeaders", [start_slot, limit])
        return res or []

    def get_leader_schedule(self, slot: Optional[int] = None) -> Optional[Dict[str, List[int]]]:
        """Returns the leader schedule for an epoch or slot."""
        params = []
        if slot is not None:
            params.append(slot)
        return self.call("getLeaderSchedule", params)

    def get_block(self, slot: int, max_supported_tx_version: int = 1, tx_details: str = "full") -> Optional[Dict[str, Any]]:
        """
        Fetches block data for a confirmed/finalized slot.
        Uses maxSupportedTransactionVersion: 1 to support all modern transaction versions.
        """
        config = {
            "encoding": "json",
            "maxSupportedTransactionVersion": max_supported_tx_version,
            "transactionDetails": tx_details,
            "rewards": False
        }
        return self.call("getBlock", [slot, config])

    def get_balance(self, pubkey: str) -> int:
        """Returns balance in lamports."""
        res = self.call("getBalance", [pubkey, {"commitment": "confirmed"}])
        return res.get("value", 0) if isinstance(res, dict) else int(res or 0)

    def get_latest_blockhash(self) -> Dict[str, Any]:
        """Returns the latest blockhash and last valid block height."""
        res = self.call("getLatestBlockhash", [{"commitment": "confirmed"}])
        return res.get("value", {}) if isinstance(res, dict) else {}

    def send_transaction(self, base64_tx: str) -> str:
        """Submits a signed transaction in base64 encoding."""
        res = self.call("sendTransaction", [
            base64_tx,
            {"encoding": "base64", "preflightCommitment": "confirmed", "maxRetries": 3}
        ])
        return str(res)
