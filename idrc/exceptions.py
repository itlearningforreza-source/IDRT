"""
idrc/exceptions.py
==================
Custom exceptions that mirror Solidity `require` / `revert` semantics.
Every exception carries a `reason` string identical to the on-chain revert message.
"""


class IDRCError(Exception):
    """Base exception for all IDRC contract errors."""

    def __init__(self, reason: str = ""):
        self.reason = reason
        super().__init__(reason)


# ── Access Control ──────────────────────────────────────────────────────────

class AccessControlError(IDRCError):
    """Caller does not hold the required role."""


class MissingRoleError(AccessControlError):
    def __init__(self, account: str, role: str):
        super().__init__(f"AccessControl: account {account} is missing role {role}")


# ── ERC-20 / Token ──────────────────────────────────────────────────────────

class ERC20Error(IDRCError):
    """General ERC-20 rule violation."""


class InsufficientBalanceError(ERC20Error):
    def __init__(self, account: str, balance: int, needed: int):
        super().__init__(
            f"ERC20: transfer amount {needed} exceeds balance {balance} of {account}"
        )


class InsufficientAllowanceError(ERC20Error):
    def __init__(self, spender: str, allowance: int, needed: int):
        super().__init__(
            f"ERC20: transfer amount {needed} exceeds allowance {allowance} for {spender}"
        )


class ZeroAddressError(ERC20Error):
    def __init__(self, context: str = ""):
        super().__init__(f"IDRC: zero address{' — ' + context if context else ''}")


class ZeroAmountError(ERC20Error):
    def __init__(self):
        super().__init__("IDRC: amount must be > 0")


class SupplyCapExceededError(ERC20Error):
    def __init__(self, requested: int, cap: int):
        super().__init__(f"IDRC: mint amount exceeds supply cap (requested: {requested}, cap: {cap})")


# ── Pausable ─────────────────────────────────────────────────────────────────

class PausedError(IDRCError):
    def __init__(self):
        super().__init__("Pausable: paused")


class NotPausedError(IDRCError):
    def __init__(self):
        super().__init__("Pausable: not paused")


# ── Blacklist ────────────────────────────────────────────────────────────────

class BlacklistedError(IDRCError):
    def __init__(self, account: str):
        super().__init__(f"IDRC: blacklisted account {account}")


class AlreadyBlacklistedError(IDRCError):
    def __init__(self, account: str):
        super().__init__(f"IDRC: {account} already blacklisted")


class NotBlacklistedError(IDRCError):
    def __init__(self, account: str):
        super().__init__(f"IDRC: {account} is not blacklisted")


# ── Initialiser ──────────────────────────────────────────────────────────────

class AlreadyInitializedError(IDRCError):
    def __init__(self):
        super().__init__("Initializable: contract is already initialized")


# ── Proxy / Upgrade ──────────────────────────────────────────────────────────

class UpgradeError(IDRCError):
    """Generic upgrade failure."""


class ImplementationNotFoundError(UpgradeError):
    def __init__(self, version: int):
        super().__init__(f"Proxy: implementation for version {version} not registered")


# ── Permit (EIP-2612) ────────────────────────────────────────────────────────

class PermitError(IDRCError):
    """Permit signature verification failed."""

    def __init__(self, reason: str = "ERC20Permit: invalid signature"):
        super().__init__(reason)


class PermitExpiredError(PermitError):
    def __init__(self):
        super().__init__("ERC20Permit: expired deadline")


# ── Reserve ──────────────────────────────────────────────────────────────────

class ReserveError(IDRCError):
    """Reserve-related errors."""
