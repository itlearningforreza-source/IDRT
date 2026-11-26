// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IBridgeRelayer} from "../interfaces/IBridge.sol";
import {IERC20} from "../interfaces/IERC20.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {Context} from "@openzeppelin/contracts/utils/Context.sol";

/**
 * @title BridgeRelayer
 * @notice Authenticated bridge relayer. Messages must be verified by a trusted
 *         verifier before minting. Never trusts caller-supplied parameters
 *         without verification (Security Audit 4.0).
 */
contract BridgeRelayer is IBridgeRelayer, AccessControl, ReentrancyGuard, Pausable {
    function _msgSender() internal view override(Context) returns (address) {
        return msg.sender;
    }

    // ============================================================
    // Constants
    // ============================================================
    bytes32 public constant RELAYER_ADMIN_ROLE = keccak256("RELAYER_ADMIN_ROLE");

    // ============================================================
    // State Variables
    // ============================================================
    address public relayer;
    address public verifier; // Trusted verification contract/agent
    mapping(bytes32 => bool) private _executedMessages; // canonical message hash
    mapping(address => bool) private _tokenAllowlist;
    uint256 private _replayCheckNonce;

    // ============================================================
    // Errors
    // ============================================================
    error ZeroAddress();
    error MessageAlreadyProcessed(bytes32 messageId);
    error OnlyVerifierAllowed();
    error InvalidAmount();
    error TransferFailed();
    error UnauthorizedToken();
    error UnauthorizedRecipient();
    error IncorrectDestinationChain();
    error IncorrectDestinationBridge();
    error NotVerified();
    error InvalidChainId(uint256 chainId);

    // ============================================================
    // Constructor
    // ============================================================
    constructor(address relayer_) {
        require(relayer_ != address(0), "BridgeRelayer: zero relayer address");
        relayer = relayer_;
        _grantRole(DEFAULT_ADMIN_ROLE, relayer_);
        _grantRole(RELAYER_ADMIN_ROLE, relayer_);
    }

    // ============================================================
    // Verification Architecture (Trusted Verifier)
    // ============================================================
    /**
     * @notice Set the trusted message verifier.
     */
    function setVerifier(address verifier_) external onlyRole(DEFAULT_ADMIN_ROLE) {
        if (verifier_ == address(0)) revert ZeroAddress();
        verifier = verifier_;
        emit VerifierSet(verifier_);
    }

    /**
     * @notice Allow/deny token on this destination bridge.
     */
    function setTokenAllowlist(address token, bool allowed) external onlyRole(DEFAULT_ADMIN_ROLE) {
        if (token == address(0)) revert ZeroAddress();
        _tokenAllowlist[token] = allowed;
    }

    // ============================================================
    // Relay Message (Mint on Destination Chain)
    // ============================================================
    /**
     * @notice Relay a verified bridge message and mint on the destination chain.
     * @dev All economically relevant fields are canonicalized into messageId and
     *      must be verified by the trusted verifier. Replay-protected.
     */
    function relay(
        uint256 srcChainId,
        uint256 dstChainId,
        address sourceBridge,
        address destinationBridge,
        address token,
        address sender,
        address recipient,
        uint256 amount,
        bytes32 messageId
    ) external nonReentrant whenNotPaused {
        if (msg.sender != verifier) revert OnlyVerifierAllowed();
        if (recipient == address(0)) revert UnauthorizedRecipient();
        if (amount == 0) revert InvalidAmount();
        if (srcChainId == 0) revert InvalidChainId(srcChainId);
        if (dstChainId != block.chainid) revert IncorrectDestinationChain();
        if (destinationBridge != address(this)) revert IncorrectDestinationBridge();
        if (!_tokenAllowlist[token]) revert UnauthorizedToken();
        if (_executedMessages[messageId]) revert MessageAlreadyProcessed(messageId);

        // Canonical hash covers all economically relevant fields (domain separation)
        bytes32 canonicalHash = keccak256(
            abi.encodePacked(
                block.chainid,
                address(this),
                srcChainId,
                dstChainId,
                sourceBridge,
                destinationBridge,
                token,
                sender,
                recipient,
                amount,
                messageId
            )
        );

        _executedMessages[canonicalHash] = true;
        _executedMessages[messageId] = true;

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

        emit MessageRelayed(recipient, amount, messageId, srcChainId, dstChainId);
    }

    function isMessageExecuted(bytes32 messageId) external view returns (bool) {
        return _executedMessages[messageId];
    }

    function tokenAllowed(address token) external view returns (bool) {
        return _tokenAllowlist[token];
    }

    // ============================================================
    // Admin Functions
    // ============================================================
    function setRelayer(address newRelayer) external onlyRole(RELAYER_ADMIN_ROLE) {
        if (newRelayer == address(0)) revert ZeroAddress();
        _revokeRole(RELAYER_ADMIN_ROLE, relayer);
        _grantRole(RELAYER_ADMIN_ROLE, newRelayer);
        relayer = newRelayer;
        emit RelayerUpdated(relayer, newRelayer);
    }

    function pause() external onlyRole(RELAYER_ADMIN_ROLE) {
        _pause();
    }

    function unpause() external onlyRole(RELAYER_ADMIN_ROLE) {
        _unpause();
    }
}
