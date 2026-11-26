// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {BridgeVault} from "../contracts/bridge/BridgeVault.sol";
import {IDRCToken} from "../contracts/token/IDRCToken.sol";
import {IBridgeVault} from "../contracts/interfaces/IBridge.sol";

contract BridgeVaultTest is Test {
    BridgeVault vault;
    IDRCToken token;

    address admin = address(0x1);
    address relayer = address(0x2);
    address user1 = address(0x10);
    address user2 = address(0x11);
    uint256 constant CHAIN_ID = 1; // Ethereum mainnet

    function setUp() public {
        vm.startPrank(admin);
        token = new IDRCToken();
        token.initialize("IDR Coin", "IDRC", admin, admin, admin, admin, admin, admin, 10_000_000_000 * 10**18);
        vault = new BridgeVault(CHAIN_ID, relayer);
        token.grantRole(token.MINTER_ROLE(), address(vault));
        token.grantRole(token.BURNER_ROLE(), address(vault));
        vm.stopPrank();
        vm.startPrank(relayer);
        vault.setDestinationBridge(user2);
        vm.stopPrank();
    }

    function _mintViaAdmin(address to, uint256 amount) internal {
        vm.prank(admin);
        token.mint(to, amount);
    }

    function _approve(address user, uint256 amount) internal {
        vm.prank(user);
        token.approve(address(vault), amount);
    }

    function testLock() public {
        _mintViaAdmin(user1, 1000 ether);
        _approve(user1, 500 ether);

        vm.prank(user1); // The user locks; relayer cannot do it on their behalf
        uint256 nonce = vault.lock(address(token), user2, 500 ether, 137);

        assertEq(token.balanceOf(user1), 500 ether); // burned into vault
        assertEq(token.balanceOf(address(vault)), 500 ether);
        assertEq(nonce, 1);
        assertEq(vault.lockedAmount(1), 500 ether);
    }

    function testLockWithoutAllowanceReverts() public {
        _mintViaAdmin(user1, 1000 ether);
        vm.prank(user1);
        vm.expectRevert();
        vault.lock(address(token), user2, 500 ether, 137);
    }

    function testLockZeroAddressReverts() public {
        vm.prank(user1);
        vm.expectRevert(BridgeVault.UnauthorizedRecipient.selector);
        vault.lock(address(token), address(0), 500 ether, 137);
    }

    function testLockZeroAmountReverts() public {
        vm.prank(user1);
        vm.expectRevert(BridgeVault.ZeroAmount.selector);
        vault.lock(address(token), user2, 0, 137);
    }

    function testLockSameChainReverts() public {
        vm.prank(user1);
        vm.expectRevert(abi.encodeWithSelector(BridgeVault.SameChain.selector, CHAIN_ID));
        vault.lock(address(token), user2, 500 ether, CHAIN_ID);
    }

    function testLockWhenPausedReverts() public {
        _mintViaAdmin(user1, 1000 ether);
        _approve(user1, 500 ether);
        vm.startPrank(relayer);
        vault.pause();
        vm.stopPrank();
        vm.prank(user1);
        vm.expectRevert();
        vault.lock(address(token), user2, 500 ether, 137);
        vm.startPrank(relayer);
        vault.unpause();
        vm.stopPrank();
    }

    // ============ EXPLOIT REPRO A: unauthorized burn of another user ============
    function testReproA_RelayerCannotBurnArbitraryUser() public {
        // Old model: relayer could call issuerBurn(user1). New model: lock()
        // has no sender param; only the vault moves funds via transferFrom(msg.sender).
        _mintViaAdmin(user1, 1000 ether);

        vm.prank(relayer); // an attacker with relayer role tries the old path
        (bool ok, ) = address(vault).call(
            abi.encodeWithSignature("lock(address,address,uint256,uint256)", address(token), user2, 500 ether, 137)
        );
        assertFalse(ok); // reverts: no allowance from relayer

        assertEq(token.balanceOf(user1), 1000 ether);
        assertEq(token.totalSupply(), 1000 ether);
    }

    // ============ RELEASE (REVERSE BRIDGE) ============
    function testRelease() public {
        _mintViaAdmin(user1, 1000 ether);
        _approve(user1, 500 ether);
        vm.prank(user1);
        vault.lock(address(token), user2, 500 ether, 137);
        vm.prank(relayer);
        vault.release(address(token), 1, user1);
        assertEq(token.balanceOf(user1), 1000 ether);
        assertEq(vault.isNonceProcessed(1), true);
    }

    function testReleaseDuplicateReverts() public {
        _mintViaAdmin(user1, 1000 ether);
        _approve(user1, 500 ether);
        vm.prank(user1);
        vault.lock(address(token), user2, 500 ether, 137);
        vm.prank(relayer);
        vault.release(address(token), 1, user1);
        vm.prank(relayer);
        vm.expectRevert(abi.encodeWithSelector(BridgeVault.NonceAlreadyProcessed.selector, 1));
        vault.release(address(token), 1, user1);
    }

    function testReleaseNonExistentReverts() public {
        vm.prank(relayer);
        vm.expectRevert(abi.encodeWithSelector(BridgeVault.NonceNotFound.selector, 999));
        vault.release(address(token), 999, user1);
    }

    // ============ INVARIANTS ============
    function testInvariant_TotalLockedConsistency() public {
        _mintViaAdmin(user1, 10000 ether);
        _approve(user1, 5000 ether);
        for (uint i = 0; i < 5; i++) {
            vm.prank(user1);
            vault.lock(address(token), user2, 1000 ether, 137);
        }
        assertEq(token.balanceOf(address(vault)), 5000 ether);
        assertEq(vault.totalLocked(), 5000 ether);
    }

    function testInvariant_MessageAccounting() public {
        _mintViaAdmin(user1, 1000 ether);
        _approve(user1, 500 ether);
        vm.prank(user1);
        uint256 nonce = vault.lock(address(token), user2, 500 ether, 137);
        BridgeVault.BridgeMessage memory msg_ = vault.bridgeMessage(nonce);
        assertEq(msg_.sourceChainId, CHAIN_ID);
        assertEq(msg_.destinationChainId, 137);
        assertEq(msg_.token, address(token));
        assertEq(msg_.sender, user1);
        assertEq(msg_.recipient, user2);
        assertEq(msg_.amount, 500 ether);
        assertEq(msg_.nonce, nonce);
    }

    // ============ ADMIN ============
    function testSetRelayer() public {
        vm.startPrank(relayer);
        vault.setRelayer(address(0x3));
        vm.stopPrank();
        assertEq(vault.relayer(), address(0x3));
        assertEq(vault.hasRole(vault.RELAYER_ROLE(), address(0x3)), true);
    }

    function testSetRelayerZeroReverts() public {
        vm.startPrank(relayer);
        vm.expectRevert();
        vault.setRelayer(address(0));
        vm.stopPrank();
    }
}
