"""
idrc/erc20.py
=============
Pure-Python ERC-20 base implementation.

Mirrors the OpenZeppelin ERC20 contract faithfully:
  - balanceOf / totalSupply
  - transfer / transferFrom
  - approve / allowance
  - internal _mint / _burn / _transfer / _approve
  - _beforeTokenTransfer hook (overridden by IDRCToken)
  - EIP-2612 Permit (off-chain approval via ECDSA signatures)

Token amounts are stored as raw integers (18 decimal places in practice).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .exceptions import (
    InsufficientAllowanceError,
    InsufficientBalanceError,
    PermitError,
    PermitExpiredError,
    ZeroAddressError,
    ZeroAmountError,
)

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


# ─── Events (equivalent to Solidity events) ──────────────────────────────────

@dataclass
class TransferEvent:
    sender: str
    recipient: str
    amount: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return (
            f"[{self.timestamp.isoformat()}] Transfer "
            f"from={self.sender} to={self.recipient} amount={self.amount}"
        )


@dataclass
class ApprovalEvent:
    owner: str
    spender: str
    amount: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return (
            f"[{self.timestamp.isoformat()}] Approval "
            f"owner={self.owner} spender={self.spender} amount={self.amount}"
        )


# ─── ERC-20 Base ─────────────────────────────────────────────────────────────

class ERC20Base:
    """
    Base ERC-20 implementation (stateful Python simulation).

    Stores balances and allowances in plain dicts. All integer arithmetic is
    exact (no floating point), matching Solidity semantics.
    """

    DECIMALS: int = 18

    def __init__(self, name: str, symbol: str) -> None:
        self._name: str = name
        self._symbol: str = symbol
        self._total_supply: int = 0
        self._balances: dict[str, int] = {}
        self._allowances: dict[str, dict[str, int]] = {}
        self._event_log: list = []

        # EIP-2612 permit nonces  (owner → nonce)
        self._permit_nonces: dict[str, int] = {}
        # Simulated "domain separator" — in real EIP-712 this is a hash of
        # chain-id, contract address, etc.  Here we use a deterministic value.
        self._domain_separator: str = hashlib.sha256(
            f"EIP712Domain:{name}:IDRC:1".encode()
        ).hexdigest()

    # ── ERC-20 View Functions ─────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def decimals(self) -> int:
        return self.DECIMALS

    @property
    def total_supply(self) -> int:
        return self._total_supply

    def balance_of(self, account: str) -> int:
        return self._balances.get(account, 0)

    def allowance(self, owner: str, spender: str) -> int:
        return self._allowances.get(owner, {}).get(spender, 0)

    def nonce_of(self, owner: str) -> int:
        """EIP-2612: current permit nonce for `owner`."""
        return self._permit_nonces.get(owner, 0)

    @property
    def domain_separator(self) -> str:
        return self._domain_separator

    # ── ERC-20 State-Changing Functions ───────────────────────────────────────

    def transfer(self, recipient: str, amount: int, *, caller: str) -> bool:
        """Transfer `amount` tokens from `caller` to `recipient`."""
        self._transfer(caller, recipient, amount)
        return True

    def approve(self, spender: str, amount: int, *, caller: str) -> bool:
        """Set allowance of `spender` to `amount` on behalf of `caller`."""
        self._approve(caller, spender, amount)
        return True

    def transfer_from(
        self, sender: str, recipient: str, amount: int, *, caller: str
    ) -> bool:
        """
        Transfer `amount` from `sender` to `recipient` using caller's allowance.
        Reduces allowance by `amount` (no reduction for type(uint256).max).
        """
        current = self.allowance(sender, caller)
        # Unlimited allowance pattern (equivalent to type(uint256).max)
        if current != (2**256 - 1):
            if current < amount:
                raise InsufficientAllowanceError(caller, current, amount)
            self._approve(sender, caller, current - amount)
        self._transfer(sender, recipient, amount)
        return True

    def increase_allowance(self, spender: str, added: int, *, caller: str) -> bool:
        """Increase allowance by `added`."""
        current = self.allowance(caller, spender)
        self._approve(caller, spender, current + added)
        return True

    def decrease_allowance(self, spender: str, subtracted: int, *, caller: str) -> bool:
        """Decrease allowance by `subtracted` (cannot go below 0)."""
        current = self.allowance(caller, spender)
        if current < subtracted:
            raise InsufficientAllowanceError(caller, current, subtracted)
        self._approve(caller, spender, current - subtracted)
        return True

    # ── EIP-2612 Permit ───────────────────────────────────────────────────────

    def permit(
        self,
        owner: str,
        spender: str,
        value: int,
        deadline: int,
        signature: str,  # In Python: HMAC-SHA256 of permit digest as hex
        *,
        current_time: int | None = None,
    ) -> None:
        """
        Approve `spender` to spend `value` on behalf of `owner` using an
        off-chain signature (EIP-2612).

        Python simulation: signature is HMAC-SHA256(secret_key=owner,
        msg=permit_digest). In production Solidity, this is ECDSA over EIP-712.
        """
        now = current_time if current_time is not None else int(time.time())
        if now > deadline:
            raise PermitExpiredError()

        nonce = self._permit_nonces.get(owner, 0)
        digest = self._permit_digest(owner, spender, value, nonce, deadline)
        expected_sig = hmac.new(owner.encode(), digest.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            raise PermitError()

        self._permit_nonces[owner] = nonce + 1
        self._approve(owner, spender, value)

    def generate_permit_signature(
        self, owner: str, spender: str, value: int, deadline: int
    ) -> str:
        """Helper used in tests: generate a valid permit signature."""
        nonce = self._permit_nonces.get(owner, 0)
        digest = self._permit_digest(owner, spender, value, nonce, deadline)
        return hmac.new(owner.encode(), digest.encode(), hashlib.sha256).hexdigest()

    def _permit_digest(
        self, owner: str, spender: str, value: int, nonce: int, deadline: int
    ) -> str:
        data = f"{self._domain_separator}:{owner}:{spender}:{value}:{nonce}:{deadline}"
        return hashlib.sha256(data.encode()).hexdigest()

    # ── Internal Hooks ────────────────────────────────────────────────────────

    def _before_token_transfer(self, sender: str, recipient: str, amount: int) -> None:
        """
        Hook called before every transfer / mint / burn.
        Overridden by IDRCToken to enforce pause + blacklist checks.
        """

    def _after_token_transfer(self, sender: str, recipient: str, amount: int) -> None:
        """Hook called after every transfer / mint / burn."""

    # ── Internal State Mutations ──────────────────────────────────────────────

    def _transfer(self, sender: str, recipient: str, amount: int) -> None:
        if sender == ZERO_ADDRESS:
            raise ZeroAddressError("transfer from zero address")
        if recipient == ZERO_ADDRESS:
            raise ZeroAddressError("transfer to zero address")
        if amount <= 0:
            raise ZeroAmountError()

        self._before_token_transfer(sender, recipient, amount)

        balance = self._balances.get(sender, 0)
        if balance < amount:
            raise InsufficientBalanceError(sender, balance, amount)

        self._balances[sender] = balance - amount
        self._balances[recipient] = self._balances.get(recipient, 0) + amount

        event = TransferEvent(sender=sender, recipient=recipient, amount=amount)
        self._event_log.append(event)

        self._after_token_transfer(sender, recipient, amount)

    def _mint(self, account: str, amount: int) -> None:
        if account == ZERO_ADDRESS:
            raise ZeroAddressError("mint to zero address")
        if amount <= 0:
            raise ZeroAmountError()

        self._before_token_transfer(ZERO_ADDRESS, account, amount)

        self._total_supply += amount
        self._balances[account] = self._balances.get(account, 0) + amount

        event = TransferEvent(sender=ZERO_ADDRESS, recipient=account, amount=amount)
        self._event_log.append(event)

        self._after_token_transfer(ZERO_ADDRESS, account, amount)

    def _burn(self, account: str, amount: int) -> None:
        if account == ZERO_ADDRESS:
            raise ZeroAddressError("burn from zero address")
        if amount <= 0:
            raise ZeroAmountError()

        self._before_token_transfer(account, ZERO_ADDRESS, amount)

        balance = self._balances.get(account, 0)
        if balance < amount:
            raise InsufficientBalanceError(account, balance, amount)

        self._balances[account] = balance - amount
        self._total_supply -= amount

        event = TransferEvent(sender=account, recipient=ZERO_ADDRESS, amount=amount)
        self._event_log.append(event)

        self._after_token_transfer(account, ZERO_ADDRESS, amount)

    def _approve(self, owner: str, spender: str, amount: int) -> None:
        if owner == ZERO_ADDRESS:
            raise ZeroAddressError("approve from zero address")
        if spender == ZERO_ADDRESS:
            raise ZeroAddressError("approve to zero address")

        if owner not in self._allowances:
            self._allowances[owner] = {}
        self._allowances[owner][spender] = amount

        event = ApprovalEvent(owner=owner, spender=spender, amount=amount)
        self._event_log.append(event)

    # ── Utilities ─────────────────────────────────────────────────────────────

    @property
    def events(self) -> list:
        return list(self._event_log)

    def format_amount(self, raw: int) -> str:
        """Pretty-print a raw integer with 18 decimal places."""
        whole, frac = divmod(abs(raw), 10**self.DECIMALS)
        sign = "-" if raw < 0 else ""
        return f"{sign}{whole:,}.{frac:018d} {self._symbol}"

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"name={self._name!r}, symbol={self._symbol!r}, "
            f"total_supply={self._total_supply})"
        )
