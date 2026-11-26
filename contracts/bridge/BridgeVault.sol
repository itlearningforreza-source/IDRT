// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IBridgeVault} from "../interfaces/IBridge.sol";
import {IERC20} from "../interfaces/IERC20.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {Context} from "@openzeppelin/contracts/utils/Context.sol";

/**
 * @title BridgeVault
 * @notice Allowance-based source-chain vault for IDRC cross-chain transfers (burn-and-mint model)
 * @dev Redesign (Security Audit 4.0):
 *  - lock() now moves tokens via IERC20.transferFrom(msg.sender, vault, amount).
 *    A relayer NEVER has authority to burn tokens from arbitrary user addresses;
 *    the user must approve the vault and the source funds must be in the vault.
 *  - Every source-side action is recorded with a full bridge message struct.
 */
contract BridgeVault is IBridgeVault, AccessControl, ReentrancyGuard, Pausable {
    function _msgSender() internal view override(Context) returns (address) {
        return msg.sender;
    }

    // ============================================================
    // Constants
    // ============================================================
    bytes32 public constant RELAYER_ROLE = keccak256("RELAYER_ROLE");
    bytes32 public constant RELAYER_ADMIN_ROLE = keccak256("RELAYER_ADMIN_ROLE");
    bytes32 public constant BRIDGE_GOVERNANCE_ROLE = keccak256("BRIDGE_GOVERNANCE_ROLE");
    bytes32 public constant EMERGENCY_GUARDIAN_ROLE = keccak256("EMERGENCY_GUARDIAN_ROLE");

    // ============================================================
    // State Variables
    // ============================================================
    uint256 public immutable chainId;
    address public relayer; // Relayer operator (least privilege: processes, does not admin)
    address public destinationBridge; // Intended destination bridge on dst chain
    uint256 private _nonce;

    // Full bridge message accounting (source side)
    struct BridgeMessage {
        uint256 sourceChainId;
        uint256 destinationChainId;
        address sourceBridge;
        address destinationBridge;
        address token;
        address sender;
        address recipient;
        uint256 amount;
        uint256 nonce;
        bytes32 messageId;
        uint256 timestamp;
        bool executed; // Release completed on source side (reverse bridge)
    }
    mapping(bytes32 => BridgeMessage) private _messages;
    mapping(uint256 => bytes32) private _nonceToMessageId;
    mapping(bytes32 => bool) private _messageIds;
    mapping(uint256 => bool) private _processedNonces;
    mapping(uint256 => bool) private _messageByNonce;
    mapping(uint256 => uint256) private _lockedAmounts;
    uint256 private _totalLocked;

    // Events (defined in interface)

    // Custom Errors
    error ZeroAddress();
    error SameChain(uint256 chainId);
    error ZeroAmount();
    error NonceNotFound(uint256 nonce);
    error NonceAlreadyProcessed(uint256 nonce);
    error OnlyRelayerAllowed();
    error OnlyGovernanceAllowed();
    error TransferFailed();
    error UnauthorizedRecipient();

    // ============================================================
    // Constructor
    // ============================================================
    constructor(uint256 chainId_, address relayer_) {
        require(chainId_ != 0, "BridgeVault: zero chain ID");
        require(relayer_ != address(0), "BridgeVault: zero relayer address");

        chainId = chainId_;
        relayer = relayer_;
        // Separate roles: relayer operator, admin, governance, guardian
        _grantRole(DEFAULT_ADMIN_ROLE, relayer_);
        _grantRole(RELAYER_ROLE, relayer_);
        _grantRole(RELAYER_ADMIN_ROLE, relayer_);
        _grantRole(BRIDGE_GOVERNANCE_ROLE, relayer_);
        _grantRole(EMERGENCY_GUARDIAN_ROLE, relayer_);
    }

    // ============================================================
    // Lock (Allowance-based, Burn on Source Chain)
    // ============================================================
    /**
     * @notice Lock tokens into the vault for a cross-chain transfer.
     * @dev Tokens move via transferFrom(msg.sender, vault). The caller must
     *      have approved the vault beforehand. A relayer cannot burn another
     *      user's tokens because msg.sender is the sole authorized spender.
     */
    function lock(
        address token,
        address recipient,
        uint256 amount,
        uint256 dstChainId
    ) external override nonReentrant whenNotPaused returns (uint256 bridgeNonce) {
        if (recipient == address(0)) revert UnauthorizedRecipient();
        if (amount == 0) revert ZeroAmount();
        if (dstChainId == chainId) revert SameChain(dstChainId);
        if (destinationBridge == address(0)) revert ZeroAddress();

        // The user calls lock() directly; they must have approved this vault.
        address sender = msg.sender;

        // Transfer user funds into the vault (allowance-based, no mint/burn)
        (bool success, bytes memory data) = token.call(
            abi.encodeWithSelector(IERC20.transferFrom.selector, sender, address(this), amount)
        );
        if (!success) {
            if (data.length > 0) {
                // Surface the original revert reason
                assembly {
                    let ret := mload(data)
                    revert(add(data, 0x20), ret)
                }
            }
            revert TransferFailed();
        }
        if (IERC20(token).balanceOf(address(this)) <= 0) revert TransferFailed();

        _nonce++;
        bridgeNonce = _nonce;
        if (_messageByNonce[bridgeNonce]) revert NonceAlreadyProcessed(bridgeNonce);

        bytes32 messageId = keccak256(
            abi.encodePacked(chainId, address(this), sender, token, amount, bridgeNonce, block.timestamp)
        );
        if (_messageIdExists(messageId)) revert NonceAlreadyProcessed(bridgeNonce);

        BridgeMessage memory msg_;
        msg_.sourceChainId = chainId;
        msg_.destinationChainId = dstChainId;
        msg_.sourceBridge = address(this);
        msg_.destinationBridge = destinationBridge;
        msg_.token = token;
        msg_.sender = sender;
        msg_.recipient = recipient;
        msg_.amount = amount;
        msg_.nonce = bridgeNonce;
        msg_.messageId = messageId;
        msg_.timestamp = block.timestamp;
        msg_.executed = false;

        _messages[messageId] = msg_;
        _nonceToMessageId[bridgeNonce] = messageId;
        _messageIds[messageId] = true;
        _messageByNonce[bridgeNonce] = true;
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
        if (recipient == address(0)) revert UnauthorizedRecipient();
        if (_lockedAmounts[bridgeNonce] == 0) revert NonceNotFound(bridgeNonce);
        if (_processedNonces[bridgeNonce]) revert NonceAlreadyProcessed(bridgeNonce);

        uint256 amount = _lockedAmounts[bridgeNonce];
        _processedNonces[bridgeNonce] = true;
        _totalLocked -= amount;

        (bool success, bytes memory data) = token.call(
            abi.encodeWithSelector(IERC20.mint.selector, recipient, amount)
        );
        if (!success) {
            if (data.length > 0) {
                assembly {
                    let ret := mload(data)
                    revert(add(data, 0x20), ret)
                }
            }
            revert TransferFailed();
        }

        bytes32 messageId = _nonceToMessageId[bridgeNonce];
        if (messageId != bytes32(0)) {
            BridgeMessage storage m = _messages[messageId];
            m.executed = true;
        }

        emit TokensReleased(bridgeNonce, recipient, amount);
    }

    function _messageIdExists(bytes32 id) private view returns (bool) {
        return _messageIds[id];
    }

    // ============================================================
    // View Functions
    // ============================================================
    function totalLocked() external view override returns (uint256) {
        return _totalLocked;
    }

    function isNonceProcessed(uint256 bridgeNonce) external view override returns (bool) {
        return _processedNonces[bridgeNonce];
    }

    function lockedAmount(uint256 bridgeNonce) external view returns (uint256) {
        return _lockedAmounts[bridgeNonce];
    }

    function bridgeMessage(uint256 bridgeNonce) external view returns (BridgeMessage memory) {
        bytes32 id = _nonceToMessageId[bridgeNonce];
        return _messages[id];
    }

    function getBridgeMessage(bytes32 messageId) external view returns (BridgeMessage memory) {
        return _messages[messageId];
    }

    function isMessageExecuted(bytes32 messageId) external view returns (bool) {
        return _messages[messageId].executed;
    }

    // ============================================================
    // Admin Functions
    // ============================================================
    function setRelayer(address newRelayer) external onlyRole(DEFAULT_ADMIN_ROLE) {
        if (newRelayer == address(0)) revert ZeroAddress();
        _revokeRole(RELAYER_ROLE, relayer);
        _grantRole(RELAYER_ROLE, newRelayer);
        _grantRole(RELAYER_ADMIN_ROLE, newRelayer);
        relayer = newRelayer;
    }

    function setDestinationBridge(address dstBridge) external onlyRole(BRIDGE_GOVERNANCE_ROLE) {
        if (dstBridge == address(0)) revert ZeroAddress();
        destinationBridge = dstBridge;
    }

    function pause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _pause();
    }

    function unpause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _unpause();
    }
}
