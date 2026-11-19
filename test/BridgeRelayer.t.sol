// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {BridgeRelayer} from "../contracts/bridge/BridgeRelayer.sol";
import {IDRCToken} from "../contracts/token/IDRCToken.sol";
import {IBridgeRelayer} from "../contracts/interfaces/IBridge.sol";

contract BridgeRelayerTest is Test {
    BridgeRelayer relayerContract;
    IDRCToken token;

    address admin = address(0x1);
    address relayer = address(0x2);
    address user1 = address(0x10);
    address user2 = address(0x11);

    function setUp() public {
        vm.startPrank(admin);

        // Deploy token via initialize
        token = new IDRCToken();
        token.initialize("IDR Coin", "IDRC", admin, admin, admin, admin, admin, admin, 10_000_000_000 * 10**18);

        // Deploy relayer
        relayerContract = new BridgeRelayer(relayer);

        // Grant minter role to relayer contract (so it can mint)
        bytes32 MINTER_ROLE = token.MINTER_ROLE();
        token.grantRole(MINTER_ROLE, address(relayerContract));

        vm.stopPrank();
    }

    // ===========================================
    // INITIALIZATION TESTS
    // ===========================================

    function testInitialization() public {
        assertEq(relayerContract.relayer(), relayer);
        assertEq(relayerContract.hasRole(relayerContract.RELAYER_ADMIN_ROLE(), relayer), true);
    }

    // ===========================================
    // RELAY MESSAGE TESTS
    // ===========================================

    function testRelayMint() public {
        vm.prank(relayer);
        relayerContract.relay(1, 1, 2, user1, 500 ether, address(token));

        assertEq(token.balanceOf(user1), 500 ether);
    }

    function testRelayMintEmitsEvent() public {
        vm.expectEmit(true, true, false, true);
        emit IBridgeRelayer.MessageRelayed(1, 1, 2, user1, 500 ether);

        vm.prank(relayer);
        relayerContract.relay(1, 1, 2, user1, 500 ether, address(token));
    }

    function testRelayMintNonRelayerReverts() public {
        vm.prank(user1);
        vm.expectRevert();
        relayerContract.relay(1, 1, 2, user1, 500 ether, address(token));
    }

    function testRelayMintReplayProtection() public {
        vm.prank(relayer);
        relayerContract.relay(1, 1, 2, user1, 500 ether, address(token));

        vm.prank(relayer);
        vm.expectRevert();
        relayerContract.relay(1, 1, 2, user1, 500 ether, address(token));
    }

    function testRelayZeroAddressReverts() public {
        vm.prank(relayer);
        vm.expectRevert(BridgeRelayer.ZeroAddress.selector);
        relayerContract.relay(1, 1, 2, address(0), 500 ether, address(token));
    }

    function testRelayZeroAmountReverts() public {
        vm.prank(relayer);
        vm.expectRevert(BridgeRelayer.InvalidAmount.selector);
        relayerContract.relay(1, 1, 2, user1, 0, address(token));
    }

    function testRelayWhenPaused() public {
        vm.prank(relayer);
        relayerContract.pause();

        vm.prank(relayer);
        vm.expectRevert(); // EnforcedPause from Pausable
        relayerContract.relay(1, 1, 2, user1, 500 ether, address(token));
    }

    // ===========================================
    // PROCESSED MESSAGES VIEW TESTS
    // ===========================================

    function testProcessedMessages() public {
        assertEq(relayerContract.processedMessages(1, 1), false);

        vm.prank(relayer);
        relayerContract.relay(1, 1, 2, user1, 500 ether, address(token));

        assertEq(relayerContract.processedMessages(1, 1), true);
    }

    // ===========================================
    // ADMIN FUNCTIONS TESTS
    // ===========================================

    function testSetRelayer() public {
        address newRelayer = address(0x3);

        vm.prank(relayer);
        relayerContract.setRelayer(newRelayer);

        assertEq(relayerContract.relayer(), newRelayer);
        assertEq(relayerContract.hasRole(relayerContract.RELAYER_ADMIN_ROLE(), newRelayer), true);
        assertEq(relayerContract.hasRole(relayerContract.RELAYER_ADMIN_ROLE(), relayer), false);
    }

    function testSetRelayerZeroAddressReverts() public {
        vm.prank(relayer);
        vm.expectRevert(BridgeRelayer.ZeroAddress.selector);
        relayerContract.setRelayer(address(0));
    }

    function testSetRelayerNonAdminReverts() public {
        vm.prank(user1);
        vm.expectRevert();
        relayerContract.setRelayer(address(0x3));
    }

    function testPauseUnpause() public {
        assertEq(relayerContract.paused(), false);

        vm.prank(relayer);
        relayerContract.pause();
        assertEq(relayerContract.paused(), true);

        vm.prank(relayer);
        relayerContract.unpause();
        assertEq(relayerContract.paused(), false);
    }

    function testPauseNonAdminReverts() public {
        vm.prank(user1);
        vm.expectRevert();
        relayerContract.pause();
    }
}
