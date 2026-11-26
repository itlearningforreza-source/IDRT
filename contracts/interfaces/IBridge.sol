// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title IBridgeVault
 * @notice Bridge vault interface for cross-chain IDRC transfers
 */
interface IBridgeVault {
    event TokensLocked(
        uint256 indexed bridgeNonce,
        address indexed sender,
        address indexed recipient,
        uint256 amount,
        uint256 dstChainId
    );
    event TokensReleased(
        uint256 indexed bridgeNonce,
        address indexed recipient,
        uint256 amount
    );
    event ChainRegistered(uint256 chainId, address vault);

    function lock(
        address token,
        address recipient,
        uint256 amount,
        uint256 dstChainId
    ) external returns (uint256 bridgeNonce);

    function release(
        address token,
        uint256 bridgeNonce,
        address recipient
    ) external;

    function relayer() external view returns (address);
    function chainId() external view returns (uint256);
    function totalLocked() external view returns (uint256);
    function isNonceProcessed(uint256 bridgeNonce) external view returns (bool);
}

/**
 * @title IBridgeRelayer
 * @notice Bridge relayer interface for processing cross-chain messages
 */
interface IBridgeRelayer {
    event MessageRelayed(
        address indexed recipient,
        uint256 amount,
        bytes32 messageId,
        uint256 srcChainId,
        uint256 dstChainId
    );
    event RelayerUpdated(address indexed oldRelayer, address indexed newRelayer);
    event VerifierSet(address indexed verifier);
    event TokenAllowlistUpdated(address indexed token, bool allowed);

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
    ) external;

    function relayer() external view returns (address);
    function verifier() external view returns (address);
    function isMessageExecuted(bytes32 messageId) external view returns (bool);
}

/**
 * @title IBridgeCoordinator
 * @notice High-level bridge coordinator interface
 */
interface IBridgeCoordinator {
    event ChainRegistered(uint256 chainId, address vault, address token);
    event TransferInitiated(
        uint256 indexed bridgeNonce,
        uint256 indexed srcChainId,
        uint256 indexed dstChainId,
        address sender,
        address recipient,
        uint256 amount
    );
    event TransferCompleted(
        uint256 indexed bridgeNonce,
        uint256 indexed srcChainId,
        uint256 indexed dstChainId,
        address recipient,
        uint256 amount
    );

    function registerChain(
        uint256 chainId,
        address vault,
        address token
    ) external;

    function transfer(
        uint256 srcChainId,
        uint256 dstChainId,
        address sender,
        address recipient,
        uint256 amount
    ) external returns (uint256 bridgeNonce);

    function completeTransfer(
        uint256 bridgeNonce,
        uint256 srcChainId,
        uint256 dstChainId,
        address recipient,
        uint256 amount
    ) external;

    function getChainConfig(uint256 chainId) external view returns (address vault, address token);
    function relayer() external view returns (address);
}