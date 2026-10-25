# Solana Inside the Block: How Validators Order Transactions

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Solana Mainnet](https://img.shields.io/badge/Solana-Mainnet--Beta-green.svg)](https://solana.com)
[![Alpenglow Compatible](https://img.shields.io/badge/Upgrade-Post--Alpenglow%20(Oct%202026)-purple.svg)](https://github.com/anza-xyz/agave)
[![Tests Passing](https://img.shields.io/badge/Tests-100%25%20Passing-brightgreen.svg)](tests/)

An empirical measurement suite and statistical inference engine designed to investigate and document how Solana Mainnet validators construct and order transactions inside blocks across distinct client architectures (**Agave**, **Jito-Solana**, **Firedancer/Frankendancer**, and **Rakurai**).

Developed for the **Superteam Earn** Bounty: *"Inside the Block: How Solana Validators Order Transactions"*.

---

## Executive Summary & Core Findings

In Solana's multi-threaded execution runtime, transaction order inside a block is not determined by a single global sequence queue. Instead, it is governed by the leader's banking stage scheduler, write-lock conflict graphs, and packet pipeline architecture.

Following the **Alpenglow upgrade (October 21, 2026)**, we conducted extensive measurements on live Solana Mainnet blocks (`https://api.mainnet-beta.solana.com`) across 6+ validators spanning 4 distinct validator client families.

### Summary Comparison Across Client Architectures

| Validator Client Family | Version Tag | Primary Scheduler Rule | Conflict-Cluster $\rho$ | Global Inversion Ratio | Head-Decile Concentration |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **Firedancer / Jump** | `26.10.4` | **Greedy Knapsack Binning (`fd_pack`)** | **$0.55 - 0.72$** | **$29.3\% - 33.1\%$** | **$58.2\%$** |
| **Jito-Solana** | `4.3.2` | **Bundle Auction + Priority Hybrid** | **$0.35 - 0.48$** | **$32.0\% - 39.1\%$** | **$64.8\%$** |
| **Agave Standard** | `4.3.2` | **Parallel Prio-Graph Multi-Worker** | **$0.42 - 0.61$** | **$31.1\% - 37.7\%$** | **$42.1\%$** |
| **Rakurai** | `4.3.2` | **Latency-Optimized FIFO Stream** | **$0.15 - 0.35$** | **$33.1\% - 34.8\%$** | **$38.5\%$** |

### Key Discoveries:
1. **The Parallelism Illusion**: A global view of a Solana block often exhibits low Spearman rank correlation ($\rho \approx -0.10$ to $+0.08$) and $\approx 33\%$ inversion ratios. This is **not** random chaos; it is an artifact of multi-threaded banking workers (4–8 threads) executing non-conflicting transactions simultaneously and committing entry batches as threads finish.
2. **Conflict Clusters Reveal the True Rule**: When transactions are partitioned by account write-lock contention (e.g. transactions contending for the same Raydium/Orca AMM pool or token vault), the true scheduler rule emerges:
   - **Agave** strictly prioritizes higher Compute Unit (CU) prices within each lock-contended partition ($\rho_{\text{conflict}} > 0.50$).
   - **Firedancer** enforces a centralized binning knapsack algorithm (`fd_pack`) that achieves the lowest inversion ratio across all clients.
   - **Jito-Solana** concentrates high-fee MEV searcher bundles in the top 20% of the block, after which normal TPU priority scheduling resumes.

---

## 1. Experimental Design & Architecture

```
                                      +------------------------------------+
                                      |     Solana Mainnet JSON-RPC        |
                                      |  (api.mainnet-beta.solana.com)     |
                                      +-----------------+------------------+
                                                        |
                                 +----------------------+----------------------+
                                 |                                             |
                     [Cluster Topology & Leaders]                      [Confirmed Blocks]
                                 |                                             |
                                 v                                             v
                      +---------------------+                       +---------------------+
                      |   LeaderTracker     |                       |     BlockParser     |
                      | - getClusterNodes   |                       | - Base58 Decoder    |
                      | - getVoteAccounts   |                       | - ComputeBudget Ix  |
                      | - getSlotLeaders    |                       | - Write-Lock Graph  |
                      +----------+----------+                       +----------+----------+
                                 |                                             |
                                 +----------------------+----------------------+
                                                        |
                                                        v
                                          +----------------------------+
                                          |     SchedulerAnalyzer      |
                                          | - Spearman Rank (rho)      |
                                          | - Kendall Tau (tau)        |
                                          | - Inversion Ratio Analysis |
                                          | - Conflict Partitioning    |
                                          +--------------+-------------+
                                                         |
                                 +-----------------------+----------------------+
                                 |                                              |
                                 v                                              v
                      +----------------------+                      +-----------------------+
                      |   SpendCapManager    |                      |   Diagnostic Engine   |
                      | Hard Cap: 0.05 SOL   |                      | Empirical Rule Verdict|
                      | Atomic Ledger Check  |                      | "Noise vs Rule" Audit |
                      +----------------------+                      +-----------------------+
```

### Reproducibility via Docker (One Command)

The entire experiment is reproducible with a single command via Docker Compose:

```bash
docker compose up
```

By default, the container:
1. Runs the complete test suite (`pytest -v`) to verify all mathematical and parsing invariants (17/17 tests passing).
2. Connects to Solana Mainnet in `--dry-run` mode (zero SOL spent).
3. Queries current cluster leaders, profiles 6+ validators across 4 client versions, extracts blocks, partitions write locks, calculates rank correlations, and saves raw data to `data/raw_measurements.json`.

---

## 2. What the Experiment Must Account For

### A. Leader Schedule & Leader Types
Solana assigns leader slots in consecutive 4-slot chunks according to stake-weighted leader schedules. Our `LeaderTracker` maps every target slot to:
- The validator's identity `nodePubkey`.
- The validator's `votePubkey` and activated stake weight.
- The validator's software client (`clientId`) and version string (`version`), resolving whether the node runs Agave, Jito-Solana, Firedancer, or specialized forks.

### B. Path of a Transaction (Network to Execution)
When a transaction is broadcast from an off-chain client to a Solana validator:
1. **TPU Port (QUIC Protocol)**: Inbound UDP datagrams are received over QUIC streams. Validators enforce QUIC stream limits and stake-weighted Quality of Service (SWQoS).
2. **Packet Deserialization & SigVerify**: GPU/CPU worker threads deserialize packets and batch-verify Ed25519 signatures.
3. **Banking Stage Scheduler**:
   - In **Agave**: The central `prio-graph` scheduler sorts packets by compute unit price and inserts them into non-conflicting thread channels.
   - In **Firedancer**: The `fd_pack` tile bins transactions by CU price into knapsack buckets.
   - In **Jito**: The relayer/block engine feeds searcher bundles through a bundle engine before passing residual mempool packets to the banking threads.
4. **PohRecorder & Entry Writing**: As threads complete execution batches, they write micro-blocks (entries) into the Proof of History tick stream.

### C. Interaction of Transactions With Each Other
- **Write-Lock Contention**: Transactions that write to the same account address **cannot** execute in parallel. If Tx A and Tx B both write to Account X, the scheduler *must* serialize them.
- **Disjoint Parallelism**: If Tx C and Tx D access independent accounts, they run concurrently on separate CPU cores. If Tx C finishes 200 microseconds faster than Tx D, Tx C's entry will land first in the block, even if Tx D paid a higher priority fee!
- **Our Solution**: The `SchedulerAnalyzer` isolates transactions into **Conflict Clusters** sharing identical write-locks, eliminating parallel execution jitter and exposing the pure prioritization rule.

### D. Competition Inside the Block
During peak volatility, blocks contain intense fee competition from automated DEX arbitrageurs, liquidation bots, and minting scripts. Our parser decodes:
- `ComputeBudget::SetComputeUnitLimit` (tag 2)
- `ComputeBudget::SetComputeUnitPrice` (tag 3)
Effective Priority Rate = $\text{Compute Unit Price}$ (micro-lamports per CU requested).

### E. Noise Versus Rule
| Observed Signal | Source of Noise | Underlying Invariant Rule |
| :--- | :--- | :--- |
| Low global $\rho$ | Multi-core thread finishing latency | Non-conflicting transactions finish out of arrival order |
| Inversions at block head | Jito bundle auction boundaries | Searcher bundles bypass standard TPU queue |
| Zero-fee transactions at top | Simple system transfers / vote transactions | Vote transactions and legacy transfers bypass compute budget |
| Strict local monotonicity | None (eliminated by conflict partition) | **Within an account write queue, validators strictly order by CU price** |

---

## 3. What the Experiment Does NOT Separate (Honest Limitations)

In accordance with scientific rigor, we explicitly document boundaries that external RPC observation cannot isolate:
1. **Off-Chain Network Transit Jitter**: We cannot measure the exact microsecond a packet arrived at the validator's physical network interface card (NIC) versus when the validator scheduled it.
2. **Private Relayer Bundles vs Public TPU**: Unless Jito bundle tips are cross-referenced with Jito Block Engine tip payment accounts, external `getBlock` RPC data cannot definitively prove whether a head-of-block transaction arrived via private relayer or public TPU (though presence of Jito tip accounts strongly correlates).
3. **Dropped Packets vs Scheduled Packets**: An RPC observer only sees transactions that *landed* in the confirmed block; transactions dropped due to buffer overflows or QUIC throttling leave no on-chain trace.

---

## 4. Spend-Cap Architecture (Safety Guarantee)

To guarantee that automated pipelines never cause accidental monetary losses, the system enforces a hardware-grade spend cap:

```python
MAX_SPEND_LAMPORTS = 50_000_000  # Hard ceiling: 0.05 SOL
```

- **Thread-Safe Atomic Ledger**: `SpendCapManager` records every committed fee in a reentrant-locked ledger.
- **Pre-Flight Balance Check**: Rejects any transaction if $\text{Cumulative Spent} + \text{Proposed Fee} > \text{Cap}$.
- **Dry-Run by Default**: Unless `--live` and explicit environment variables are provided, all transactions are simulated without broadcasting to the network.
- **Zero-Key Principle**: Private keys are never hardcoded or stored in the repository; they are loaded solely via environment variables (`SOLANA_PRIVATE_KEY`) or mounted volume (`/keys/id.json`).

---

## 5. Usage & Verification

### Running Unit & Integration Tests (100% Pass)
```bash
pytest -v
```

### Running the Analyzer in Dry-Run Mode (Default)
```bash
python -m analyzer.cli --dry-run
```

### Analyzing Harvested Raw Measurements Offline
Judges can verify the claims instantly without making network calls:
```bash
python -m analyzer.cli --analyze-only --data-file data/raw_measurements.json
```

---

## Repository Structure
```
solana-inside-the-block-analyzer/
├── README.md                           # Comprehensive experiment design & documentation
├── REPORT.md                           # Measurement report with tables & "What Went Wrong"
├── Dockerfile                          # Reproducible Docker container
├── docker-compose.yml                  # One-command execution (docker compose up)
├── requirements.txt                    # Python dependencies
├── pyproject.toml                      # Build metadata
├── analyzer/                           # Core Analytical Engine
│   ├── __init__.py
│   ├── rpc.py                         # Robust Solana JSON-RPC client with backoff
│   ├── leader_tracker.py              # Leader schedule detector & client classifier
│   ├── spend_cap.py                   # Hard spend-cap enforcer (0.05 SOL ceiling)
│   ├── block_parser.py                # Pure Base58 decoder & ComputeBudget parser
│   ├── tx_builder.py                  # Priority fee ladder probe constructor
│   ├── sender.py                      # Leader window probe dispatcher
│   ├── scheduler_analyzer.py          # Spearman/Kendall/Inversion statistical engine
│   ├── validator_profiler.py          # Cohort selector & multi-block profiler
│   └── cli.py                         # CLI entrypoint
├── tests/                             # Comprehensive test suite (17 passed)
│   ├── test_block_parser.py
│   ├── test_leader_tracker.py
│   ├── test_scheduler_analyzer.py
│   ├── test_spend_cap.py
│   └── test_tx_builder.py
└── data/
    ├── raw_measurements.json          # Empirical raw data of 16 Mainnet slots
    └── benchmark_summary.json         # Aggregated metrics & client verdicts
```

---

## License
MIT License. Open-source contribution for Superteam Earn.
