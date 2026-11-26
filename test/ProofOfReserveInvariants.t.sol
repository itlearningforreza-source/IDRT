// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {ProofOfReserve} from "../contracts/reserve/ProofOfReserve.sol";

/**
 * @title ProofOfReserveInvariantTest
 * @notice Forge invariants + fuzz tests for ProofOfReserve (addresses DEBT-015 / DEBT-016).
 */
contract ProofOfReserveInvariantTest is Test {
    ProofOfReserve internal reserve;
    address internal admin = address(0x1);
    address internal oracle;

    function setUp() public {
        oracle = vm.rememberKey(0x1234);
        vm.warp(1_800_000_000);
        address[] memory signers = new address[](1);
        signers[0] = oracle;
        reserve = new ProofOfReserve(admin, signers, 1);

        // Submit one fresh attestation so invariants can reason about a populated state
        uint256 fiatBalance_ = 1_000_000 * 1e18;
        uint256 timestamp_ = block.timestamp;
        bytes32 digest = _attestationDigest(fiatBalance_, timestamp_, 11155111, address(reserve));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);
        vm.prank(oracle);
        reserve.submitAttestation(fiatBalance_, timestamp_, 11155111, address(reserve), _arr(oracle), _arr(signature_));
    }

    // ===========================================
    // FORGE INVARIANTS
    // ===========================================

    function invariant_thresholdDoesNotExceedSignerCount() public view {
        assertLe(reserve.requiredSignatures(), reserve.oracleSignerCount());
    }

    function invariant_oracleSignerListMatchesCount() public view {
        assertEq(reserve.getOracleSigners().length, reserve.oracleSignerCount());
    }

    function invariant_oracleSignersAreUnique() public view {
        address[] memory signers = reserve.getOracleSigners();
        for (uint256 i = 0; i < signers.length; i++) {
            for (uint256 j = i + 1; j < signers.length; j++) {
                assertNotEq(signers[i], signers[j]);
            }
        }
    }

    function invariant_attestationTimestampWithinValidityWindow() public view {
        uint256 lastUpdate = reserve.lastOracleUpdate();
        if (lastUpdate > 0) {
            // Accepted attestations are at most validity old and at most
            // _FUTURE_TIMESTAMP_TOLERANCE in the future.
            assertLe(block.timestamp, lastUpdate + reserve.attestationValidity() + 1 minutes);
        }
    }

    function invariant_noZeroFiatBalance() public view {
        // A zero balance is only valid before any attestation has been accepted.
        if (reserve.lastOracleUpdate() > 0) {
            assertGt(reserve.fiatBalanceIdr(), 0);
        }
    }

    // ===========================================
    // FUZZ TESTS
    // ===========================================

    function testFuzz_submitAttestationSetsPositiveBalance(uint256 balance, uint256 offsetSeconds) public {
        balance = bound(balance, 1e18, 1e30); // Stays well below the overflow guard
        uint256 timestamp_ = block.timestamp + bound(offsetSeconds, 0, 60);

        bytes32 digest = _attestationDigest(balance, timestamp_, 11155111, address(reserve));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracle, digest);
        bytes memory signature_ = abi.encodePacked(r, s, v);

        vm.prank(oracle);
        reserve.submitAttestation(balance, timestamp_, 11155111, address(reserve), _arr(oracle), _arr(signature_));

        assertGt(reserve.fiatBalanceIdr(), 0);
    }

    // ===========================================
    // HELPERS
    // ===========================================

    function _arr(address a) internal pure returns (address[] memory) {
        address[] memory arr = new address[](1);
        arr[0] = a;
        return arr;
    }

    function _arr(bytes memory b) internal pure returns (bytes[] memory) {
        bytes[] memory arr = new bytes[](1);
        arr[0] = b;
        return arr;
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
}
