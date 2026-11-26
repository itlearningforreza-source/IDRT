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
    address verifier = address(0x4);
    address user1 = address(0x10);
    address user2 = address(0x11);

    function setUp() public {
        vm.startPrank(admin);
        token = new IDRCToken();
        token.initialize("IDR Coin", "IDRC", admin, admin, admin, admin, admin, admin, 10_000_000_000 * 10**18);
        relayerContract = new BridgeRelayer(relayer);
        token.grantRole(token.MINTER_ROLE(), address(relayerContract));

        vm.startPrank(relayer); // constructor granted DEFAULT_ADMIN_ROLE to relayer
        relayerContract.setVerifier(verifier);
        relayerContract.setTokenAllowlist(address(token), true);
        vm.stopPrank();
    }

    function _relay(bytes32 messageId, address recipient, uint256 amount) internal {
        vm.prank(verifier);
        relayerContract.relay(
            1, block.chainid, address(0x100), address(relayerContract), address(token), user1, recipient, amount, messageId
        );
    }

    function testRelayMint() public {
        _relay(bytes32(uint256(1)), user1, 500 ether);
        assertEq(token.balanceOf(user1), 500 ether);
        assertTrue(relayerContract.isMessageExecuted(bytes32(uint256(1))));
    }

    // ============ EXPLOIT REPRO B/C: arbitrary minting ============
    function testReproC_RelayerCannotRelayWithoutVerifier() public {
        // Old model: any RELAYER_ADMIN could call relay(...) directly.
        // New model: only the trusted verifier can relay.
        vm.prank(relayer);
        vm.expectRevert(BridgeRelayer.OnlyVerifierAllowed.selector);
        relayerContract.relay(1, 2, address(0), address(relayerContract), address(token), user1, user2, 100 ether, bytes32(uint256(1)));
    }

    // ============ Replay ============
    function testRelayReplayProtection() public {
        _relay(bytes32(uint256(2)), user1, 100 ether);
        vm.prank(verifier);
        vm.expectRevert(abi.encodeWithSelector(BridgeRelayer.MessageAlreadyProcessed.selector, bytes32(uint256(2))));
        relayerContract.relay(1, block.chainid, address(0x100), address(relayerContract), address(token), user1, user1, 100 ether, bytes32(uint256(2)));
    }

    // ============ Wrong chain ============
    function testReproD_WrongDestinationChainReverts() public {
        vm.prank(verifier);
        vm.expectRevert(BridgeRelayer.IncorrectDestinationChain.selector);
        relayerContract.relay(1, block.chainid + 1, address(0x100), address(relayerContract), address(token), user1, user2, 100 ether, bytes32(uint256(3)));
    }

    function testRelayToWrongDestinationBridgeReverts() public {
        vm.prank(verifier);
        vm.expectRevert(BridgeRelayer.IncorrectDestinationBridge.selector);
        relayerContract.relay(1, block.chainid, address(0x100), address(admin), address(token), user1, user2, 100 ether, bytes32(uint256(9)));
    }

    // ============ Unallowlisted token ============
    function testReproArbitraryTokenReverts() public {
        address evilToken = address(0x99);
        vm.startPrank(relayer);
        relayerContract.setTokenAllowlist(evilToken, false);
        vm.stopPrank();
        vm.prank(verifier);
        vm.expectRevert(BridgeRelayer.UnauthorizedToken.selector);
        relayerContract.relay(1, block.chainid, address(0x100), address(relayerContract), evilToken, user1, user2, 100 ether, bytes32(uint256(4)));
    }

    function testZeroAmountReverts() public {
        vm.prank(verifier);
        vm.expectRevert(BridgeRelayer.InvalidAmount.selector);
        relayerContract.relay(1, 2, address(0x100), address(relayerContract), address(token), user1, user2, 0, bytes32(uint256(5)));
    }

    function testSetVerifierZeroReverts() public {
        vm.prank(relayer);
        vm.expectRevert();
        relayerContract.setVerifier(address(0));
    }

    // ============ Admin ============
    function testSetRelayer() public {
        vm.prank(relayer);
        relayerContract.setRelayer(address(0x3));
        assertEq(relayerContract.relayer(), address(0x3));
    }
}
