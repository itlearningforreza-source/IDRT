// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title IMultisig
 * @notice M-of-N Multisig wallet interface (Gnosis Safe compatible)
 */
interface IMultisig {
    // Events
    event Submission(address indexed sender, uint256 indexed transactionId);
    event Confirmation(address indexed sender, uint256 indexed transactionId);
    event Revocation(address indexed sender, uint256 indexed transactionId);
    event Execution(address indexed sender, uint256 indexed transactionId);
    event ExecutionFailure(address indexed sender, uint256 indexed transactionId);
    event Deposit(address indexed sender, uint256 value);
    event ChangedThreshold(uint256 threshold);
    event OwnerAdded(address indexed owner);
    event OwnerRemoved(address indexed owner);
    event OwnerChanged(address indexed prevOwner, address indexed newOwner);

    // Transaction lifecycle
    function submitTransaction(
        address to,
        uint256 value,
        bytes calldata data
    ) external returns (uint256 transactionId);

    function confirmTransaction(uint256 transactionId) external;
    function revokeConfirmation(uint256 transactionId) external;
    function executeTransaction(uint256 transactionId) external payable returns (bool success);

    // Transaction queries
    function getTransactionCount() external view returns (uint256);
    function transactions(uint256 transactionId) external view returns (
        address to,
        uint256 value,
        bytes memory data,
        bool executed,
        uint256 confirmationsRequired
    );
    function getConfirmations(uint256 transactionId) external view returns (address[] memory confirmations, bool executed);
    function isConfirmed(uint256 transactionId) external view returns (bool);
    function getTransactionIds(
        uint256 from,
        uint256 to
    ) external view returns (uint256[] memory pending, uint256[] memory confirmed, uint256[] memory executed);

    // Owner management
    function getOwners() external view returns (address[] memory);
    function getThreshold() external view returns (uint256);
    function isOwner(address account) external view returns (bool);

    // Advanced
    function addOwnerWithThreshold(address owner, uint256 threshold) external;
    function removeOwner(address owner, uint256 threshold) external;
    function replaceOwner(address prevOwner, address newOwner, uint256 threshold) external;
    function changeThreshold(uint256 threshold) external;
}