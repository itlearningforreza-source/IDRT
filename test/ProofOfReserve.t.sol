// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {ProofOfReserve} from "../contracts/reserve/ProofOfReserve.sol";
import {IDRCToken} from "../contracts/token/IDRCToken.sol";
import {MultisigWallet} from "../contracts/multisig/MultisigWallet.sol";
import {IProofOfReserve} from "../contracts/interfaces/IReserve.sol";

contract ProofOfReserveTest is Test {
    ProofOfReserve reserve;
    IDRCToken token;
    MultisigWallet multisig;
    
    address admin = address(0x1);
    address oracle;
    address auditor = address(0x3);
    address user;
    address[] signers = [address(0x1), address(0x2), address(0x3)];

    // Oracle signers for threshold
    address[] oracleSigners;
    uint256 threshold = 1;

    function setUp() public {
        oracle = vm.rememberKey(0x1234);
        user = vm.rememberKey(0x5678);
        oracleSigners = new address[](1);
        oracleSigners[0] = oracle;

        vm.warp(1_800_000_000);

        vm.startPrank(admin);

        // Deploy multisig
        multisig = new MultisigWallet(signers, 2, 3600);

        // Deploy ProofOfReserve with oracle signers and threshold
        reserve = new ProofOfReserve(admin, oracleSigners, threshold);

        vm.stopPrank();
    }

    function _attestationDigest(uint256 fiatBalance_, uint256 timestamp_, uint256 chainId_, address reserveContract_)
        internal
        view
        returns (bytes32)
    {
        bytes32 structHash = keccak256(abi.encode(
            keccak256("Attestation(uint256 fiatBalanceIdr,uint256 timestamp,uint256 chainId,address reserveContract)"),
            fiatBalance_, timestamp_, chainId_, reserveContract_
        ));
        bytes32 domainSeparator = keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            keccak256("IDRC ProofOfReserve"),
            keccak256("1"),
            block.chainid,
            reserveContract_
        ));
        return keccak256(abi.encodePacked(hex"1901", domainSeparator, structHash));
    }

    // ===========================================
    // INITIALIZATION TESTS
    // ===========================================

    function testInitialization() public {
        assertEq(reserve.oracleSignerCount(), 1);
        assertEq(reserve.requiredSignatures(), 1);
        assertTrue(reserve.isOracleSigner(oracle));
        assertEq(reserve.fiatBalanceIdr(), 0);
        assertEq(reserve.lastOracleUpdate(), 0);
    }

    function testOracleChange() public {
        // Legacy function - should revert
        address newOracle = address(0x100);
        vm.prank(admin);
        vm.expectRevert();
        reserve.setOracle(newOracle);
    }

    function testAddOracleSigner() public {
        address newOracle = address(0x100);
        vm.prank(admin);
        reserve.addOracleSigner(newOracle);
        assertTrue(reserve.isOracleSigner(newOracle));
        assertEq(reserve.oracleSignerCount(), 2);
    }

    function testGetOracleSignersReturnsSigners() public {
        // Initially one signer (the oracle)
        address[] memory signers = reserve.getOracleSigners();
        assertEq(signers.length, 1);
        assertEq(signers[0], oracle);

        // Add another signer - list grows
        address oracle2 = address(0x100);
        vm.prank(admin);
        reserve.addOracleSigner(oracle2);
        assertEq(reserve.getOracleSigners().length, 2);

        // Remove it - list shrinks and still holds the original signer
        vm.prank(admin);
        reserve.removeOracleSigner(oracle2);
        signers = reserve.getOracleSigners();
        assertEq(signers.length, 1);
        assertEq(signers[0], oracle);
    }

    function testRemoveOracleSigner() public {
        address newOracle = address(0x100);
        vm.prank(admin);
        reserve.addOracleSigner(newOracle);
        assertEq(reserve.oracleSignerCount(), 2);
        
        vm.prank(admin);
        reserve.removeOracleSigner(newOracle);
        assertFalse(reserve.isOracleSigner(newOracle));
        assertEq(reserve.oracleSignerCount(), 1);
    }

    function testRemoveLastOracleSignerReverts() public {
        vm.prank(admin);
        vm.expectRevert();
        reserve.removeOracleSigner(oracle);
    }

    function testSetThreshold() public {
        address newOracle = address(0x100);
        vm.prank(admin);
        reserve.addOracleSigner(newOracle);
        
        vm.prank(admin);
        reserve.setThreshold(2);
        assertEq(reserve.requiredSignatures(), 2);
    }

    function testSetThresholdZeroReverts() public {
        vm.prank(admin);
        vm.expectRevert();
        reserve.setThreshold(0);
    }

    function testSetThresholdExceedsSignersReverts() public {
        vm.prank(admin);
        vm.expectRevert();
        reserve.setThreshold(5); // Only 1 signer
    }

    // ===========================================
    // ATTESTATION TESTS
    // ===========================================

    function _sigArray(address a) internal pure returns (address[] memory) {
        address[] memory arr = new address[](1);
        arr[0] = a;
        return arr;
    }

    function _sigArray2(address a, address b) internal pure returns (address[] memory) {
        address[] memory arr = new address[](2);
        arr[0] = a;
        arr[1] = b;
        return arr;
    }

    function _bytesArray(bytes memory b) internal pure returns (bytes[] memory) {
        bytes[] memory arr = new bytes[](1);
        arr[0] = b;
        return arr;
    }

    function _bytesArray2(bytes memory b1, bytes memory b2) internal pure returns (bytes[] memory) {
        bytes[] memory arr = new bytes[](2);
        arr[0] = b1;
        arr[1] = b2;
        return arr;
    }

    function testSubmitAttestation() public {
        uint256 fiatBalance_ = 1000000 * 1e18;
        uint256 timestamp_ = block.timestamp;
        uint256 chainId_ = 11155111;
        address reserveContract_ = address(reserve);
        
        // Create attestation hash
        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));
        
        // Sign with oracle key
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);
        
        vm.prank(oracle);
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray(oracle), _bytesArray(signature_));
        
        assertEq(reserve.fiatBalanceIdr(), fiatBalance_);
        assertEq(reserve.lastOracleUpdate(), timestamp_);
    }

    function testSubmitAttestationEmitsEvent() public {
        uint256 fiatBalance_ = 1000000 * 1e18;
        uint256 timestamp_ = block.timestamp;
        uint256 chainId_ = 11155111;
        
        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));
        
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);
        
        vm.expectEmit(true, true, false, true);
        emit IProofOfReserve.FiatBalanceUpdated(fiatBalance_, oracle, timestamp_, 1);
        
        vm.prank(oracle);
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray(oracle), _bytesArray(signature_));
    }

    function testSubmitAttestationNonOracleReverts() public {
        uint256 fiatBalance_ = 1000000 * 1e18;
        uint256 timestamp_ = block.timestamp;
        uint256 chainId_ = 11155111;
        
        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));
        
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(user, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);
        
        vm.prank(user);
        vm.expectRevert();
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray(user), _bytesArray(signature_));
    }

    function testSubmitAttestationInsufficientSignaturesReverts() public {
        // Add second oracle but keep threshold at 1
        address oracle2 = address(0x100);
        vm.prank(admin);
        reserve.addOracleSigner(oracle2);
        
        // Set threshold to 2
        vm.prank(admin);
        reserve.setThreshold(2);
        
        // Submit with only 1 signature
        uint256 fiatBalance_ = 1000000 * 1e18;
        uint256 timestamp_ = block.timestamp;
        uint256 chainId_ = 11155111;
        
        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));
        
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);
        
        vm.prank(oracle);
        vm.expectRevert();
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray(oracle), _bytesArray(signature_));
    }

    function testSubmitAttestationDuplicateSignerReverts() public {
        uint256 fiatBalance_ = 1000000 * 1e18;
        uint256 timestamp_ = block.timestamp;
        uint256 chainId_ = 11155111;
        
        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));
        
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);
        
        vm.prank(oracle);
        vm.expectRevert();
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray2(oracle, oracle), _bytesArray2(signature_, signature_));
    }

    function testSubmitAttestationInvalidSignerReverts() public {
        uint256 fiatBalance_ = 1000000 * 1e18;
        uint256 timestamp_ = block.timestamp;
        uint256 chainId_ = 11155111;
        
        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));
        
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(user, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);
        
        vm.prank(oracle);
        vm.expectRevert();
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray(user), _bytesArray(signature_));
    }

    function testSubmitAttestationExpiredReverts() public {
        uint256 fiatBalance_ = 1000000 * 1e18;
        uint256 timestamp_ = block.timestamp - 3 hours; // Expired
        uint256 chainId_ = 11155111;
        
        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));
        
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);
        
        vm.prank(oracle);
        vm.expectRevert();
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray(oracle), _bytesArray(signature_));
    }

    function testSubmitAttestationFutureTimestampReverts() public {
        uint256 fiatBalance_ = 1000000 * 1e18;
        uint256 timestamp_ = block.timestamp + 2 minutes; // Future timestamp
        uint256 chainId_ = 11155111;
        
        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));
        
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);
        
        vm.prank(oracle);
        vm.expectRevert();
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray(oracle), _bytesArray(signature_));
    }

    function testSubmitAttestationZeroBalanceReverts() public {
        uint256 fiatBalance_ = 0;
        uint256 timestamp_ = block.timestamp;
        uint256 chainId_ = 11155111;
        
        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));
        
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);
        
        vm.prank(oracle);
        vm.expectRevert();
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray(oracle), _bytesArray(signature_));
    }

    function testSubmitAttestationValueTooLargeReverts() public {
        uint256 fiatBalance_ = type(uint256).max / 2; // Exceeds the max accepted by the contract
        uint256 timestamp_ = block.timestamp;
        uint256 chainId_ = 11155111;

        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));

        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);

        vm.prank(oracle);
        vm.expectRevert();
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray(oracle), _bytesArray(signature_));
    }

    // ===========================================
    // AUDIT PROOF TESTS
    // ===========================================

    function testSubmitAuditProof() public {
        bytes32 hash = keccak256("audit-report-hash-123");
        uint256 reportedFiat = 1000000 * 1e6;

        // Grant auditor role first
        bytes32 AUDITOR_ROLE = keccak256("AUDITOR_ROLE");
        vm.prank(admin);
        reserve.grantRole(AUDITOR_ROLE, auditor);

        vm.prank(auditor);
        reserve.submitAuditProof(hash, reportedFiat);

        // Check audit report
        (uint256 seq, bytes32 proofHash, uint256 fiat, address submittedBy, uint256 timestamp) = reserve.getAuditReport(1);
        assertEq(seq, 1);
        assertEq(proofHash, hash);
        assertEq(fiat, reportedFiat);
        assertEq(submittedBy, auditor);
    }

    function testSubmitAuditProofEmitsEvent() public {
        bytes32 hash = keccak256("audit-report-hash-123");
        uint256 reportedFiat = 1000000 * 1e6;

        bytes32 AUDITOR_ROLE = keccak256("AUDITOR_ROLE");
        vm.prank(admin);
        reserve.grantRole(AUDITOR_ROLE, auditor);

        vm.expectEmit(true, true, false, true);
        emit IProofOfReserve.AuditProofSubmitted(1, hash, reportedFiat, auditor);

        vm.prank(auditor);
        reserve.submitAuditProof(hash, reportedFiat);
    }

    function testSubmitAuditProofNonAuditorReverts() public {
        bytes32 hash = keccak256("audit-report-hash-123");
        uint256 reportedFiat = 1000000 * 1e6;

        vm.prank(user);
        vm.expectRevert();
        reserve.submitAuditProof(hash, reportedFiat);
    }

    // ===========================================
    // CIRCUIT BREAKER & STALENESS TESTS
    // ===========================================

    function testCheckStaleness() public {
        // No oracle update yet - should be stale
        assertTrue(reserve.checkStaleness(1 hours));
        
        // Submit attestation
        uint256 fiatBalance_ = 1000000 * 1e18;
        uint256 timestamp_ = block.timestamp;
        uint256 chainId_ = 11155111;
        
        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));
        
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);
        
        vm.prank(oracle);
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray(oracle), _bytesArray(signature_));
        
        // Should not be stale immediately
        assertFalse(reserve.checkStaleness(1 hours));
        
        // Warp time forward past staleness threshold
        vm.warp(block.timestamp + 2 hours);
        
        // Should be stale now
        assertTrue(reserve.checkStaleness(1 hours));
    }

    function testIsStale() public {
        // No oracle update yet: stale
        assertTrue(reserve.isStale(1 hours));

        // Submit attestation
        uint256 fiatBalance_ = 1000000 * 1e18;
        uint256 timestamp_ = block.timestamp;
        uint256 chainId_ = 11155111;

        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));

        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);

        vm.prank(oracle);
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray(oracle), _bytesArray(signature_));

        // Fresh: not stale
        assertFalse(reserve.isStale(1 hours));

        // Warp past validity: stale
        vm.warp(block.timestamp + 2 hours);
        assertTrue(reserve.isStale(1 hours));
    }

    function testTriggerCircuitBreaker() public {
        // No oracle update yet - fail-closed: pauses because there is no fresh data
        vm.prank(admin);
        reserve.triggerCircuitBreaker(1 hours);
        assertTrue(reserve.paused());

        // Reset circuit breaker
        vm.prank(admin);
        reserve.resetCircuitBreaker();
        assertFalse(reserve.paused());

        // Submit fresh attestation
        uint256 fiatBalance_ = 1000000 * 1e18;
        uint256 timestamp_ = block.timestamp;
        uint256 chainId_ = 11155111;

        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));

        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);

        vm.prank(oracle);
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray(oracle), _bytesArray(signature_));

        assertFalse(reserve.paused());

        // Warp time forward past staleness threshold
        vm.warp(block.timestamp + 2 hours);

        // Trigger circuit breaker
        vm.prank(admin);
        reserve.triggerCircuitBreaker(1 hours);

        // Contract should be paused
        assertTrue(reserve.paused());
    }

    function testResetCircuitBreaker() public {
        // Submit attestation
        uint256 fiatBalance_ = 1000000 * 1e18;
        uint256 timestamp_ = block.timestamp;
        uint256 chainId_ = 11155111;
        
        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));
        
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);
        
        vm.prank(oracle);
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray(oracle), _bytesArray(signature_));
        
        // Warp time forward past staleness threshold
        vm.warp(block.timestamp + 2 hours);
        
        // Trigger circuit breaker
        vm.prank(admin);
        reserve.triggerCircuitBreaker(1 hours);
        assertTrue(reserve.paused());
        
        // Reset circuit breaker
        vm.prank(admin);
        reserve.resetCircuitBreaker();
        assertFalse(reserve.paused());
    }

    function testTriggerCircuitBreakerNotStaleReverts() public {
        // Submit recent attestation
        uint256 fiatBalance_ = 1000000 * 1e18;
        uint256 timestamp_ = block.timestamp;
        uint256 chainId_ = 11155111;
        
        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));
        
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);
        
        vm.prank(oracle);
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray(oracle), _bytesArray(signature_));
        
        // Try to trigger circuit breaker when not stale
        vm.prank(admin);
        vm.expectRevert();
        reserve.triggerCircuitBreaker(1 hours);
    }

    // ===========================================
    // RESERVE RATIO TESTS
    // ===========================================

    function testReserveRatio() public {
        uint256 fiatBalance_ = 1000000 * 1e18;
        uint256 timestamp_ = block.timestamp;
        uint256 chainId_ = 11155111;
        
        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));
        
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);
        
        vm.prank(oracle);
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray(oracle), _bytesArray(signature_));
        
        // Test with zero supply
        assertEq(reserve.reserveRatio(0), type(uint256).max);
        
        // Test with supply equal to fiat
        assertEq(reserve.reserveRatio(fiatBalance_), 1e18);
        
        // Test with half supply
        assertEq(reserve.reserveRatio(fiatBalance_ / 2), 2e18);
    }

    function testIsFullyCollateralised() public {
        uint256 fiatBalance_ = 1000000 * 1e18;
        uint256 timestamp_ = block.timestamp;
        uint256 chainId_ = 11155111;
        
        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));
        
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);
        
        vm.prank(oracle);
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray(oracle), _bytesArray(signature_));
        
        // Should be fully collateralised at 1:1
        assertTrue(reserve.isFullyCollateralised(fiatBalance_));
        
        // Should be fully collateralised at 1:2 (200%)
        assertTrue(reserve.isFullyCollateralised(fiatBalance_ / 2));
        
        // Should NOT be fully collateralised at 2:1 (50%)
        assertFalse(reserve.isFullyCollateralised(fiatBalance_ * 2));
    }

    function testCheckCollateralisation() public {
        uint256 fiatBalance_ = 1000000 * 1e18;
        uint256 timestamp_ = block.timestamp;
        uint256 chainId_ = 11155111;
        
        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, chainId_, address(reserve));
        
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);
        
        vm.prank(oracle);
        reserve.submitAttestation(fiatBalance_, timestamp_, chainId_, address(reserve), _sigArray(oracle), _bytesArray(signature_));
        
        assertTrue(reserve.checkCollateralisation(fiatBalance_));
    }

    // ===========================================
    // AUDIT PROOF TESTS
    // ===========================================



    function testMultipleAuditProofs() public {
        // Grant auditor role first
        bytes32 AUDITOR_ROLE = keccak256("AUDITOR_ROLE");
        vm.prank(admin);
        reserve.grantRole(AUDITOR_ROLE, auditor);

        // Submit first audit proof
        vm.prank(auditor);
        reserve.submitAuditProof(keccak256("hash-1"), 1000 * 1e18);

        vm.warp(block.timestamp + 3600);

        // Submit second audit proof
        vm.prank(auditor);
        reserve.submitAuditProof(keccak256("hash-2"), 1500 * 1e18);

        // Check both audit reports exist
        assertEq(reserve.auditReportCount(), 2);
        (, bytes32 proofHash2,,,) = reserve.getAuditReport(2);
        assertEq(proofHash2, keccak256("hash-2"));
    }

    function testSubmitAuditProofZeroHashReverts() public {
        bytes32 AUDITOR_ROLE = keccak256("AUDITOR_ROLE");
        vm.prank(admin);
        reserve.grantRole(AUDITOR_ROLE, auditor);

        vm.prank(auditor);
        vm.expectRevert();
        reserve.submitAuditProof(bytes32(0), 1000 * 1e18);
    }

    function testSubmitAuditProofZeroFiatReverts() public {
        bytes32 AUDITOR_ROLE = keccak256("AUDITOR_ROLE");
        vm.prank(admin);
        reserve.grantRole(AUDITOR_ROLE, auditor);

        vm.prank(auditor);
        vm.expectRevert();
        reserve.submitAuditProof(keccak256("hash-1"), 0);
    }

    // ===========================================
    // ORACLE SIGNER MANAGEMENT TESTS
    // ===========================================


    function testAddOracleSignerZeroAddressReverts() public {
        vm.prank(admin);
        vm.expectRevert();
        reserve.addOracleSigner(address(0));
    }

    function testAddOracleSignerAlreadyExistsReverts() public {
        vm.prank(admin);
        vm.expectRevert();
        reserve.addOracleSigner(oracle);
    }


    function testRemoveOracleSignerNotSignerReverts() public {
        vm.prank(admin);
        vm.expectRevert();
        reserve.removeOracleSigner(address(0x100));
    }

    function testRemoveOracleSignerThresholdReverts() public {
        // Can't remove last signer if threshold would be exceeded
        vm.prank(admin);
        vm.expectRevert();
        reserve.removeOracleSigner(oracle);
    }



}
