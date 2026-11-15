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
    IDRCToken implementationV2;
    MultisigWallet multisig;

    address admin = address(0x1);
    address user1 = address(0x2);
    address user2 = address(0x3);
    address[] signers = [address(0x1), address(0x2), address(0x3)];

    function setUp() public {
        vm.startPrank(admin);

        multisig = new MultisigWallet(signers, 2, 3600);

        implementation = new IDRCToken("IDR Coin", "IDRC", admin, admin, admin, admin, admin, admin, 10_000_000_000 * 10**18);
        proxyAdmin = new ProxyAdmin(address(multisig));

        // Initialize proxy with token constructor args
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
        assertEq(address(proxy.implementation()), address(implementation));
        assertEq(proxyAdmin.getAdmin(address(proxy)), address(proxyAdmin));
    }

    function testProxyDelegateCall() public {
        IDRCToken token = IDRCToken(address(proxy));

        assertEq(token.name(), "IDR Coin");
        assertEq(token.symbol(), "IDRC");
        assertEq(token.decimals(), 18);
    }

    function testProxyStoragePersistence() public {
        IDRCToken token = IDRCToken(address(proxy));

        // Mint some tokens
        bytes32 MINTER_ROLE = token.MINTER_ROLE();
        token.grantRole(MINTER_ROLE, admin);

        vm.prank(admin);
        token.mint(user1, 1000 ether);

        assertEq(token.balanceOf(user1), 1000 ether);
        assertEq(token.totalSupply(), 1000 ether);
    }

    // ===========================================
    // UPGRADE TESTS
    // ===========================================

    function testUpgrade() public {
        IDRCToken token = IDRCToken(address(proxy));

        // Deploy V2
        implementationV2 = new IDRCToken("IDR Coin", "IDRC", admin, admin, admin, admin, admin, admin, 10_000_000_000 * 10**18);

        // Upgrade via proxyAdmin (owned by multisig)
        // Need to execute through multisig
        bytes memory data = abi.encodeWithSignature("upgradeTo(address)", address(implementationV2));

        vm.prank(signers[0]);
        multisig.submitTransaction(address(proxyAdmin), 0, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        vm.warp(block.timestamp + 3600 + 1);

        vm.prank(signers[2]);
        multisig.executeTransaction(0);

        // Verify implementation changed
        assertEq(address(proxy.implementation()), address(implementationV2));

        // Verify storage persisted
        assertEq(token.balanceOf(user1), 1000 ether);
        assertEq(token.totalSupply(), 1000 ether);
    }

    function testUpgradeViaProxyAdminDirectly() public {
        // ProxyAdmin owner (multisig) can upgrade directly
        implementationV2 = new IDRCToken("IDR Coin", "IDRC", admin, admin, admin, admin, admin, admin, 10_000_000_000 * 10**18);

        // This would fail because proxyAdmin is owned by multisig
        // Test shows only multisig can upgrade
        vm.prank(admin);
        vm.expectRevert(Ownable.OwnableUnauthorizedAccount.selector);
        proxyAdmin.upgrade(address(proxy), address(implementationV2));
    }

    // ===========================================
    // ADMIN TESTS
    // ===========================================

    function testChangeAdmin() public {
        address newAdmin = address(0x4);

        // Change admin via multisig
        bytes memory data = abi.encodeWithSignature("changeAdmin(address)", newAdmin);

        vm.prank(signers[0]);
        multisig.submitTransaction(address(proxyAdmin), 0, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        vm.warp(block.timestamp + 3600 + 1);

        vm.prank(signers[2]);
        multisig.executeTransaction(0);

        assertEq(proxyAdmin.getAdmin(address(proxy)), newAdmin);
    }

    // ===========================================
    // FALLBACK TESTS
    // ===========================================

    function testFallbackToImplementation() public {
        IDRCToken token = IDRCToken(address(proxy));

        bytes32 MINTER_ROLE = token.MINTER_ROLE();
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

    function testProxyAdminGetProxyImplementation() public {
        assertEq(proxyAdmin.getImplementation(address(proxy)), address(implementation));
    }

    function testProxyAdminGetProxyAdmin() public {
        assertEq(proxyAdmin.getAdmin(address(proxy)), address(proxyAdmin));
    }

    // ===========================================
    // EDGE CASES
    // ===========================================

    function testMultipleUpgrades() public {
        IDRCToken token = IDRCToken(address(proxy));

        bytes32 MINTER_ROLE = token.MINTER_ROLE();
        token.grantRole(MINTER_ROLE, admin);

        vm.prank(admin);
        token.mint(user1, 1000 ether);

        // Upgrade 3 times
        for (uint i = 0; i < 3; i++) {
            IDRCToken newImpl = new IDRCToken("IDR Coin", "IDRC", admin, admin, admin, admin, admin, admin, 10_000_000_000 * 10**18);

            bytes memory data = abi.encodeWithSignature("upgradeTo(address)", address(newImpl));

            vm.prank(signers[0]);
            multisig.submitTransaction(address(proxyAdmin), 0, data);

            vm.prank(signers[1]);
            multisig.confirmTransaction(0);

            vm.warp(block.timestamp + 3600 + 1);

            vm.prank(signers[2]);
            multisig.executeTransaction(0);

            assertEq(address(proxy.implementation()), address(newImpl));
            assertEq(token.balanceOf(user1), 1000 ether);
        }
    }

    function testUpgradeToZeroAddressReverts() public {
        bytes memory data = abi.encodeWithSignature("upgradeTo(address)", address(0));

        vm.prank(signers[0]);
        multisig.submitTransaction(address(proxyAdmin), 0, data);

        vm.prank(signers[1]);
        multisig.confirmTransaction(0);

        vm.warp(block.timestamp + 3600 + 1);

        vm.prank(signers[2]);
        vm.expectRevert(); // ERC1967InvalidImplementation or similar
        multisig.executeTransaction(0);
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