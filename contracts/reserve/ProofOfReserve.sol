// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IProofOfReserve} from "../interfaces/IReserve.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {Context} from "@openzeppelin/contracts/utils/Context.sol";

/**
 * @title ProofOfReserve
 * @notice On-chain Proof of Reserve for IDRC stablecoin with threshold oracle signatures
 * @dev Supports:
 * 1. Off-chain audit hashes (SHA-256 of auditor report PDF)
 * 2. Oracle-pushed fiat balance with threshold signatures and collateralization ratio check
 * 3. Attestation expiration and staleness detection
 * 4. Circuit breaker for oracle failures
 */
contract ProofOfReserve is IProofOfReserve, AccessControl, ReentrancyGuard, Pausable {
    using ECDSA for bytes32;
    
    function _msgSender() internal view override(Context) returns (address) {
        return msg.sender;
    }
    
    // ============================================================
    // Constants
    // ============================================================
    uint256 internal constant _MIN_RESERVE_RATIO = 1e18; // 100% = 1e18 (1.0 with 18 decimals)
    uint256 internal constant _ATTESTATION_VALIDITY = 2 hours; // Attestations valid for 2 hours
    bytes32 public constant ORACLE_ROLE = keccak256("ORACLE_ROLE");
    bytes32 public constant AUDITOR_ROLE = keccak256("AUDITOR_ROLE");
    bytes32 public constant ORACLE_ADMIN_ROLE = keccak256("ORACLE_ADMIN_ROLE");
    
    // EIP-712 domain for attestations
    bytes32 private _domainSeparator;
    bytes32 public constant ATTESTATION_TYPEHASH = keccak256(
        "Attestation(uint256 fiatBalanceIdr,uint256 timestamp,uint256 chainId,address reserveContract)"
    );
    
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
    
    struct Attestation {
        uint256 fiatBalanceIdr;
        uint256 timestamp;
        uint256 chainId;
        address reserveContract;
        address[] signers; // Oracle signers
        bytes[] signatures; // Their signatures
    }
    
    AuditReport[] private _auditReports;
    bytes32 private _latestProofHash;
    uint256 private fiatBalanceIdr_;
    uint256 private _lastOracleUpdate;
    Attestation private _latestAttestation;
    mapping(address => bool) private _isOracleSigner;
    uint256 private _requiredSignatures; // Threshold (e.g., 3)
    uint256 private _oracleSignerCount; // Total signers (e.g., 5)
    
    // NOTE: events inherited from IProofOfReserve (AuditProofSubmitted, FiatBalanceUpdated,
    // OracleSignerAdded, OracleSignerRemoved, ThresholdUpdated, CircuitBreakerTriggered).
    
    // ============================================================
    // Constructor
    // ============================================================
    constructor(
        address admin_,
        address[] memory oracleSigners_,
        uint256 threshold_
    ) {
        require(oracleSigners_.length > 0, "At least one oracle signer required");
        require(threshold_ > 0 && threshold_ <= oracleSigners_.length, "Invalid threshold");
        
        _admin = admin_;
        _grantRole(DEFAULT_ADMIN_ROLE, admin_);
        _grantRole(AUDITOR_ROLE, admin_);
        _grantRole(ORACLE_ADMIN_ROLE, admin_);
        
        _requiredSignatures = threshold_;
        _oracleSignerCount = oracleSigners_.length;
        
        // Initialize oracle signers
        for (uint256 i = 0; i < oracleSigners_.length; i++) {
            _isOracleSigner[oracleSigners_[i]] = true;
            _grantRole(ORACLE_ROLE, oracleSigners_[i]);
            emit OracleSignerAdded(oracleSigners_[i]);
        }
        
        // Initialize EIP-712 domain separator
        {
            uint256 chainId;
            assembly {
                chainId := chainid()
            }
            _domainSeparator = keccak256(
                abi.encode(
                    keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                    keccak256(bytes("IDRC ProofOfReserve")),
                    keccak256(bytes("1")),
                    chainId,
                    address(this)
                )
            );
        }
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
        if (reportedFiatIdr == 0) revert ZeroFiatBalance();
        
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
    
    function addOracleSigner(address signer_) external override onlyRole(ORACLE_ADMIN_ROLE) {
        if (signer_ == address(0)) revert ZeroAddress();
        if (_isOracleSigner[signer_]) revert SignerAlreadyExists(signer_);
        
        _isOracleSigner[signer_] = true;
        _grantRole(ORACLE_ROLE, signer_);
        _oracleSignerCount++;
        emit OracleSignerAdded(signer_);
    }
    
    function removeOracleSigner(address signer_) external override onlyRole(ORACLE_ADMIN_ROLE) {
        if (signer_ == address(0)) revert ZeroAddress();
        if (!_isOracleSigner[signer_]) revert SignerDoesNotExist(signer_);
        if (_oracleSignerCount <= _requiredSignatures) revert InsufficientSigners(_oracleSignerCount, _requiredSignatures);
        
        _isOracleSigner[signer_] = false;
        _revokeRole(ORACLE_ROLE, signer_);
        _oracleSignerCount--;
        emit OracleSignerRemoved(signer_);
    }
    
    function setThreshold(uint256 threshold_) external override onlyRole(ORACLE_ADMIN_ROLE) {
        if (threshold_ == 0) revert ZeroAddress();
        if (threshold_ > _oracleSignerCount) revert ThresholdExceedsSigners(threshold_, _oracleSignerCount);
        
        uint256 oldThreshold = _requiredSignatures;
        _requiredSignatures = threshold_;
        emit ThresholdUpdated(oldThreshold, threshold_);
    }
    
    function setOracle(address oracle_) external override onlyRole(DEFAULT_ADMIN_ROLE) {
        // Legacy single oracle setter - deprecated but kept for compatibility
        // In multi-oracle mode, use addOracleSigner/removeOracleSigner
        revert OnlyOracleAllowed();
    }
    
    function setAdmin(address admin_) external override onlyRole(DEFAULT_ADMIN_ROLE) {
        if (admin_ == address(0)) revert ZeroAddress();
        // Note: In production, use Ownable's transferOwnership instead
        // This is a simplified version
    }
    
    // ============================================================
    // Oracle Functions (Threshold Signatures)
    // ============================================================
    
    function submitAttestation(
        uint256 fiatBalance_,
        uint256 timestamp_,
        uint256 chainId_,
        address reserveContract_,
        address[] memory signers_,
        bytes[] memory signatures_
    ) external override onlyRole(ORACLE_ROLE) nonReentrant whenNotPaused {
        // Validate inputs
        if (fiatBalance_ == 0) revert ZeroFiatBalance();
        if (timestamp_ == 0) revert ZeroFiatBalance();
        if (chainId_ == 0) revert InvalidChainId(chainId_);
        if (reserveContract_ == address(0)) revert InvalidReserveContract(reserveContract_);
        if (signers_.length != signatures_.length) revert InsufficientSignatures(signers_.length, signatures_.length);
        if (signers_.length < _requiredSignatures) revert InsufficientSignatures(signers_.length, _requiredSignatures);
        
        // Check timestamp freshness (not too old, not in future)
        if (block.timestamp > timestamp_ + _ATTESTATION_VALIDITY) revert AttestationExpired(timestamp_, _ATTESTATION_VALIDITY);
        if (timestamp_ > block.timestamp + 1 minutes) revert AttestationExpired(timestamp_, 0);
        
        // Verify each signature
        bytes32 digest = _hashAttestation(fiatBalance_, timestamp_, chainId_, reserveContract_);
        uint256 validSignatures = 0;
        
        for (uint256 i = 0; i < signers_.length; i++) {
            address signer = signers_[i];
            bytes memory signature = signatures_[i];
            
            if (!_isOracleSigner[signer]) {
                revert InvalidSigner(signer);
            }
            
            // Check for duplicate signers
            for (uint256 j = 0; j < i; j++) {
                if (signers_[j] == signer) {
                    revert DuplicateSigner(signer);
                }
            }
            
            // Recover signer from signature
            address recovered = digest.recover(signatures_[i]);
            if (recovered != signer) {
                revert InvalidSignature(signer);
            }
            
            validSignatures++;
        }
        
        if (validSignatures < _requiredSignatures) {
            revert InsufficientSignatures(validSignatures, _requiredSignatures);
        }
        
        // Store attestation
        _latestAttestation = Attestation({
            fiatBalanceIdr: fiatBalance_,
            timestamp: timestamp_,
            chainId: chainId_,
            reserveContract: reserveContract_,
            signers: signers_,
            signatures: signatures_
        });
        
        fiatBalanceIdr_ = fiatBalance_;
        _lastOracleUpdate = timestamp_;
        
        emit FiatBalanceUpdated(fiatBalanceIdr_, msg.sender, timestamp_, validSignatures);
    }
    
    function _hashAttestation(
        uint256 fiatBalanceIdr,
        uint256 timestamp,
        uint256 chainId,
        address reserveContract
    ) internal view returns (bytes32) {
        bytes32 structHash = keccak256(
            abi.encode(ATTESTATION_TYPEHASH, fiatBalanceIdr, timestamp, chainId, reserveContract)
        );
        // EIP-191 prefix
        return keccak256(abi.encodePacked(hex"1901", _domainSeparator, structHash));
    }
    
    // ============================================================
    // Circuit Breaker & Staleness
    // ============================================================
    
    function checkStaleness(uint256 stalenessThreshold) external view override returns (bool) {
        if (_lastOracleUpdate == 0) return true; // No data yet = stale
        if (block.timestamp > _lastOracleUpdate + stalenessThreshold) return true;
        return false;
    }
    
    function _checkStaleness(uint256 stalenessThreshold) internal view returns (bool) {
        if (_lastOracleUpdate == 0) return true; // No data yet = stale
        if (block.timestamp > _lastOracleUpdate + stalenessThreshold) return true;
        return false;
    }
    
        function triggerCircuitBreaker(uint256 stalenessThreshold) external override onlyRole(ORACLE_ADMIN_ROLE) {
        if (!_checkStaleness(stalenessThreshold)) revert CircuitBreakerActive(_lastOracleUpdate, stalenessThreshold);
        
        // Pause the contract to prevent minting during oracle failure
        _pause();
        emit CircuitBreakerTriggered(_lastOracleUpdate, stalenessThreshold);
    }
    
    function resetCircuitBreaker() external override onlyRole(ORACLE_ADMIN_ROLE) {
        _unpause();
    }
    
    // ============================================================
    // View Functions
    // ============================================================
    
    function reserveRatio(uint256 tokenTotalSupply) public view override returns (uint256) {
        if (tokenTotalSupply == 0) return type(uint256).max;
        return (fiatBalanceIdr_ * 1e18) / tokenTotalSupply;
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
    
    function verifyProof(bytes calldata reportData) external view override returns (bool) {
        return keccak256(reportData) == _latestProofHash;
    }
    
    function latestProofHash() external view override returns (bytes32) {
        return _latestProofHash;
    }
    
    function fiatBalanceIdr() external view override returns (uint256) {
        return fiatBalanceIdr_;
    }
    
    function lastOracleUpdate() external view override returns (uint256) {
        return _lastOracleUpdate;
    }
    
    function oracle() external view override returns (address) {
        // Return first oracle signer for backward compatibility
        // In production, this should be deprecated
        return address(0);
    }
    
    function getOracleSigners() external view override returns (address[] memory) {
        // In production, this would return the list of signers
        // For now, return empty (would need enumeration)
        return new address[](0);
    }
    
    function requiredSignatures() external view override returns (uint256) {
        return _requiredSignatures;
    }
    
    function oracleSignerCount() external view override returns (uint256) {
        return _oracleSignerCount;
    }
    
    function isOracleSigner(address signer) external view override returns (bool) {
        return _isOracleSigner[signer];
    }
    
    function latestAttestation() external view override returns (
        uint256 fiatBalance_,
        uint256 timestamp_,
        uint256 chainId_,
        address reserveContract_,
        address[] memory signers_,
        bytes[] memory signatures_
    ) {
        return (
            _latestAttestation.fiatBalanceIdr,
            _latestAttestation.timestamp,
            _latestAttestation.chainId,
            _latestAttestation.reserveContract,
            _latestAttestation.signers,
            _latestAttestation.signatures
        );
    }
    
    function attestationValidity() external view override returns (uint256) {
        return _ATTESTATION_VALIDITY;
    }
    
    function admin() external view override returns (address) {
        return _admin;
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
    // Private
    // ============================================================
    
    address private _admin;
}

