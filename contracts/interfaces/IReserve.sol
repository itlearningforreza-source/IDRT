// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title IProofOfReserve
 * @notice Proof-of-Reserve interface for IDRC stablecoin
 */
interface IProofOfReserve {
    // Events
    event AuditProofSubmitted(uint256 indexed seq, bytes32 proofHash, uint256 reportedFiat, address indexed submittedBy);
    event FiatBalanceUpdated(uint256 newBalance, address indexed oracle);
    event OracleChanged(address indexed oldOracle, address indexed newOracle);
    event AdminChanged(address indexed oldAdmin, address indexed newAdmin);
    
    // Admin functions
    function submitAuditProof(bytes32 proofHash, uint256 reportedFiatIdr) external;
    function setOracle(address oracle) external;
    function setAdmin(address admin) external;

    // Oracle functions
    function updateFiatBalance(uint256 newBalanceIdr) external;

    // View functions
    function latestProofHash() external view returns (bytes32);
    function fiatBalanceIdr() external view returns (uint256);
    function lastOracleUpdate() external view returns (uint256);
    function reserveRatio(uint256 tokenTotalSupply) external view returns (uint256);
    function isFullyCollateralised(uint256 tokenTotalSupply) external view returns (bool);
    function checkCollateralisation(uint256 tokenTotalSupply) external view returns (bool);
    function oracle() external view returns (address);
    function admin() external view returns (address);
    function MIN_RESERVE_RATIO() external view returns (uint256);

    // Audit reports
    function getAuditReport(uint256 seq) external view returns (
        uint256 seq_,
        bytes32 proofHash,
        uint256 reportedFiatIdr,
        address submittedBy,
        uint256 timestamp
    );
    function auditReportCount() external view returns (uint256);

    // Utility
    function computeProofHash(bytes calldata reportData) external pure returns (bytes32);
    function verifyProof(bytes calldata reportData) external view returns (bool);
}