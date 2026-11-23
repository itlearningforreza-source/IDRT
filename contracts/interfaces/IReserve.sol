// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title IProofOfReserve
 * @notice Interface for Proof of Reserve contract with threshold oracle signatures
 */
interface IProofOfReserve {
    // ============================================================
    // Events
    // ============================================================
    event AuditProofSubmitted(uint256 indexed seq, bytes32 indexed proofHash, uint256 reportedFiatIdr, address indexed submittedBy);
    event FiatBalanceUpdated(uint256 indexed newBalanceIdr, address indexed submittedBy, uint256 timestamp, uint256 signaturesCount);
    event OracleSignerAdded(address indexed signer);
    event OracleSignerRemoved(address indexed signer);
    event ThresholdUpdated(uint256 oldThreshold, uint256 newThreshold);
    event CircuitBreakerTriggered(uint256 lastUpdate, uint256 stalenessThreshold);
    
    // ============================================================
    // Errors
    // ============================================================
    error ZeroAddress();
    error InvalidProofHash();
    error ZeroFiatBalance();
    error OnlyOracleAllowed();
    error UnderCollateralisedError(uint256 ratio, uint256 fiat, uint256 supply);
    error PauseNotAllowed();
    error InsufficientSignatures(uint256 provided, uint256 required);
    error InvalidSigner(address signer);
    error DuplicateSigner(address signer);
    error InvalidSignature(address signer);
    error AttestationExpired(uint256 attestationTimestamp, uint256 maxAge);
    error InvalidChainId(uint256 chainId);
    error InvalidReserveContract(address reserveContract);
    error ThresholdExceedsSigners(uint256 threshold, uint256 signerCount);
    error InsufficientSigners(uint256 signers, uint256 threshold);
    error SignerAlreadyExists(address signer);
    error SignerDoesNotExist(address signer);
    error CircuitBreakerActive(uint256 lastUpdate, uint256 stalenessThreshold);
    
    // ============================================================
    // Admin Functions
    // ============================================================
    function submitAuditProof(bytes32 proofHash, uint256 reportedFiatIdr) external;
    function addOracleSigner(address signer) external;
    function removeOracleSigner(address signer) external;
    function setThreshold(uint256 threshold) external;
    function setOracle(address oracle) external;
    function setAdmin(address admin) external;
    
    // ============================================================
    // Oracle Functions (Threshold Signatures)
    // ============================================================
    function submitAttestation(
        uint256 fiatBalanceIdr,
        uint256 timestamp,
        uint256 chainId,
        address reserveContract,
        address[] memory signers,
        bytes[] memory signatures
    ) external;
    
    // ============================================================
    // Circuit Breaker & Staleness
    // ============================================================
    function checkStaleness(uint256 stalenessThreshold) external view returns (bool);
    function triggerCircuitBreaker(uint256 stalenessThreshold) external;
    function resetCircuitBreaker() external;
    
    // ============================================================
    // View Functions
    // ============================================================
    function reserveRatio(uint256 tokenTotalSupply) external view returns (uint256);
    function isFullyCollateralised(uint256 tokenTotalSupply) external view returns (bool);
    function checkCollateralisation(uint256 tokenTotalSupply) external view returns (bool);
    function computeProofHash(bytes calldata reportData) external pure returns (bytes32);
    function verifyProof(bytes calldata reportData) external view returns (bool);
    function latestProofHash() external view returns (bytes32);
    function fiatBalanceIdr() external view returns (uint256);
    function lastOracleUpdate() external view returns (uint256);
    function oracle() external view returns (address);
    function getOracleSigners() external view returns (address[] memory);
    function requiredSignatures() external view returns (uint256);
    function oracleSignerCount() external view returns (uint256);
    function isOracleSigner(address signer) external view returns (bool);
    function latestAttestation() external view returns (
        uint256 fiatBalanceIdr,
        uint256 timestamp,
        uint256 chainId,
        address reserveContract,
        address[] memory signers,
        bytes[] memory signatures
    );
    function attestationValidity() external view returns (uint256);
    function admin() external view returns (address);
    function MIN_RESERVE_RATIO() external view returns (uint256);
    
    // ============================================================
    // Audit Reports
    // ============================================================
    function getAuditReport(uint256 seq) external view returns (uint256, bytes32, uint256, address, uint256);
    function auditReportCount() external view returns (uint256);
}