// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {ProofOfReserve} from "../contracts/reserve/ProofOfReserve.sol";
import {IDRCToken} from "../contracts/token/IDRCToken.sol";
import {MultisigWallet} from "../contracts/multisig/MultisigWallet.sol";
import {AccessControl} from "../contracts/access/AccessControl.sol";
import {IProofOfReserve} from "../contracts/interfaces/IReserve.sol";

contract ProofOfReserveTest is Test {
    ProofOfReserve reserve;
    IDRCToken token;
    MultisigWallet multisig;
    AccessControl accessControl;

    address admin = address(0x1);
    address oracle = address(0x2);
    address auditor = address(0x3);
    address user = address(0x10);
    address[] signers = [address(0x1), address(0x2), address(0x3)];

    function setUp() public {
        vm.startPrank(admin);

        // Deploy multisig
        multisig = new MultisigWallet(signers, 2, 3600);

        // Deploy access control (constructor sets admin)
        accessControl = new AccessControl();

        // Grant oracle role
        bytes32 ORACLE_ROLE = keccak256("ORACLE_ROLE");
        accessControl.grantRole(ORACLE_ROLE, oracle);

        // Deploy reserve (constructor takes admin and oracle)
        reserve = new ProofOfReserve(admin, oracle);

        vm.stopPrank();
    }

    // ===========================================
    // INITIALIZATION TESTS
    // ===========================================

    function testInitialization() public {
        assertEq(reserve.oracle(), oracle);
        assertEq(reserve.fiatBalanceIdr(), 0);
        assertEq(reserve.lastOracleUpdate(), 0);
    }

    function testOracleChange() public {
        address newOracle = address(0x100);
        vm.prank(admin);
        reserve.setOracle(newOracle);
        assertEq(reserve.oracle(), newOracle);
    }

    // ===========================================
    // FIAT BALANCE TESTS
    // ===========================================

    function testUpdateFiatBalance() public {
        uint256 amount = 1000000 * 1e6; // 1M with 6 decimals

        vm.prank(oracle);
        reserve.updateFiatBalance(amount);

        assertEq(reserve.fiatBalanceIdr(), amount);
        assertEq(reserve.lastOracleUpdate(), block.timestamp);
    }

    function testUpdateFiatBalanceEmitsEvent() public {
        uint256 amount = 1000000 * 1e6;

        vm.expectEmit(true, true, false, true);
        emit IProofOfReserve.FiatBalanceUpdated(amount, oracle);

        vm.prank(oracle);
        reserve.updateFiatBalance(amount);
    }

    function testUpdateFiatBalanceNonOracleReverts() public {
        vm.prank(user);
        vm.expectRevert();
        reserve.updateFiatBalance(1000 * 1e6);
    }

    function testUpdateFiatBalanceZeroAmount() public {
        vm.prank(oracle);
        reserve.updateFiatBalance(0);

        assertEq(reserve.fiatBalanceIdr(), 0);
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

        // Grant auditor role first
        bytes32 AUDITOR_ROLE = keccak256("AUDITOR_ROLE");
        vm.prank(admin);
        reserve.grantRole(AUDITOR_ROLE, auditor);

        vm.prank(auditor);

        vm.expectEmit(true, true, false, true);
        emit IProofOfReserve.AuditProofSubmitted(1, hash, reportedFiat, auditor);

        reserve.submitAuditProof(hash, reportedFiat);
    }

    function testSubmitAuditProofNonAuditorReverts() public {
        bytes32 AUDITOR_ROLE = keccak256("AUDITOR_ROLE");
        vm.prank(admin);
        reserve.grantRole(AUDITOR_ROLE, auditor);

        vm.prank(user);
        vm.expectRevert();
        reserve.submitAuditProof(keccak256("hash"), 1000000 * 1e6);
    }

    // ===========================================
    // COLLATERALIZATION RATIO TESTS
    // ===========================================

    function testGetCollateralizationRatio() public {
        // Set fiat balance to 1M USD
        vm.prank(oracle);
        reserve.updateFiatBalance(1000000 * 1e6);

        // Total supply = 0, ratio should be max
        uint256 ratio = reserve.reserveRatio(0);
        assertEq(ratio, type(uint256).max);
    }

    function testCollateralizationRatioCalculation() public {
        // Set fiat balance to 1M USD (1e6 = 6 decimals)
        vm.prank(oracle);
        reserve.updateFiatBalance(1000000 * 1e6);

        // Total supply = 500k tokens (1:1 peg, 18 decimals)
        // Ratio = (fiat * 1e18) / supply = (1e12 * 1e18) / 5e23 = 1e30 / 5e23 = 2e6
        // Wait: fiatBalanceIdr = 1,000,000 * 1e6 = 1e12
        // supply = 500,000 * 1e18 = 5e23
        // ratio = (1e12 * 1e18) / 5e23 = 1e30 / 5e23 = 2e6
        uint256 ratio = reserve.reserveRatio(500000 * 1e18);

        assertEq(ratio, 2 * 10**6);
    }

    function testCollateralizationRatioUnderCollateralized() public {
        vm.prank(oracle);
        reserve.updateFiatBalance(500000 * 1e6); // 500k USD

        // Total supply = 1M tokens
        uint256 ratio = reserve.reserveRatio(1000000 * 1e18);

        // (5e11 * 1e18) / 1e24 = 5e29 / 1e24 = 5e5
        assertEq(ratio, 5 * 10**5);
    }

    function testCollateralizationRatioExactlyFullyBacked() public {
        vm.prank(oracle);
        reserve.updateFiatBalance(1000000 * 1e6); // 1M USD

        // Total supply = 1M tokens
        // (1e12 * 1e18) / 1e24 = 1e30 / 1e24 = 1e6
        uint256 ratio = reserve.reserveRatio(1000000 * 1e18);

        assertEq(ratio, 10**6);
    }

    // ===========================================
    // IS SOLVENT TESTS
    // ===========================================

    function testIsFullyCollateralisedWhenFullyBacked() public {
        vm.prank(oracle);
        // For isFullyCollateralised to return true, need ratio >= 1e18
        // ratio = (fiat * 1e18) / supply >= 1e18
        // fiat * 1e18 >= supply * 1e18
        // fiat >= supply
        // So if supply = 1000 ether = 1000 * 1e18, need fiat >= 1000 * 1e18
        reserve.updateFiatBalance(1000 * 1e18);

        assertEq(reserve.isFullyCollateralised(1000 * 1e18), true);
        assertEq(reserve.isFullyCollateralised(500 * 1e18), true);
    }

    function testIsFullyCollateralisedWhenUnderCollateralized() public {
        vm.prank(oracle);
        reserve.updateFiatBalance(500 * 1e18);

        assertEq(reserve.isFullyCollateralised(1000 * 1e18), false);
    }

    function testIsFullyCollateralisedWithMinRatio() public {
        vm.prank(oracle);
        reserve.updateFiatBalance(1100 * 1e18);

        // Min ratio is 1e18 (100%)
        // With fiat=1100e18, supply=1000e18: ratio = (1100e18 * 1e18) / 1000e18 = 1.1e18 >= 1e18 => true
        // With fiat=1100e18, supply=1100e18: ratio = (1100e18 * 1e18) / 1100e18 = 1e18 >= 1e18 => true
        // Need supply > fiat to get false
        assertEq(reserve.isFullyCollateralised(1000 * 1e18), true);
        assertEq(reserve.isFullyCollateralised(1100 * 1e18), true);
        assertEq(reserve.isFullyCollateralised(1200 * 1e18), false);
    }

    // ===========================================
    // RESERVE STATUS TESTS
    // ===========================================

    function testGetReserveStatus() public {
        vm.prank(oracle);
        reserve.updateFiatBalance(1000 * 1e18);

        // Grant auditor role and submit audit proof
        bytes32 AUDITOR_ROLE = keccak256("AUDITOR_ROLE");
        vm.prank(admin);
        reserve.grantRole(AUDITOR_ROLE, auditor);

        vm.prank(auditor);
        reserve.submitAuditProof(keccak256("audit-hash"), 1000 * 1e18);

        // Check audit report
        (uint256 seq, bytes32 proofHash, uint256 fiat, address submittedBy, uint256 timestamp) = reserve.getAuditReport(1);
        assertEq(seq, 1);
        assertEq(proofHash, keccak256("audit-hash"));
        assertEq(fiat, 1000 * 1e18);
        assertEq(submittedBy, auditor);
        assertEq(reserve.auditReportCount(), 1);
    }

    // ===========================================
    // ADMIN FUNCTIONS TESTS
    // ===========================================

    function testSetOracle() public {
        address newOracle = address(0x4);

        vm.prank(admin);
        reserve.setOracle(newOracle);

        assertEq(reserve.oracle(), newOracle);
    }

    function testAdminOnlySetOracle() public {
        vm.prank(user);
        vm.expectRevert();
        reserve.setOracle(address(0x4));
    }

    // ===========================================
    // EDGE CASES
    // ===========================================

    function testLargeFiatBalance() public {
        uint256 largeAmount = type(uint128).max;

        vm.prank(oracle);
        reserve.updateFiatBalance(largeAmount);

        assertEq(reserve.fiatBalanceIdr(), largeAmount);
    }

    function testMultipleFiatUpdates() public {
        vm.prank(oracle);
        reserve.updateFiatBalance(1000 * 1e18);

        vm.warp(block.timestamp + 3600);

        vm.prank(oracle);
        reserve.updateFiatBalance(1500 * 1e18);

        assertEq(reserve.fiatBalanceIdr(), 1500 * 1e18);
    }

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
}