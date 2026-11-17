// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {UUPSProxy} from "../contracts/proxy/UUPSProxy.sol";
import {ProxyAdmin} from "../contracts/proxy/ProxyAdmin.sol";
import {IDRCToken} from "../contracts/token/IDRCToken.sol";
import {MultisigWallet} from "../contracts/multisig/MultisigWallet.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

contract UUPSProxyTest is Test {
    UUPSProxy proxy;
    ProxyAdmin proxyAdmin;
    IDRCToken implementation;
    MultisigWallet multisig;

    address admin = address(0x1);
    address user1 = address(0x2);
    address user2 = address(0x3);
    address[] signers = [address(0x1), address(0x2), address(0x3)];

    function setUp() public {
        vm.startPrank(admin);

        multisig = new MultisigWallet(signers, 2, 3600);

        // Deploy implementation via initialize (no constructor args)
        implementation = new IDRCToken();
        implementation.initialize("IDR Coin", "IDRC", admin, admin, admin, admin, admin, admin, 10_000_000_000 * 10**18);
        proxyAdmin = new ProxyAdmin(address(multisig));

        // Initialize proxy with token initialize function
        bytes memory initData = abi.encodeWithSignature(
            "initialize(string,string,address,address,address,address,address,address,uint256)",
            "IDR Coin", "IDRC", admin, admin, admin, admin, admin, admin, 10_000_000_000 * 10**18
        );
        proxy = new UUPSProxy(address(implementation), initData);

        vm.stopPrank();
    }

    // ===========================================
    // INITIALIZATION TESTS
    // ===========================================

    function testProxyDeployment() public {
        // Verify proxy implementation is set correctly
        assertEq(proxy.implementation(), address(implementation));
        // Verify proxyAdmin is owner of itself
        assertEq(proxyAdmin.owner(), address(multisig));
    }

    function testProxyDelegateCall() public {
        IDRCToken token = IDRCToken(address(proxy));

        assertEq(token.name(), "IDR Coin");
        assertEq(token.symbol(), "IDRC");
        assertEq(token.decimals(), 18);
    }

    function testProxyStoragePersistence() public {
        IDRCToken token = IDRCToken(address(proxy));

        // Grant minter role to admin
        bytes32 MINTER_ROLE = token.MINTER_ROLE();
        vm.prank(admin);
        token.grantRole(MINTER_ROLE, admin);

        // Mint some tokens
        vm.prank(admin);
        token.mint(user1, 1000 ether);

        assertEq(token.balanceOf(user1), 1000 ether);
        assertEq(token.totalSupply(), 1000 ether);
    }

    // ===========================================
    // FALLBACK TESTS
    // ===========================================

    function testFallbackToImplementation() public {
        IDRCToken token = IDRCToken(address(proxy));

        bytes32 MINTER_ROLE = token.MINTER_ROLE();
        vm.prank(admin);
        token.grantRole(MINTER_ROLE, admin);

        // Call mint via fallback (direct call to proxy)
        vm.prank(admin);
        (bool success, ) = address(proxy).call(abi.encodeWithSignature("mint(address,uint256)", user1, 500 ether));
        assertEq(success, true);

        assertEq(token.balanceOf(user1), 500 ether);
    }

    // ===========================================
    // PROXY ADMIN TESTS
    // ===========================================

    function testProxyAdminOwnership() public {
        assertEq(proxyAdmin.owner(), address(multisig));
    }

    // ===========================================
    // UPGRADE TESTS (test the upgrade mechanism directly on proxy)
    // ===========================================

    function testUpgradeToZeroAddressReverts() public {
        vm.prank(admin);
        vm.expectRevert(); // UUPSProxy: zero address implementation
        proxy.upgradeTo(address(0));
    }

    function testNonUpgraderCannotUpgrade() public {
        // Deploy V2
        IDRCToken implementationV2 = new IDRCToken();
        implementationV2.initialize("IDR Coin", "IDRC", admin, admin, admin, admin, admin, admin, 10_000_000_000 * 10**18);

        // user1 doesn't have UPGRADER_ROLE
        vm.prank(user1);
        vm.expectRevert(); // AccessControlMissingRole
        proxy.upgradeTo(address(implementationV2));
    }
}

// Mock contracts for testing
contract ProofOfReserve {
    function initialize(address, address, address) external {}
}

contract BridgeVault {
    function initialize(address, address, address, address, uint256) external {}
}

contract BridgeRelayer {
    function initialize(address, address, address, address) external {}
}