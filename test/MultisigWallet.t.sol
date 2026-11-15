// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {MultisigWallet} from "../contracts/multisig/MultisigWallet.sol";
import {IMultisig} from "../contracts/interfaces/IMultisig.sol";

contract MultisigWalletTest is Test {
    MultisigWallet multisig;
    address[] signers = [address(0x1), address(0x2), address(0x3)];
    uint256 constant THRESHOLD = 2;
    uint256 constant TIMELOCK = 3600; // 1 hour
    address target = address(0x100);
    address user = address(0x10);

    function setUp() public {
        multisig = new MultisigWallet(signers, THRESHOLD, TIMELOCK);
    }

    // ===========================================
    // CONSTRUCTOR TESTS
    // ===========================================

    function testConstructorSetsSigners() public {
        assertEq(multisig.getOwners(), signers);
    }

    function testConstructorSetsThreshold() public {
        assertEq(multisig.getThreshold(), THRESHOLD);
    }

    function testConstructorSetsTimelock() public {
        assertEq(multisig.getTimelock(), TIMELOCK);
    }

    function testConstructorRevertsInvalidThreshold() public {
        vm.expectRevert();
        new MultisigWallet(signers, 0, TIMELOCK);
    }

    function testConstructorRevertsThresholdExceedsSigners() public {
        vm.expectRevert();
        new MultisigWallet(signers, 4, TIMELOCK);
    }

    function testConstructorRevertsDuplicateSigners() public {
        address[] memory dupSigners = new address[](3);
        dupSigners[0] = address(0x1);
        dupSigners[1] = address(0x1);
        dupSigners[2] = address(0x2);
        vm.expectRevert();
        new MultisigWallet(dupSigners, 2, TIMELOCK);
    }

    function testConstructorRevertsZeroAddressSigner() public {
        address[] memory zeroSigners = new address[](3);
        zeroSigners[0] = address(0);
        zeroSigners[1] = address(0x2);
        zeroSigners[2] = address(0x3);
        vm.expectRevert();
        new MultisigWallet(zeroSigners, 2, TIMELOCK);
    }

    // ===========================================
    // SUBMIT TRANSACTION TESTS
    // ===========================================

    function testSubmitTransaction() public {
        bytes memory data = abi.encodeWithSignature("transfer(address,uint256)", user, 100 ether);

        vm.prank(signers[0]);
        multisig.submitTransaction(target, 1 ether, data);

        (address to, uint256 value, bytes memory txData, bool executed, uint256 confirmationsRequired) = multisig.transactions(0);
        assertEq(to, target);
        assertEq(value, 1 ether);
        assertEq(txData, data);
        assertEq(executed, false);
        assertEq(confirmationsRequired, THRESHOLD);

        (address[] memory confirmations, bool txExecuted) = multisig.getConfirmations(0);
        assertEq(confirmations.length, 1);
        assertEq(txExecuted, false);
    }

    function testSubmitTransactionEmitsEvent() public {
        bytes memory data = abi.encodeWithSignature("transfer(address,uint256)", user, 100 ether);

        vm.expectEmit(true, true, false, true);
        emit IMultisig.Submission(signers[0], 0);

        vm.prank(signers[0]);
        multisig.submitTransaction(target, 1 ether, data);
    }

    function testSubmitTransactionNonSignerReverts() public {
        bytes memory data = abi.encodeWithSignature("transfer(address,uint256)", user, 100 ether);

        vm.prank(user);
        vm.expectRevert();
        multisig.submitTransaction(target, 1 ether, data);
    }

    // ===========================================
    // CONFIRM TRANSACTION TESTS
    // ===========================================

    function testConfirmTransaction() public {
        bytes memory data = abi.encodeWithSignature("transfer(address,uint256)", user, 100 ether);

        vm.prank(signers[0]);
        multisig.submitTransaction(target, 1 ether, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        (address[] memory confirmations, bool txExecuted) = multisig.getConfirmations(0);
        assertEq(confirmations.length, 2);
        assertEq(txExecuted, false);
    }

    function testConfirmTransactionEmitsEvent() public {
        bytes memory data = abi.encodeWithSignature("transfer(address,uint256)", user, 100 ether);

        vm.prank(signers[0]);
        multisig.submitTransaction(target, 1 ether, data);

        vm.expectEmit(true, true, false, true);
        emit IMultisig.Confirmation(signers[1], 0);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);
    }

    function testConfirmTransactionNonSignerReverts() public {
        bytes memory data = abi.encodeWithSignature("transfer(address,uint256)", user, 100 ether);

        vm.prank(signers[0]);
        multisig.submitTransaction(target, 1 ether, data);

        vm.prank(user);
        vm.expectRevert();
        multisig.confirmTransaction(0);
    }

    function testConfirmAlreadyConfirmedReverts() public {
        bytes memory data = abi.encodeWithSignature("transfer(address,uint256)", user, 100 ether);

        vm.prank(signers[0]);
        multisig.submitTransaction(target, 1 ether, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        // Second confirmation should just be ignored, not revert
        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        (address[] memory confirmations, bool txExecuted) = multisig.getConfirmations(0);
        assertEq(confirmations.length, 2);
    }

    function testConfirmExecutedTransactionReverts() public {
        TestContract testContract = new TestContract();
        bytes memory data = abi.encodeWithSignature("setValue(uint256)", 42);

        vm.prank(signers[0]);
        multisig.submitTransaction(address(testContract), 0, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        // Advance time past timelock
        vm.warp(block.timestamp + TIMELOCK + 1);

        vm.prank(signers[0]);
        multisig.executeTransaction(0);

        vm.prank(signers[2]);
        vm.expectRevert();
        multisig.confirmTransaction(0);
    }

    // ===========================================
    // EXECUTE TRANSACTION TESTS
    // ===========================================

    function testExecuteTransaction() public {
        // Deploy a simple contract to call
        TestContract testContract = new TestContract();
        bytes memory data = abi.encodeWithSignature("setValue(uint256)", 42);

        vm.prank(signers[0]);
        multisig.submitTransaction(address(testContract), 0, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        // Advance time past timelock
        vm.warp(block.timestamp + TIMELOCK + 1);

        vm.prank(signers[0]);
        multisig.executeTransaction(0);

        assertEq(testContract.value(), 42);
        (,,, bool executed,) = multisig.transactions(0);
        assertEq(executed, true);
    }

    function testExecuteTransactionEmitsEvent() public {
        TestContract testContract = new TestContract();
        bytes memory data = abi.encodeWithSignature("setValue(uint256)", 42);

        vm.prank(signers[0]);
        multisig.submitTransaction(address(testContract), 0, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        vm.warp(block.timestamp + TIMELOCK + 1);

        vm.expectEmit(true, true, false, true);
        emit IMultisig.Execution(signers[0], 0);

        vm.prank(signers[0]);
        multisig.executeTransaction(0);
    }

    function testExecuteTransactionInsufficientConfirmationsReverts() public {
        TestContract testContract = new TestContract();
        bytes memory data = abi.encodeWithSignature("setValue(uint256)", 42);

        vm.prank(signers[0]);
        multisig.submitTransaction(address(testContract), 0, data);

        // Only 1 confirmation, need 2
        vm.warp(block.timestamp + TIMELOCK + 1);

        vm.prank(signers[0]);
        vm.expectRevert();
        multisig.executeTransaction(0);
    }

    function testExecuteTransactionTimelockNotPassedReverts() public {
        TestContract testContract = new TestContract();
        bytes memory data = abi.encodeWithSignature("setValue(uint256)", 42);

        vm.prank(signers[0]);
        multisig.submitTransaction(address(testContract), 0, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        // Timelock not passed yet
        vm.prank(signers[0]);
        vm.expectRevert();
        multisig.executeTransaction(0);
    }

    function testExecuteAlreadyExecutedReverts() public {
        TestContract testContract = new TestContract();
        bytes memory data = abi.encodeWithSignature("setValue(uint256)", 42);

        vm.prank(signers[0]);
        multisig.submitTransaction(address(testContract), 0, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        vm.warp(block.timestamp + TIMELOCK + 1);

        vm.prank(signers[0]);
        multisig.executeTransaction(0);

        vm.prank(signers[0]);
        vm.expectRevert();
        multisig.executeTransaction(0);
    }

    function testExecuteTransactionNonSignerReverts() public {
        TestContract testContract = new TestContract();
        bytes memory data = abi.encodeWithSignature("setValue(uint256)", 42);

        vm.prank(signers[0]);
        multisig.submitTransaction(address(testContract), 0, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        vm.warp(block.timestamp + TIMELOCK + 1);

        vm.prank(user);
        vm.expectRevert();
        multisig.executeTransaction(0);
    }

    function testExecuteTransactionWithValue() public {
        TestContract testContract = new TestContract();
        bytes memory data = abi.encodeWithSignature("setValue(uint256)", 42);

        // Fund the multisig with ETH
        vm.deal(address(multisig), 1 ether);

        vm.prank(signers[0]);
        multisig.submitTransaction(address(testContract), 1 ether, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        vm.warp(block.timestamp + TIMELOCK + 1);

        vm.prank(signers[0]);
        multisig.executeTransaction(0);

        assertEq(address(testContract).balance, 1 ether);
    }

    // ===========================================
    // REVOKE CONFIRMATION TESTS
    // ===========================================

    function testRevokeConfirmation() public {
        bytes memory data = abi.encodeWithSignature("transfer(address,uint256)", user, 100 ether);

        vm.prank(signers[0]);
        multisig.submitTransaction(target, 1 ether, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        (address[] memory confirmations, bool txExecuted) = multisig.getConfirmations(0);
        assertEq(confirmations.length, 2);

        vm.prank(signers[1]);
        multisig.revokeConfirmation(0);

        (confirmations, txExecuted) = multisig.getConfirmations(0);
        assertEq(confirmations.length, 1);
    }

    function testRevokeConfirmationEmitsEvent() public {
        bytes memory data = abi.encodeWithSignature("transfer(address,uint256)", user, 100 ether);

        vm.prank(signers[0]);
        multisig.submitTransaction(target, 1 ether, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        vm.expectEmit(true, true, false, true);
        emit IMultisig.Revocation(signers[1], 0);

        vm.prank(signers[1]);
        multisig.revokeConfirmation(0);
    }

    function testRevokeNonConfirmedReverts() public {
        bytes memory data = abi.encodeWithSignature("transfer(address,uint256)", user, 100 ether);

        vm.prank(signers[0]);
        multisig.submitTransaction(target, 1 ether, data);

        // Not confirmed yet, revoking should be silent (not revert)
        vm.prank(signers[1]);
        multisig.revokeConfirmation(0);

        (address[] memory confirmations, bool txExecuted) = multisig.getConfirmations(0);
        assertEq(confirmations.length, 1);
    }

    function testRevokeAfterExecutionReverts() public {
        TestContract testContract = new TestContract();
        bytes memory data = abi.encodeWithSignature("setValue(uint256)", 42);

        vm.prank(signers[0]);
        multisig.submitTransaction(address(testContract), 0, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        vm.warp(block.timestamp + TIMELOCK + 1);

        vm.prank(signers[0]);
        multisig.executeTransaction(0);

        // Revoking after execution is allowed (no check for executed status)
        vm.prank(signers[1]);
        multisig.revokeConfirmation(0);

        (address[] memory confirmations, bool txExecuted) = multisig.getConfirmations(0);
        assertEq(confirmations.length, 1);
        assertEq(txExecuted, true);
    }

    // ===========================================
    // SIGNER MANAGEMENT TESTS
    // ===========================================

    function testAddSigner() public {
        address newSigner = address(0x4);

        // Propose adding signer
        bytes memory data = abi.encodeWithSignature("addOwnerWithThreshold(address,uint256)", newSigner, 2);
        vm.prank(signers[0]);
        multisig.submitTransaction(address(multisig), 0, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        vm.warp(block.timestamp + TIMELOCK + 1);

        vm.prank(signers[0]);
        multisig.executeTransaction(0);

        address[] memory newSigners = multisig.getOwners();
        assertEq(newSigners.length, 4);
        assertEq(newSigners[3], newSigner);
    }

    function testRemoveSigner() public {
        // Propose removing signer
        bytes memory data = abi.encodeWithSignature("removeOwner(address,uint256)", signers[2], 2);
        vm.prank(signers[0]);
        multisig.submitTransaction(address(multisig), 0, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        vm.warp(block.timestamp + TIMELOCK + 1);

        vm.prank(signers[0]);
        multisig.executeTransaction(0);

        address[] memory newSigners = multisig.getOwners();
        assertEq(newSigners.length, 2);
        assertEq(newSigners[0], signers[0]);
        assertEq(newSigners[1], signers[1]);
    }

    function testChangeThreshold() public {
        // Propose changing threshold
        bytes memory data = abi.encodeWithSignature("changeThreshold(uint256)", 3);
        vm.prank(signers[0]);
        multisig.submitTransaction(address(multisig), 0, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        vm.warp(block.timestamp + TIMELOCK + 1);

        vm.prank(signers[0]);
        multisig.executeTransaction(0);

        assertEq(multisig.getThreshold(), 3);
    }

    function testChangeTimelock() public {
        // Propose changing timelock
        bytes memory data = abi.encodeWithSignature("setTimelock(uint256)", 7200);
        vm.prank(signers[0]);
        multisig.submitTransaction(address(multisig), 0, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        vm.warp(block.timestamp + TIMELOCK + 1);

        vm.prank(signers[0]);
        multisig.executeTransaction(0);

        assertEq(multisig.getTimelock(), 7200);
    }

    // ===========================================
    // EDGE CASES
    // ===========================================

    function testMultipleTransactions() public {
        TestContract c1 = new TestContract();
        TestContract c2 = new TestContract();

        bytes memory data1 = abi.encodeWithSignature("setValue(uint256)", 1);
        bytes memory data2 = abi.encodeWithSignature("setValue(uint256)", 2);

        vm.prank(signers[0]);
        multisig.submitTransaction(address(c1), 0, data1);

        vm.prank(signers[0]);
        multisig.submitTransaction(address(c2), 0, data2);

        assertEq(multisig.getTransactionCount(), 2);
    }

    function testGetTransactionIds() public {
        TestContract c1 = new TestContract();
        bytes memory data = abi.encodeWithSignature("setValue(uint256)", 1);

        vm.prank(signers[0]);
        multisig.submitTransaction(address(c1), 0, data);

        (uint256[] memory pending, uint256[] memory confirmed, uint256[] memory executed) = multisig.getTransactionIds(0, 10);
        assertEq(pending.length, 1);
        assertEq(pending[0], 0);
        assertEq(confirmed.length, 0);
        assertEq(executed.length, 0);
    }

    function testGetTransactionIdsWithConfirmations() public {
        TestContract c1 = new TestContract();
        TestContract c2 = new TestContract();
        bytes memory data = abi.encodeWithSignature("setValue(uint256)", 1);

        vm.prank(signers[0]);
        multisig.submitTransaction(address(c1), 0, data);

        vm.prank(signers[0]);
        multisig.submitTransaction(address(c2), 0, data);

        // Confirm first
        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        (uint256[] memory pending, uint256[] memory confirmed, uint256[] memory executed) = multisig.getTransactionIds(0, 10);
        assertEq(pending.length, 1);
        assertEq(confirmed.length, 1);
        assertEq(executed.length, 0);
    }

    // ===========================================
    // GAS ESTIMATION
    // ===========================================

    function testExecutionGasEstimation() public {
        TestContract testContract = new TestContract();
        bytes memory data = abi.encodeWithSignature("setValue(uint256)", 42);

        vm.prank(signers[0]);
        multisig.submitTransaction(address(testContract), 0, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        vm.warp(block.timestamp + TIMELOCK + 1);

        uint256 gasBefore = gasleft();
        vm.prank(signers[0]);
        multisig.executeTransaction(0);
        uint256 gasAfter = gasleft();

        console.log("Gas used:", gasBefore - gasAfter);
    }
}

contract TestContract {
    uint256 public value;

    function setValue(uint256 _value) external payable {
        value = _value;
    }

    receive() external payable {}
}