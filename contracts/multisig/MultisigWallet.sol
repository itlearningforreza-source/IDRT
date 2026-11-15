// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IMultisig} from "../interfaces/IMultisig.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title MultisigWallet
 * @notice M-of-N Multisig wallet (Gnosis Safe compatible)
 * @dev Features: timelock, owner management, transaction lifecycle, ETH handling
 * Does not inherit from Ownable - implements owner checks directly
 */
contract MultisigWallet is IMultisig, ReentrancyGuard {
    // ============================================================
    // State Variables
    // ============================================================
    address[] private _owners;
    mapping(address => bool) private _isOwner;
    uint256 private _threshold;
    uint256 private _timelock; // seconds

    // Transaction storage
    struct Transaction {
        address to;
        uint256 value;
        bytes data;
        bool executed;
        uint256 nonce; // for replay protection
    }
    Transaction[] private _transactions;
    mapping(uint256 => mapping(address => bool)) private _confirmations;
    mapping(uint256 => uint256) private _confirmationCount;
    mapping(uint256 => uint256) private _submissionTime;

    // Events (defined in interface, emitted here)

    // Custom Errors
    error InvalidThreshold(uint256 threshold, uint256 ownerCount);
    error NotOwner(address account);
    error AlreadyOwner(address account);
    error OwnerNotFound(address account);
    error ThresholdNotReached(uint256 confirmations, uint256 threshold);
    error TimelockNotExpired(uint256 remaining);
    error TransactionAlreadyExecuted(uint256 txId);
    error TransactionNotFound(uint256 txId);
    error TransactionFailed();
    error ZeroAddress();
    error InsufficientBalance(uint256 needed, uint256 available);

    // ============================================================
    // Constructor
    // ============================================================
    constructor(
        address[] memory owners,
        uint256 threshold,
        uint256 timelock_
    ) {
        require(owners.length > 0, "Multisig: at least one owner required");
        require(threshold > 0 && threshold <= owners.length, "Multisig: invalid threshold");
        require(timelock_ >= 0, "Multisig: negative timelock");

        _threshold = threshold;
        _timelock = timelock_;

        for (uint256 i = 0; i < owners.length; i++) {
            address owner = owners[i];
            require(owner != address(0), "Multisig: zero address owner");
            require(!_isOwner[owner], "Multisig: duplicate owner");
            _owners.push(owner);
            _isOwner[owner] = true;
        }
    }

    // ============================================================
    // Transaction Lifecycle
    // ============================================================

    /**
     * @notice Submit a new transaction
     * @param to Destination address
     * @param value ETH value to send
     * @param data Calldata
     * @return transactionId ID of submitted transaction
     */
    function submitTransaction(
        address to,
        uint256 value,
        bytes calldata data
    ) external override onlyOwner nonReentrant returns (uint256 transactionId) {
        transactionId = _transactions.length;
        _transactions.push(Transaction({
            to: to,
            value: value,
            data: data,
            executed: false,
            nonce: transactionId
        }));
        _confirmationCount[transactionId] = 1;
        _confirmations[transactionId][msg.sender] = true;
        _submissionTime[transactionId] = block.timestamp;
        emit Submission(msg.sender, transactionId);
    }

    /**
     * @notice Confirm a pending transaction
     * @param transactionId ID of transaction to confirm
     */
    function confirmTransaction(uint256 transactionId) external override onlyOwner nonReentrant {
        Transaction storage txn = _transactions[transactionId];
        if (txn.executed) revert TransactionAlreadyExecuted(transactionId);
        if (_confirmations[transactionId][msg.sender]) return; // already confirmed

        _confirmations[transactionId][msg.sender] = true;
        _confirmationCount[transactionId] += 1;
        emit Confirmation(msg.sender, transactionId);
    }

    /**
     * @notice Revoke confirmation for a transaction
     * @param transactionId ID of transaction
     */
    function revokeConfirmation(uint256 transactionId) external override onlyOwner {
        if (!_confirmations[transactionId][msg.sender]) return;
        _confirmations[transactionId][msg.sender] = false;
        _confirmationCount[transactionId] -= 1;
        emit Revocation(msg.sender, transactionId);
    }

    /**
     * @notice Execute a confirmed transaction
     * @param transactionId ID of transaction to execute
     * @return success Whether execution succeeded
     */
    function executeTransaction(uint256 transactionId)
        external
        override
        payable
        onlyOwner
        nonReentrant
        returns (bool success)
    {
        Transaction storage txn = _transactions[transactionId];

        // Checks
        if (txn.executed) revert TransactionAlreadyExecuted(transactionId);
        if (_confirmationCount[transactionId] < _threshold) {
            revert ThresholdNotReached(_confirmationCount[transactionId], _threshold);
        }
        if (_timelock > 0 && block.timestamp < _submissionTime[transactionId] + _timelock) {
            revert TimelockNotExpired(_submissionTime[transactionId] + _timelock - block.timestamp);
        }

        // Execute
        txn.executed = true;

        // Use delegatecall for self-calls to preserve msg.sender context
        // This allows owner management functions to be called through the multisig
        bool callSuccess;
        if (txn.to == address(this)) {
            (callSuccess, ) = address(this).delegatecall(txn.data);
        } else {
            (callSuccess, ) = txn.to.call{value: txn.value}(txn.data);
        }

        if (!callSuccess) {
            emit ExecutionFailure(msg.sender, transactionId);
            revert TransactionFailed();
        }

        emit Execution(msg.sender, transactionId);
        return true;
    }

    // ============================================================
    // Transaction Queries
    // ============================================================

    function getTransactionCount() external view override returns (uint256) {
        return _transactions.length;
    }

    function transactions(uint256 transactionId)
        external
        view
        override
        returns (address to, uint256 value, bytes memory data, bool executed, uint256 confirmationsRequired)
    {
        Transaction storage txn = _transactions[transactionId];
        return (txn.to, txn.value, txn.data, txn.executed, _threshold);
    }

    function getConfirmations(uint256 transactionId)
        external
        view
        override
        returns (address[] memory confirmations, bool executed)
    {
        Transaction storage txn = _transactions[transactionId];
        uint256 count = _confirmationCount[transactionId];
        confirmations = new address[](count);
        uint256 idx = 0;
        for (uint256 i = 0; i < _owners.length; i++) {
            if (_confirmations[transactionId][_owners[i]]) {
                confirmations[idx] = _owners[i];
                idx++;
            }
        }
        return (confirmations, txn.executed);
    }

    function isConfirmed(uint256 transactionId) external view override returns (bool) {
        return _confirmationCount[transactionId] >= _threshold;
    }

    function getTransactionIds(
        uint256 from,
        uint256 to
    ) external view override returns (uint256[] memory pending, uint256[] memory confirmed, uint256[] memory executed) {
        uint256 pendingCount = 0;
        uint256 confirmedCount = 0;
        uint256 executedCount = 0;

        // First pass: count
        for (uint256 i = from; i < to && i < _transactions.length; i++) {
            if (_transactions[i].executed) {
                executedCount++;
            } else if (_confirmationCount[i] >= _threshold) {
                confirmedCount++;
            } else {
                pendingCount++;
            }
        }

        // Second pass: fill arrays
        pending = new uint256[](pendingCount);
        confirmed = new uint256[](confirmedCount);
        executed = new uint256[](executedCount);

        uint256 p = 0;
        uint256 c = 0;
        uint256 e = 0;
        for (uint256 i = from; i < to && i < _transactions.length; i++) {
            if (_transactions[i].executed) {
                executed[e] = i;
                e++;
            } else if (_confirmationCount[i] >= _threshold) {
                confirmed[c] = i;
                c++;
            } else {
                pending[p] = i;
                p++;
            }
        }
    }

    // ============================================================
    // Owner Management
    // ============================================================

    function getOwners() external view override returns (address[] memory) {
        return _owners;
    }

    function getThreshold() external view override returns (uint256) {
        return _threshold;
    }

    function isOwner(address account) external view override returns (bool) {
        return _isOwner[account];
    }

    function addOwnerWithThreshold(address owner, uint256 threshold) external override onlyOwner {
        require(owner != address(0), "Multisig: zero address");
        require(!_isOwner[owner], "Multisig: already owner");
        require(threshold > 0 && threshold <= _owners.length + 1, "Multisig: invalid threshold");

        _owners.push(owner);
        _isOwner[owner] = true;
        _threshold = threshold;
        emit OwnerAdded(owner);
        emit ChangedThreshold(threshold);
    }

    function removeOwner(address owner, uint256 threshold) external override onlyOwner {
        require(_isOwner[owner], "Multisig: not an owner");
        require(_owners.length > 1, "Multisig: cannot remove last owner");
        require(threshold > 0 && threshold <= _owners.length - 1, "Multisig: invalid threshold");

        // Remove owner from array (swap with last)
        for (uint256 i = 0; i < _owners.length; i++) {
            if (_owners[i] == owner) {
                _owners[i] = _owners[_owners.length - 1];
                _owners.pop();
                break;
            }
        }
        _isOwner[owner] = false;
        _threshold = threshold;
        emit OwnerRemoved(owner);
        emit ChangedThreshold(threshold);
    }

    function replaceOwner(address prevOwner, address newOwner, uint256 threshold) external override onlyOwner {
        require(_isOwner[prevOwner], "Multisig: prevOwner not an owner");
        require(newOwner != address(0), "Multisig: zero address");
        require(!_isOwner[newOwner], "Multisig: newOwner already owner");
        require(threshold > 0 && threshold <= _owners.length, "Multisig: invalid threshold");

        for (uint256 i = 0; i < _owners.length; i++) {
            if (_owners[i] == prevOwner) {
                _owners[i] = newOwner;
                break;
            }
        }
        _isOwner[prevOwner] = false;
        _isOwner[newOwner] = true;
        _threshold = threshold;
        emit OwnerChanged(prevOwner, newOwner);
        emit ChangedThreshold(threshold);
    }

    function changeThreshold(uint256 threshold) external override onlyOwner {
        require(threshold > 0 && threshold <= _owners.length, "Multisig: invalid threshold");
        _threshold = threshold;
        emit ChangedThreshold(threshold);
    }

    // ============================================================
    // ETH Handling
    // ============================================================

    receive() external payable {
        emit Deposit(msg.sender, msg.value);
    }

    fallback() external payable {
        emit Deposit(msg.sender, msg.value);
    }

    // ============================================================
    // Timelock Management
    // ============================================================

    function getTimelock() external view returns (uint256) {
        return _timelock;
    }

    function setTimelock(uint256 timelock_) external onlyOwner {
        _timelock = timelock_;
    }

    // ============================================================
    // Helper
    // ============================================================

    modifier onlyOwner() {
        if (!_isOwner[msg.sender]) revert NotOwner(msg.sender);
        _;
    }
}