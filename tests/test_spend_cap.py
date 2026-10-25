"""
Unit tests for SpendCapManager.
Ensures strict enforcement of 0.05 SOL spend ceiling and thread safety.
"""

import pytest
import threading
from analyzer.spend_cap import SpendCapManager, SpendCapExceededError, MAX_SPEND_LAMPORTS, LAMPORTS_PER_SOL


def test_spend_cap_initial_state():
    manager = SpendCapManager(max_lamports=50_000_000, dry_run=True)
    assert manager.spent_lamports == 0
    assert manager.remaining_lamports == 50_000_000
    assert manager.spent_sol == 0.0
    assert manager.remaining_sol == 0.05
    assert manager.check_can_spend(10_000) is True


def test_spend_cap_commit_success():
    manager = SpendCapManager(max_lamports=100_000, dry_run=True)
    manager.commit_spend(30_000, "Probe 1")
    assert manager.spent_lamports == 30_000
    assert manager.remaining_lamports == 70_000
    assert manager.check_can_spend(70_000) is True
    assert manager.check_can_spend(70_001) is False

    manager.commit_spend(70_000, "Probe 2")
    assert manager.spent_lamports == 100_000
    assert manager.remaining_lamports == 0
    assert manager.check_can_spend(1) is False


def test_spend_cap_exceeded_error():
    manager = SpendCapManager(max_lamports=50_000, dry_run=True)
    manager.commit_spend(40_000, "Initial spend")

    with pytest.raises(SpendCapExceededError) as exc_info:
        manager.commit_spend(15_000, "Over budget probe")

    assert "SPEND CAP BREACH PREVENTED" in str(exc_info.value)
    assert manager.spent_lamports == 40_000  # uncommitted


def test_spend_cap_thread_safety():
    manager = SpendCapManager(max_lamports=10_000_000, dry_run=True)
    threads = []
    num_threads = 20
    spend_per_thread = 50_000

    def worker():
        for _ in range(10):
            manager.commit_spend(spend_per_thread, "Thread worker")

    for _ in range(num_threads):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    expected_total = num_threads * 10 * spend_per_thread
    assert manager.spent_lamports == expected_total


def test_spend_cap_audit_summary():
    manager = SpendCapManager(max_lamports=1_000_000, dry_run=False)
    manager.commit_spend(250_000, "Mainnet Probe A")
    summary = manager.get_audit_summary()

    assert summary["max_allowed_lamports"] == 1_000_000
    assert summary["total_spent_lamports"] == 250_000
    assert summary["total_spent_sol"] == 0.00025
    assert summary["dry_run"] is False
    assert summary["total_probes"] == 1
    assert len(summary["history"]) == 1
