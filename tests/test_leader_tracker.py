"""
Unit tests for LeaderTracker and Client Classifier.
Ensures correct recognition of Firedancer, Jito, Agave, and Rakurai validator nodes.
"""

import pytest
from analyzer.leader_tracker import classify_client


def test_classify_client():
    # Firedancer / Frankendancer
    assert classify_client("firedancer-v0.1.2", "26.10") == "Firedancer"
    assert classify_client("frankendancer", "0.114.0") == "Firedancer"
    assert classify_client(None, "26.10.0") == "Firedancer"

    # Jito
    assert classify_client("jito-solana", "2.0.14-jito") == "Jito"
    assert classify_client("solana-labs", "2.0.14-jito") == "Jito"

    # Rakurai
    assert classify_client("rakurai-v1", "1.18.26") == "Rakurai"

    # Agave / Solana Labs
    assert classify_client("agave", "2.0.15") == "Agave"
    assert classify_client("solanalabs", "1.18.25") == "Agave"
    assert classify_client("", "2.0.12") == "Agave"
    assert classify_client(None, None) == "Agave"

    # Other
    assert classify_client("custom-obscure-client", "1.0.0") == "Other"
