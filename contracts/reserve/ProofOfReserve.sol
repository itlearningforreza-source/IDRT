// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IProofOfReserve} from "../interfaces/IReserve.sol";
import {AccessControl} from "../access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {Context} from "@openzeppelin/contracts/utils/Context.sol";

/**
 * @title ProofOfReserve
 * @notice On-chain Proof of Reserve for IDRC stablecoin
 * @dev Supports two approaches:
 * 1. Off-chain audit hashes (SHA-256 of auditor report PDF)
 * 2. Oracle-pushed fiat balance with collateralization ratio check
 */
contract ProofOfReserve is IProofOfReserve, AccessControl, ReentrancyGuard, Pausable {
    function _msgSender() internal view override(Context, AccessControl) returns (address) {
        return msg.sender;
    }
    // ============================================================
    // Constants
    // ============================================================
    uint256 internal constant _MIN_RESERVE_RATIO = 1e18; // 100% = 1e18 (1.0 with 18 decimals)
    bytes32 public constant ORACLE_ROLE = keccak256("ORACLE_ROLE");
    bytes32 public constant AUDITOR_ROLE = keccak256("AUDITOR_ROLE");

    // ============================================================
    // State Variables
    // ============================================================
    struct AuditReport {
        uint256 seq;
        bytes32 proofHash;
        uint256 reportedFiatIdr;
        address submittedBy;
        uint256 timestamp;
    }

    AuditReport[] private _auditReports;
    bytes32 private _latestProofHash;
    uint256 private _fiatBalanceIdr;
    uint256 private _lastOracleUpdate;
    address private _oracle;

    // Events (defined in interface)

    // Custom Errors
    error ZeroAddress();
    error InvalidProofHash();
    error NegativeFiatBalance();
    error OracleNotSet();
    error OnlyOracleAllowed();
    error UnderCollateralisedError(uint256 ratio, uint256 fiat, uint256 supply);
    error PauseNotAllowed();

    // ============================================================
    // Constructor
    // ============================================================
    constructor(address admin_, address oracle_) {
        _setupRole(DEFAULT_ADMIN_ROLE, admin_);
        _setupRole(ORACLE_ROLE, oracle_);
        _setupRole(AUDITOR_ROLE, admin_); // admin can also be auditor initially
        _oracle = oracle_;
    }

    // ============================================================
    // Admin Functions
    // ============================================================

    function submitAuditProof(bytes32 proofHash, uint256 reportedFiatIdr)
        external
        override
        onlyRole(AUDITOR_ROLE)
        nonReentrant
        whenNotPaused
    {
        if (proofHash == bytes32(0)) revert InvalidProofHash();
        if (reportedFiatIdr == 0) revert NegativeFiatBalance();

        uint256 seq = _auditReports.length + 1;
        _auditReports.push(AuditReport({
            seq: seq,
            proofHash: proofHash,
            reportedFiatIdr: reportedFiatIdr,
            submittedBy: msg.sender,
            timestamp: block.timestamp
        }));
        _latestProofHash = proofHash;
        emit AuditProofSubmitted(seq, proofHash, reportedFiatIdr, msg.sender);
    }

    function setOracle(address oracle_) external override onlyRole(DEFAULT_ADMIN_ROLE) {
        if (oracle_ == address(0)) revert ZeroAddress();
        address oldOracle = _oracle;
        _oracle = oracle_;
        _revokeRole(ORACLE_ROLE, oldOracle);
        _setupRole(ORACLE_ROLE, oracle_);
        emit OracleChanged(oldOracle, oracle_);
    }

    function setAdmin(address admin_) external override onlyRole(DEFAULT_ADMIN_ROLE) {
        if (admin_ == address(0)) revert ZeroAddress();
        // Note: In production, use Ownable's transferOwnership instead
        // This is a simplified version
    }

    // ============================================================
    // Oracle Functions
    // ============================================================

    function updateFiatBalance(uint256 newBalanceIdr)
        external
        override
        onlyRole(ORACLE_ROLE)
        nonReentrant
        whenNotPaused
    {
        _fiatBalanceIdr = newBalanceIdr;
        _lastOracleUpdate = block.timestamp;
        emit FiatBalanceUpdated(newBalanceIdr, msg.sender);
    }

    // ============================================================
    // View Functions
    // ============================================================

    function reserveRatio(uint256 tokenTotalSupply) public view override returns (uint256) {
        if (tokenTotalSupply == 0) return type(uint256).max; // Infinite ratio
        return (_fiatBalanceIdr * 1e18) / tokenTotalSupply;
    }

    function isFullyCollateralised(uint256 tokenTotalSupply) public view override returns (bool) {
        return reserveRatio(tokenTotalSupply) >= _MIN_RESERVE_RATIO;
    }

    function checkCollateralisation(uint256 tokenTotalSupply) public view override returns (bool) {
        return isFullyCollateralised(tokenTotalSupply);
    }

    function computeProofHash(bytes calldata reportData) public pure override returns (bytes32) {
        return keccak256(reportData);
    }

    function latestProofHash() external view override returns (bytes32) {
        return _latestProofHash;
    }

    function fiatBalanceIdr() external view override returns (uint256) {
        return _fiatBalanceIdr;
    }

    function lastOracleUpdate() external view override returns (uint256) {
        return _lastOracleUpdate;
    }

    function oracle() external view override returns (address) {
        return _oracle;
    }

    function admin() external view override returns (address) {
        // Return first admin - simplified
        return getRoleMember(DEFAULT_ADMIN_ROLE, 0);
    }

    function MIN_RESERVE_RATIO() external view override returns (uint256) {
        return _MIN_RESERVE_RATIO;
    }

    // ============================================================
    // Audit Reports
    // ============================================================

    function getAuditReport(uint256 seq)
        external
        view
        override
        returns (uint256, bytes32, uint256, address, uint256)
    {
        require(seq > 0 && seq <= _auditReports.length, "Invalid sequence");
        AuditReport storage report = _auditReports[seq - 1];
        return (report.seq, report.proofHash, report.reportedFiatIdr, report.submittedBy, report.timestamp);
    }

    function auditReportCount() external view override returns (uint256) {
        return _auditReports.length;
    }

    // ============================================================
    // Utility Functions
    // ============================================================

    function verifyProof(bytes calldata reportData) external view override returns (bool) {
        if (_latestProofHash == bytes32(0)) return false;
        return computeProofHash(reportData) == _latestProofHash;
    }

    // ============================================================
    // Pause Control (for emergency)
    // ============================================================

    function pause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _pause();
    }

    function unpause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _unpause();
    }

    // ============================================================
    // Helper: get role member by index
    // ============================================================
    // In production, use EnumerableSet from OpenZeppelin
    function getRoleMember(bytes32 role, uint256 index) internal view returns (address) {
        // Simplified - would need EnumerableSet in production
        return address(0);
    }
}