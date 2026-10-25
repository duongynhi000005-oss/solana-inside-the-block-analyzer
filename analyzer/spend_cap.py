"""
Hard Spend-Cap Management Module.
Strictly limits transaction fee expenditures to a maximum of 0.05 SOL.
Prevents unintended cost overruns in automated measurement pipelines.
"""

from typing import Dict, Any, List
import logging
import threading

logger = logging.getLogger("solana_analyzer.spend_cap")

# Hard ceiling: 0.05 SOL = 50,000,000 lamports
MAX_SPEND_LAMPORTS: int = 50_000_000
LAMPORTS_PER_SOL: int = 1_000_000_000


class SpendCapExceededError(Exception):
    """Raised when an operation would exceed the hard spend-cap."""
    pass


class SpendCapManager:
    """Thread-safe ledger tracking cumulative lamports spent across probes."""

    def __init__(self, max_lamports: int = MAX_SPEND_LAMPORTS, dry_run: bool = True):
        self.max_lamports = max_lamports
        self.dry_run = dry_run
        self._spent_lamports: int = 0
        self._probe_history: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    @property
    def spent_lamports(self) -> int:
        with self._lock:
            return self._spent_lamports

    @property
    def remaining_lamports(self) -> int:
        with self._lock:
            return max(0, self.max_lamports - self._spent_lamports)

    @property
    def spent_sol(self) -> float:
        return self.spent_lamports / LAMPORTS_PER_SOL

    @property
    def remaining_sol(self) -> float:
        return self.remaining_lamports / LAMPORTS_PER_SOL

    def check_can_spend(self, amount_lamports: int) -> bool:
        """Verifies if the specified amount can be spent without breaching the cap."""
        with self._lock:
            return (self._spent_lamports + amount_lamports) <= self.max_lamports

    def commit_spend(self, amount_lamports: int, context: str = "") -> None:
        """
        Commits an expenditure to the ledger.
        Raises SpendCapExceededError if the spend-cap would be breached.
        """
        with self._lock:
            if (self._spent_lamports + amount_lamports) > self.max_lamports:
                msg = (
                    f"SPEND CAP BREACH PREVENTED: Cannot spend {amount_lamports} lamports. "
                    f"Already spent {self._spent_lamports}/{self.max_lamports} lamports "
                    f"({self._spent_lamports / LAMPORTS_PER_SOL:.6f} / {self.max_lamports / LAMPORTS_PER_SOL:.4f} SOL). "
                    f"Context: {context}"
                )
                logger.error(msg)
                raise SpendCapExceededError(msg)

            self._spent_lamports += amount_lamports
            record = {
                "amount_lamports": amount_lamports,
                "cumulative_spent": self._spent_lamports,
                "context": context,
                "dry_run": self.dry_run
            }
            self._probe_history.append(record)
            logger.info(
                "Spend committed: %d lamports (%s). Cumulative: %d/%d (%.6f SOL)",
                amount_lamports, "[DRY-RUN]" if self.dry_run else "[LIVE]",
                self._spent_lamports, self.max_lamports, self.spent_sol
            )

    def get_audit_summary(self) -> Dict[str, Any]:
        """Returns full audit ledger of all spends."""
        with self._lock:
            return {
                "max_allowed_lamports": self.max_lamports,
                "max_allowed_sol": self.max_lamports / LAMPORTS_PER_SOL,
                "total_spent_lamports": self._spent_lamports,
                "total_spent_sol": self.spent_sol,
                "remaining_sol": self.remaining_sol,
                "dry_run": self.dry_run,
                "total_probes": len(self._probe_history),
                "history": list(self._probe_history)
            }
