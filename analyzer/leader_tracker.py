"""
Leader Tracker & Validator Client Classifier.
Maps Solana leader schedules to validator identities, software clients, and versions.
Identifies upcoming leader windows for targeted probe injections.
"""

from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field
import logging
import re
from .rpc import SolanaRpcClient

logger = logging.getLogger("solana_analyzer.leader_tracker")


@dataclass
class ValidatorNodeInfo:
    """Detailed metadata for a validator node."""
    node_pubkey: str
    vote_pubkey: Optional[str] = None
    client_family: str = "Unknown"  # Agave, Jito, Firedancer, Rakurai, Other
    client_raw_id: str = ""
    version: str = ""
    gossip: Optional[str] = None
    tpu_quic: Optional[str] = None
    activated_stake: int = 0
    commission: int = 0


def classify_client(client_id: Optional[str], version: Optional[str]) -> str:
    """
    Classifies validator into major client architectures.
    Agave: Reference client (formerly Solana Labs).
    Jito: Jito-Solana bundle client.
    Firedancer: Jump Crypto Firedancer / Frankendancer / FireBAM.
    Rakurai: Specialized low-latency client.
    """
    cid = (client_id or "").lower()
    ver = (version or "").lower()

    if "firedancer" in cid or "firebam" in cid or "frankendancer" in cid or "jump" in cid or "26.10" in ver or "-fd" in ver or "0.1.1" in ver:
        return "Firedancer"
    elif "jito" in cid or "jito" in ver:
        return "Jito"
    elif "rakurai" in cid:
        return "Rakurai"
    elif "agave" in cid or "solanalabs" in cid or cid == "":
        return "Agave"
    return "Other"


class LeaderTracker:
    """Tracks cluster topology, leader windows, and client versions."""

    def __init__(self, rpc_client: Optional[SolanaRpcClient] = None, rpc: Optional[SolanaRpcClient] = None):
        self.rpc = rpc_client or rpc
        if not self.rpc:
            raise ValueError("SolanaRpcClient must be provided to LeaderTracker")
        self._nodes: Dict[str, ValidatorNodeInfo] = {}
        self._vote_to_node: Dict[str, str] = {}
        self._initialized = False

    def refresh_cluster_nodes(self) -> None:
        """Fetches and caches cluster nodes and vote accounts."""
        logger.info("Fetching cluster nodes from RPC...")
        raw_nodes = self.rpc.get_cluster_nodes()
        vote_data = self.rpc.get_vote_accounts()

        # Map vote accounts
        vote_stake_map: Dict[str, Tuple[str, int, int]] = {}
        for va in vote_data.get("current", []):
            npk = va.get("nodePubkey", "")
            vpk = va.get("votePubkey", "")
            stake = va.get("activatedStake", 0)
            comm = va.get("commission", 0)
            if npk and vpk:
                vote_stake_map[npk] = (vpk, stake, comm)
                self._vote_to_node[vpk] = npk

        nodes_map: Dict[str, ValidatorNodeInfo] = {}
        for n in raw_nodes:
            npk = n.get("pubkey")
            if not npk:
                continue
            raw_cid = n.get("clientId") or ""
            ver = n.get("version") or ""
            family = classify_client(raw_cid, ver)
            
            vpk, stake, comm = vote_stake_map.get(npk, (None, 0, 0))

            nodes_map[npk] = ValidatorNodeInfo(
                node_pubkey=npk,
                vote_pubkey=vpk,
                client_family=family,
                client_raw_id=raw_cid,
                version=ver,
                gossip=n.get("gossip"),
                tpu_quic=n.get("tpuQuic"),
                activated_stake=stake,
                commission=comm
            )

        self._nodes = nodes_map
        self._initialized = True
        logger.info("Cluster refreshed: %d nodes, %d vote mappings cached.", len(self._nodes), len(self._vote_to_node))

    def get_node_info(self, pubkey: str) -> Optional[ValidatorNodeInfo]:
        """Resolves node info by nodePubkey or votePubkey."""
        if not self._initialized:
            self.refresh_cluster_nodes()

        if pubkey in self._nodes:
            return self._nodes[pubkey]
        if pubkey in self._vote_to_node:
            node_pk = self._vote_to_node[pubkey]
            return self._nodes.get(node_pk)
        return None

    def find_validators_by_family(self, min_stake: int = 1_000_000_000) -> Dict[str, List[ValidatorNodeInfo]]:
        """Groups active validators with stake by client family."""
        if not self._initialized:
            self.refresh_cluster_nodes()

        families: Dict[str, List[ValidatorNodeInfo]] = {
            "Agave": [],
            "Jito": [],
            "Firedancer": [],
            "Rakurai": [],
            "Other": []
        }

        for n in self._nodes.values():
            if n.activated_stake >= min_stake:
                fam = n.client_family if n.client_family in families else "Other"
                families[fam].append(n)

        # Sort each family by activated stake descending
        for fam in families:
            families[fam].sort(key=lambda x: -x.activated_stake)

        return families

    def get_recent_slot_leaders(self, start_slot: int, limit: int = 100) -> List[Tuple[int, str, ValidatorNodeInfo]]:
        """
        Retrieves recent slot leaders with attached node info.
        Returns list of (slot, leader_pubkey, ValidatorNodeInfo).
        """
        if not self._initialized:
            self.refresh_cluster_nodes()

        leaders = self.rpc.get_slot_leaders(start_slot, limit)
        result: List[Tuple[int, str, ValidatorNodeInfo]] = []

        for i, l_pk in enumerate(leaders):
            curr_slot = start_slot + i
            info = self.get_node_info(l_pk) or ValidatorNodeInfo(
                node_pubkey=l_pk,
                client_family="Unknown",
                version="Unknown"
            )
            result.append((curr_slot, l_pk, info))

        return result
