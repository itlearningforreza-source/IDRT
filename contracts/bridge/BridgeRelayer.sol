// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IBridgeRelayer} from "../interfaces/IBridge.sol";
import {IDRCToken} from "../token/IDRCToken.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {Context} from "@openzeppelin/contracts/utils/Context.sol";

/**
 * @title BridgeRelayer
 * @notice Off-chain relayer contract for processing cross-chain messages
 * @dev In production, this would be a decentralized network (LayerZero, Axelar, etc.)
 * This contract simulates the relayer logic for testing and single-relayer setups
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
    mapping(uint256 => mapping(uint256 => bool)) private _processedMessages; // srcChainId => bridgeNonce => processed

    // Events (defined in interface)

    // Custom Errors
    error ZeroAddress();
    error MessageAlreadyProcessed(uint256 srcChainId, uint256 bridgeNonce);
    error OnlyRelayerAllowed();
    error InvalidAmount();
    error TransferFailed();

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
    // Relay Message (Mint on Destination Chain)
    // ============================================================

    function relay(
        uint256 bridgeNonce,
        uint256 srcChainId,
        uint256 dstChainId,
        address recipient,
        uint256 amount,
        address token
    ) external override onlyRole(RELAYER_ADMIN_ROLE) nonReentrant whenNotPaused {
        if (recipient == address(0)) revert ZeroAddress();
        if (amount == 0) revert InvalidAmount();
        if (_processedMessages[srcChainId][bridgeNonce]) {
            revert MessageAlreadyProcessed(srcChainId, bridgeNonce);
        }

        // Mark as processed (replay protection)
        _processedMessages[srcChainId][bridgeNonce] = true;

        // Mint tokens on destination chain
        IDRCToken(token).mint(recipient, amount);

        emit MessageRelayed(bridgeNonce, srcChainId, dstChainId, recipient, amount);
    }

    // ============================================================
    // View Functions
    // ============================================================

    function processedMessages(uint256 srcChainId, uint256 bridgeNonce)
        external
        view
        override
        returns (bool)
    {
        return _processedMessages[srcChainId][bridgeNonce];
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
