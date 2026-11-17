"""
IDRC — IDR Coin Stablecoin Package
===================================
Python simulation of the IDRC ERC-20-equivalent stablecoin smart contract.

IDRC is a fiat-collateralised stablecoin pegged 1:1 to the Indonesian Rupiah (IDR),
built to the ERC-20 / EIP-2612 standard with UUPS upgradeability, role-based access
control, blacklist, pause, proof-of-reserve, monitoring, and cross-chain bridge support.

Public API
----------
    from idrc import IDRCToken, IDRCReserve, IDRCMonitor, IDRCBridge
    from idrc import deploy_idrc, upgrade_idrc, verify_deployment
    from idrc import MultisigWallet, UUPSProxy, ProxyAdmin
    from idrc.access_control import MINTER_ROLE, BURNER_ROLE, PAUSER_ROLE
    from idrc.bridge import ChainID

See https://github.com/idrc-stablecoin/idrc-python for full documentation.
"""

__version__   = "1.0.0"
__author__    = "IDRC Development Team"
__license__   = "MIT"
__copyright__ = "Copyright 2026 IDRC Development Team"
__url__       = "https://github.com/idrc-stablecoin/idrc-python"

# ── Core token ───────────────────────────────────────────────────────────────
from .bridge import BridgeRelayer, BridgeVault, ChainID, IDRCBridge

# ── Operations ───────────────────────────────────────────────────────────────
from .deploy import DeploymentResult, deploy_idrc, upgrade_idrc, verify_deployment
from .erc20 import ZERO_ADDRESS, ERC20Base

# ── Exceptions (re-exported for convenience) ─────────────────────────────────
from .exceptions import (
    AccessControlError,
    AlreadyBlacklistedError,
    AlreadyInitializedError,
    BlacklistedError,
    ERC20Error,
    IDRCError,
    InsufficientAllowanceError,
    InsufficientBalanceError,
    MissingRoleError,
    NotBlacklistedError,
    NotPausedError,
    PausedError,
    PermitError,
    PermitExpiredError,
    ReserveError,
    UpgradeError,
    ZeroAddressError,
    ZeroAmountError,
)
from .monitor import AlertEvent, IDRCMonitor
from .multisig import MultisigWallet

# ── Infrastructure ───────────────────────────────────────────────────────────
from .proxy import ProxyAdmin, UUPSProxy
from .reserve import IDRCReserve
from .token import IDRCToken

__all__ = [
    "ZERO_ADDRESS",
    "AccessControlError",
    "AlertEvent",
    "AlreadyBlacklistedError",
    "AlreadyInitializedError",
    "BlacklistedError",
    "BridgeRelayer",
    "BridgeVault",
    "ChainID",
    "DeploymentResult",
    "ERC20Base",
    "ERC20Error",
    # Bridge
    "IDRCBridge",
    # Exceptions
    "IDRCError",
    # Monitor
    "IDRCMonitor",
    # Reserve
    "IDRCReserve",
    # Token
    "IDRCToken",
    "InsufficientAllowanceError",
    "InsufficientBalanceError",
    "MissingRoleError",
    "MultisigWallet",
    "NotBlacklistedError",
    "NotPausedError",
    "PausedError",
    "PermitError",
    "PermitExpiredError",
    "ProxyAdmin",
    "ReserveError",
    # Proxy & Multisig
    "UUPSProxy",
    "UpgradeError",
    "ZeroAddressError",
    "ZeroAmountError",
    # Deploy
    "deploy_idrc",
    "upgrade_idrc",
    "verify_deployment",
]
