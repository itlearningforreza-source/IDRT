"""
idrc/bridge.py
==============
Cross-chain bridge stub for IDRC (Section 10.1).

Simulates the lock-and-mint / burn-and-release bridge pattern used to
move IDRC between EVM chains (Ethereum ↔ Polygon ↔ BSC).

Architecture
------------
  Source chain: User locks IDRC in BridgeVault → BridgeRelayer picks up
                the Lock event → mints equivalent tokens on dest chain.

  Dest chain:   User initiates BurnForBridge → BridgeRelayer burns on
                dest chain → releases locked IDRC on source chain.

In production this is implemented by a trust-minimised relayer network
(e.g. Multichain, Celer, LayerZero). This module provides a Python
simulation suitable for integration tests.

Classes
-------
  ChainID         - Enum of supported networks
  BridgeLockEvent - Emitted when tokens are locked on source chain
  BridgeMintEvent - Emitted when tokens are minted on destination chain
  BridgeVault     - Source-chain vault that holds locked tokens
  BridgeRelayer   - Off-chain relayer that processes cross-chain messages
  IDRCBridge      - High-level bridge coordinator
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

# ─── Chain IDs ────────────────────────────────────────────────────────────────

class ChainID(Enum):
    ETHEREUM = 1
    POLYGON  = 137
    BSC      = 56
    ARBITRUM = 42161
    OPTIMISM = 10


CHAIN_NAMES = {v: v.name for v in ChainID}


# ─── Bridge Events ────────────────────────────────────────────────────────────

@dataclass
class BridgeLockEvent:
    """Emitted on source chain when IDRC is locked in the vault."""
    bridge_nonce: int
    sender: str
    recipient: str      # address on destination chain
    amount: int
    src_chain: ChainID
    dst_chain: ChainID
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return (
            f"[BridgeLock #{self.bridge_nonce}] "
            f"{self.amount / 10**18:.6f} IDRC "
            f"{self.src_chain.name} → {self.dst_chain.name} "
            f"sender={self.sender} recipient={self.recipient}"
        )


@dataclass
class BridgeMintEvent:
    """Emitted on destination chain when bridged IDRC is minted."""
    bridge_nonce: int
    recipient: str
    amount: int
    src_chain: ChainID
    dst_chain: ChainID
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return (
            f"[BridgeMint #{self.bridge_nonce}] "
            f"{self.amount / 10**18:.6f} IDRC "
            f"on {self.dst_chain.name} to {self.recipient}"
        )


@dataclass
class BridgeReleaseEvent:
    """Emitted on source chain when locked IDRC is released back to user."""
    bridge_nonce: int
    recipient: str
    amount: int
    src_chain: ChainID
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return (
            f"[BridgeRelease #{self.bridge_nonce}] "
            f"{self.amount / 10**18:.6f} IDRC "
            f"on {self.src_chain.name} to {self.recipient}"
        )


# ─── BridgeVault ──────────────────────────────────────────────────────────────

class BridgeVault:
    """
    Source-chain vault that locks IDRC during cross-chain transfers.

    In Solidity this would hold an ERC-20 balance and emit events
    picked up by the relayer. Here we simulate the locking mechanism
    by reducing the token balance of the user and storing the locked
    amount in the vault's ledger.
    """

    def __init__(self, chain: ChainID, relayer_address: str) -> None:
        self.chain = chain
        self._relayer_address = relayer_address
        self._locked: dict[int, int] = {}       # bridge_nonce → amount
        self._nonce: int = 0
        self._event_log: list = []

    def lock(
        self,
        token,
        sender: str,
        recipient: str,
        amount: int,
        dst_chain: ChainID,
    ) -> BridgeLockEvent:
        """
        Lock `amount` IDRC from `sender` in the vault.
        Token is burned on source chain (burn-and-mint model) or
        locked (lock-and-mint model). Here we use lock-and-mint.

        Parameters
        ----------
        token     : IDRCToken (or _TokenHandle) on the source chain
        sender    : Address initiating the bridge transfer
        recipient : Address on the destination chain to receive tokens
        amount    : Amount of IDRC to bridge (raw units)
        dst_chain : Target chain ID
        """
        if amount <= 0:
            raise ValueError("Bridge: amount must be > 0")
        if dst_chain == self.chain:
            raise ValueError("Bridge: source and destination chains must differ")

        # Lock tokens by burning them on source (burn-and-mint pattern)
        token.burn(amount, caller=sender)

        self._nonce += 1
        self._locked[self._nonce] = amount

        event = BridgeLockEvent(
            bridge_nonce=self._nonce,
            sender=sender,
            recipient=recipient,
            amount=amount,
            src_chain=self.chain,
            dst_chain=dst_chain,
        )
        self._event_log.append(event)
        return event

    def release(self, token, bridge_nonce: int, recipient: str) -> BridgeReleaseEvent:
        """
        Release locked IDRC back to the user (used in reverse-bridge).
        Called by the relayer after burn on destination chain is confirmed.
        """
        if bridge_nonce not in self._locked:
            raise ValueError(f"Bridge: nonce {bridge_nonce} not found in vault")

        amount = self._locked.pop(bridge_nonce)
        # Re-mint released tokens to recipient
        token.mint(recipient, amount, caller=self._relayer_address)

        event = BridgeReleaseEvent(
            bridge_nonce=bridge_nonce,
            recipient=recipient,
            amount=amount,
            src_chain=self.chain,
        )
        self._event_log.append(event)
        return event

    @property
    def total_locked(self) -> int:
        return sum(self._locked.values())

    @property
    def events(self) -> list:
        return list(self._event_log)

    def __repr__(self) -> str:
        return (
            f"BridgeVault(chain={self.chain.name}, "
            f"total_locked={self.total_locked / 10**18:.6f} IDRC, "
            f"pending_nonces={len(self._locked)})"
        )


# ─── BridgeRelayer ────────────────────────────────────────────────────────────

class BridgeRelayer:
    """
    Off-chain relayer that listens to BridgeLockEvents on the source chain
    and triggers minting on the destination chain.

    In production: a decentralised relayer network (LayerZero, Celer, Axelar)
    with cryptographic attestation. Here we simulate the relay logic.
    """

    def __init__(self, relayer_address: str) -> None:
        self._address = relayer_address
        self._processed: set = set()   # processed bridge nonces (dedup)
        self._event_log: list = []

    def relay(
        self,
        lock_event: BridgeLockEvent,
        dst_token,                 # IDRCToken on destination chain
    ) -> BridgeMintEvent:
        """
        Process a BridgeLockEvent and mint equivalent tokens on dst chain.

        Idempotency: replaying the same nonce raises an error (replay protection).
        """
        nonce = (lock_event.src_chain, lock_event.bridge_nonce)
        if nonce in self._processed:
            raise ValueError(
                f"Bridge: relay already processed nonce {lock_event.bridge_nonce} "
                f"from {lock_event.src_chain.name}"
            )

        # Mint on destination chain
        dst_token.mint(
            lock_event.recipient,
            lock_event.amount,
            caller=self._address,
        )

        self._processed.add(nonce)

        mint_event = BridgeMintEvent(
            bridge_nonce=lock_event.bridge_nonce,
            recipient=lock_event.recipient,
            amount=lock_event.amount,
            src_chain=lock_event.src_chain,
            dst_chain=lock_event.dst_chain,
        )
        self._event_log.append(mint_event)
        return mint_event

    @property
    def events(self) -> list:
        return list(self._event_log)

    def __repr__(self) -> str:
        return (
            f"BridgeRelayer(address={self._address!r}, "
            f"processed={len(self._processed)})"
        )


# ─── IDRCBridge ───────────────────────────────────────────────────────────────

class IDRCBridge:
    """
    High-level bridge coordinator that wires together vaults and relayer.

    Supports the burn-and-mint cross-chain transfer model:
      1. User calls bridge.transfer(...) on the source chain.
      2. Source vault burns user's IDRC and emits BridgeLockEvent.
      3. Relayer picks up the event and calls bridge.complete_transfer(...)
         on the destination chain, minting equivalent IDRC.

    Usage
    -----
        bridge = IDRCBridge(relayer_address="0xRelayer")
        bridge.register_chain(ChainID.ETHEREUM, eth_vault, eth_token)
        bridge.register_chain(ChainID.POLYGON,  poly_vault, poly_token)

        # User bridges 1000 IDRC from Ethereum to Polygon
        lock_ev = bridge.transfer(
            src_chain=ChainID.ETHEREUM,
            dst_chain=ChainID.POLYGON,
            sender="0xUser",
            recipient="0xUser",
            amount=1000 * 10**18,
        )
        # Relayer processes the lock event
        bridge.complete_transfer(lock_ev)
    """

    def __init__(self, relayer_address: str) -> None:
        self._relayer = BridgeRelayer(relayer_address)
        # chain → (vault, token)
        self._chains: dict[ChainID, tuple] = {}

    def register_chain(
        self, chain: ChainID, vault: BridgeVault, token
    ) -> None:
        """Register a chain's vault and token contract with the bridge."""
        self._chains[chain] = (vault, token)

    def transfer(
        self,
        src_chain: ChainID,
        dst_chain: ChainID,
        sender: str,
        recipient: str,
        amount: int,
    ) -> BridgeLockEvent:
        """
        Initiate a cross-chain transfer.
        Burns tokens on src_chain and returns a BridgeLockEvent for the relayer.
        """
        if src_chain not in self._chains:
            raise ValueError(f"Bridge: source chain {src_chain.name} not registered")
        if dst_chain not in self._chains:
            raise ValueError(f"Bridge: destination chain {dst_chain.name} not registered")

        src_vault, src_token = self._chains[src_chain]
        return src_vault.lock(src_token, sender, recipient, amount, dst_chain)

    def complete_transfer(self, lock_event: BridgeLockEvent) -> BridgeMintEvent:
        """
        Relayer calls this after observing a BridgeLockEvent.
        Mints equivalent IDRC on the destination chain.
        """
        dst_chain = lock_event.dst_chain
        if dst_chain not in self._chains:
            raise ValueError(f"Bridge: destination chain {dst_chain.name} not registered")

        _, dst_token = self._chains[dst_chain]
        return self._relayer.relay(lock_event, dst_token)

    def print_status(self) -> None:
        """Print bridge status across all registered chains."""
        print(f"\n{'─'*55}")
        print("  IDRC Cross-Chain Bridge Status")
        print(f"{'─'*55}")
        for chain, (vault, token) in self._chains.items():
            supply = token.total_supply
            locked = vault.total_locked
            print(f"  {chain.name:<12}  supply={supply / 10**18:>18,.6f} IDRC")
            print(f"  {'':12}  locked={locked / 10**18:>18,.6f} IDRC")
        print(f"  Relayed txs: {len(self._relayer._processed)}")
        print(f"{'─'*55}\n")

    @property
    def relayer(self) -> BridgeRelayer:
        return self._relayer
