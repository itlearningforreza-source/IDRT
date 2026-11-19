// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IBridgeVault} from "../interfaces/IBridge.sol";
import {IDRCToken} from "../token/IDRCToken.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {Context} from "@openzeppelin/contracts/utils/Context.sol";

/**
 * @title BridgeVault
 * @notice Vault for locking IDRC tokens during cross-chain transfers
 * @dev Implements burn-and-mint bridge model: burns on source, mints on destination
 */
contract BridgeVault is IBridgeVault, AccessControl, ReentrancyGuard, Pausable {
    function _msgSender() internal view override(Context) returns (address) {
        return msg.sender;
    }
    // ============================================================
    // Constants
    // ============================================================
    bytes32 public constant RELAYER_ROLE = keccak256("RELAYER_ROLE");

    // ============================================================
    // State Variables
    // ============================================================
    uint256 public immutable chainId;
    address public relayer; // Changed from immutable to mutable for setRelayer
    uint256 private _nonce;
    mapping(uint256 => uint256) private _lockedAmounts;
    mapping(uint256 => bool) private _processedNonces;
    uint256 private _totalLocked;

    // Events (defined in interface)

    // Custom Errors
    error ZeroAddress();
    error SameChain(uint256 chainId);
    error ZeroAmount();
    error NonceNotFound(uint256 nonce);
    error NonceAlreadyProcessed(uint256 nonce);
    error OnlyRelayerAllowed();
    error TransferFailed();

    // ============================================================
    // Constructor
    // ============================================================
    constructor(uint256 chainId_, address relayer_) {
        require(chainId_ != 0, "BridgeVault: zero chain ID");
        require(relayer_ != address(0), "BridgeVault: zero relayer address");

        chainId = chainId_;
        relayer = relayer_;

        _grantRole(DEFAULT_ADMIN_ROLE, relayer_); // relayer is initial admin
        _grantRole(RELAYER_ROLE, relayer_);
    }

    // ============================================================
    // Lock (Burn on Source Chain)
    // ============================================================

    function lock(
        address token,
        address sender,
        address recipient,
        uint256 amount,
        uint256 dstChainId
    ) external override onlyRole(RELAYER_ROLE) nonReentrant whenNotPaused returns (uint256 bridgeNonce) {
        if (sender == address(0)) revert ZeroAddress();
        if (amount == 0) revert ZeroAmount();
        if (dstChainId == chainId) revert SameChain(dstChainId);

        // Burn tokens from sender on source chain
        IDRCToken(token).issuerBurn(sender, amount);

        // Record lock
        _nonce++;
        bridgeNonce = _nonce;
        _lockedAmounts[bridgeNonce] = amount;
        _totalLocked += amount;

        emit TokensLocked(bridgeNonce, sender, recipient, amount, dstChainId);
    }

    // ============================================================
    // Release (Mint on Source Chain - for reverse bridge)
    // ============================================================

    function release(
        address token,
        uint256 bridgeNonce,
        address recipient
    ) external override onlyRole(RELAYER_ROLE) nonReentrant whenNotPaused {
        if (recipient == address(0)) revert ZeroAddress();
        if (_lockedAmounts[bridgeNonce] == 0) revert NonceNotFound(bridgeNonce);
        if (_processedNonces[bridgeNonce]) revert NonceAlreadyProcessed(bridgeNonce);

        uint256 amount = _lockedAmounts[bridgeNonce];
        _processedNonces[bridgeNonce] = true;
        _totalLocked -= amount;

        // Mint tokens back to recipient on source chain
        IDRCToken(token).mint(recipient, amount);

        emit TokensReleased(bridgeNonce, recipient, amount);
    }

    // ============================================================
    // View Functions
    // ============================================================
    // Note: chainId() getter is auto-generated from public immutable variable

    function totalLocked() external view override returns (uint256) {
        return _totalLocked;
    }

    function isNonceProcessed(uint256 bridgeNonce) external view override returns (bool) {
        return _processedNonces[bridgeNonce];
    }

    function lockedAmount(uint256 bridgeNonce) external view returns (uint256) {
        return _lockedAmounts[bridgeNonce];
    }

    // ============================================================
    // Admin Functions
    // ============================================================

    function setRelayer(address newRelayer) external onlyRole(DEFAULT_ADMIN_ROLE) {
        if (newRelayer == address(0)) revert ZeroAddress();
        _revokeRole(RELAYER_ROLE, relayer);
        _grantRole(RELAYER_ROLE, newRelayer);
        relayer = newRelayer;
    }

    function pause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _pause();
    }

    function unpause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _unpause();
    }
}
