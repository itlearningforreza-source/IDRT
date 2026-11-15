// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {BridgeVault} from "../contracts/bridge/BridgeVault.sol";
import {IDRCToken} from "../contracts/token/IDRCToken.sol";
import {IBridgeVault} from "../contracts/interfaces/IBridge.sol";
import {AccessControl} from "../contracts/access/AccessControl.sol";

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

        // Deploy token
        token = new IDRCToken(
            "IDR Coin", "IDRC",
            admin, admin, admin, admin, admin, admin,
            10_000_000_000 * 10**18
        );

        // Deploy vault
        vault = new BridgeVault(CHAIN_ID, relayer);

        // Grant minter/burner roles to vault (so it can burn/mint)
        bytes32 MINTER_ROLE = token.MINTER_ROLE();
        bytes32 BURNER_ROLE = token.BURNER_ROLE();
        token.grantRole(MINTER_ROLE, address(vault));
        token.grantRole(BURNER_ROLE, address(vault));

        vm.stopPrank();
    }

    function _mintViaAdmin(address to, uint256 amount) internal {
        vm.prank(admin);
        token.mint(to, amount);
    }

    // ===========================================
    // INITIALIZATION TESTS
    // ===========================================

    function testInitialization() public {
        assertEq(vault.chainId(), CHAIN_ID);
        assertEq(vault.relayer(), relayer);
        assertEq(vault.paused(), false);
        assertEq(vault.hasRole(vault.RELAYER_ROLE(), relayer), true);
    }

    // ===========================================
    // LOCK (BURN ON SOURCE) TESTS
    // ===========================================

    function testLock() public {
        _mintViaAdmin(user1, 1000 ether);

        vm.prank(relayer);
        uint256 nonce = vault.lock(address(token), user1, user2, 500 ether, 137); // Polygon

        assertEq(token.balanceOf(user1), 500 ether);
        assertEq(token.totalSupply(), 500 ether);
        assertEq(nonce, 1);
        assertEq(vault.lockedAmount(1), 500 ether);
    }

    function testLockEmitsEvent() public {
        _mintViaAdmin(user1, 1000 ether);

        vm.expectEmit(true, true, false, true);
        emit IBridgeVault.TokensLocked(1, user1, user2, 500 ether, 137);

        vm.prank(relayer);
        vault.lock(address(token), user1, user2, 500 ether, 137);
    }

    function testLockNonRelayerReverts() public {
        _mintViaAdmin(user1, 1000 ether);

        vm.prank(user1);
        vm.expectRevert();
        vault.lock(address(token), user1, user2, 500 ether, 137);
    }

    function testLockZeroAddressReverts() public {
        vm.prank(relayer);
        vm.expectRevert(BridgeVault.ZeroAddress.selector);
        vault.lock(address(token), address(0), user2, 500 ether, 137);
    }

    function testLockZeroAmountReverts() public {
        vm.prank(relayer);
        vm.expectRevert(BridgeVault.ZeroAmount.selector);
        vault.lock(address(token), user1, user2, 0, 137);
    }

    function testLockSameChainReverts() public {
        vm.prank(relayer);
        vm.expectRevert();
        vault.lock(address(token), user1, user2, 500 ether, CHAIN_ID);
    }

    function testLockWhenPausedReverts() public {
        _mintViaAdmin(user1, 1000 ether);

        vm.prank(admin);
        vault.pause();

        vm.prank(relayer);
        vm.expectRevert(); // EnforcedPause from Pausable
        vault.lock(address(token), user1, user2, 500 ether, 137);
    }

    // ===========================================
    // RELEASE (MINT ON SOURCE - REVERSE BRIDGE) TESTS
    // ===========================================

    function testRelease() public {
        _mintViaAdmin(user1, 1000 ether);

        vm.prank(relayer);
        vault.lock(address(token), user1, user2, 500 ether, 137);

        vm.prank(relayer);
        vault.release(address(token), 1, user1);

        assertEq(token.balanceOf(user1), 1000 ether);
        assertEq(vault.isNonceProcessed(1), true);
    }

    function testReleaseEmitsEvent() public {
        _mintViaAdmin(user1, 1000 ether);

        vm.prank(relayer);
        vault.lock(address(token), user1, user2, 500 ether, 137);

        vm.expectEmit(true, true, false, true);
        emit IBridgeVault.TokensReleased(1, user1, 500 ether);

        vm.prank(relayer);
        vault.release(address(token), 1, user1);
    }

    function testReleaseNonRelayerReverts() public {
        vm.prank(user1);
        vm.expectRevert();
        vault.release(address(token), 1, user1);
    }

    function testReleaseNonExistentNonceReverts() public {
        vm.prank(relayer);
        vm.expectRevert();
        vault.release(address(token), 999, user1);
    }

    function testReleaseAlreadyProcessedReverts() public {
        _mintViaAdmin(user1, 1000 ether);

        vm.prank(relayer);
        vault.lock(address(token), user1, user2, 500 ether, 137);

        vm.prank(relayer);
        vault.release(address(token), 1, user1);

        vm.prank(relayer);
        vm.expectRevert();
        vault.release(address(token), 1, user1);
    }

    function testReleaseZeroAddressReverts() public {
        vm.prank(relayer);
        vm.expectRevert(BridgeVault.ZeroAddress.selector);
        vault.release(address(token), 1, address(0));
    }

    function testReleaseWhenPausedReverts() public {
        _mintViaAdmin(user1, 1000 ether);

        vm.prank(relayer);
        vault.lock(address(token), user1, user2, 500 ether, 137);

        vm.prank(admin);
        vault.pause();

        vm.prank(relayer);
        vm.expectRevert(); // EnforcedPause from Pausable
        vault.release(address(token), 1, user1);
    }

    // ===========================================
    // VIEW FUNCTION TESTS
    // ===========================================

    function testTotalLocked() public {
        assertEq(vault.totalLocked(), 0);

        _mintViaAdmin(user1, 1000 ether);

        vm.prank(relayer);
        vault.lock(address(token), user1, user2, 500 ether, 137);

        assertEq(vault.totalLocked(), 500 ether);

        vm.prank(relayer);
        vault.release(address(token), 1, user1);

        assertEq(vault.totalLocked(), 0);
    }

    function testIsNonceProcessed() public {
        assertEq(vault.isNonceProcessed(1), false);

        _mintViaAdmin(user1, 1000 ether);

        vm.prank(relayer);
        vault.lock(address(token), user1, user2, 500 ether, 137);

        assertEq(vault.isNonceProcessed(1), false);

        vm.prank(relayer);
        vault.release(address(token), 1, user1);

        assertEq(vault.isNonceProcessed(1), true);
    }

    function testLockedAmount() public {
        assertEq(vault.lockedAmount(1), 0);

        _mintViaAdmin(user1, 1000 ether);

        vm.prank(relayer);
        vault.lock(address(token), user1, user2, 500 ether, 137);

        assertEq(vault.lockedAmount(1), 500 ether);
    }

    // ===========================================
    // ADMIN FUNCTIONS TESTS
    // ===========================================

    function testSetRelayer() public {
        address newRelayer = address(0x3);

        vm.prank(admin);
        vault.setRelayer(newRelayer);

        assertEq(vault.hasRole(vault.RELAYER_ROLE(), newRelayer), true);
    }

    function testSetRelayerZeroAddressReverts() public {
        vm.prank(admin);
        vm.expectRevert(BridgeVault.ZeroAddress.selector);
        vault.setRelayer(address(0));
    }

    function testPauseUnpause() public {
        assertEq(vault.paused(), false);

        vm.prank(admin);
        vault.pause();
        assertEq(vault.paused(), true);

        vm.prank(admin);
        vault.unpause();
        assertEq(vault.paused(), false);
    }

    function testPauseNonAdminReverts() public {
        vm.prank(user1);
        vm.expectRevert();
        vault.pause();
    }

    // ===========================================
    // EDGE CASES
    // ===========================================

    function testMultipleLocksAndReleases() public {
        _mintViaAdmin(user1, 10000 ether);

        for (uint i = 0; i < 5; i++) {
            vm.prank(relayer);
            vault.lock(address(token), user1, user2, 1000 ether, 137);
        }

        assertEq(token.balanceOf(user1), 5000 ether);
        assertEq(vault.totalLocked(), 5000 ether);

        for (uint i = 1; i <= 5; i++) {
            vm.prank(relayer);
            vault.release(address(token), i, user1);
        }

        assertEq(token.balanceOf(user1), 10000 ether);
        assertEq(vault.totalLocked(), 0);
    }

    function testMultipleChains() public {
        _mintViaAdmin(user1, 10000 ether);

        vm.prank(relayer);
        vault.lock(address(token), user1, user2, 2000 ether, 137);   // Polygon
        vm.prank(relayer);
        vault.lock(address(token), user1, user2, 3000 ether, 42161); // Arbitrum

        assertEq(vault.totalLocked(), 5000 ether);
    }
}