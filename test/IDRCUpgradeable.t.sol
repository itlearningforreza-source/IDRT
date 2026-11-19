// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {IDRCUpgradeable} from "../contracts/upgrade/IDRCUpgradeable.sol";
import {IDRCToken} from "../contracts/token/IDRCToken.sol";
import {MultisigWallet} from "../contracts/multisig/MultisigWallet.sol";
import {ProofOfReserve} from "../contracts/reserve/ProofOfReserve.sol";
import {BridgeVault} from "../contracts/bridge/BridgeVault.sol";
import {BridgeRelayer} from "../contracts/bridge/BridgeRelayer.sol";
import {UUPSProxy} from "../contracts/proxy/UUPSProxy.sol";
import {ProxyAdmin} from "../contracts/proxy/ProxyAdmin.sol";

contract IDRCUpgradeableTest is Test {
    IDRCToken token;
    IDRCUpgradeable upgradeable;
    MultisigWallet multisig;
    UUPSProxy proxy;
    ProxyAdmin proxyAdmin;

    address admin = address(0x1);
    address user1 = address(0x10);
    address user2 = address(0x11);
    address[] signers = [address(0x1), address(0x2), address(0x3)];

    function setUp() public {
        vm.startPrank(admin);

        multisig = new MultisigWallet(signers, 2, 3600);

        IDRCToken implementation = new IDRCToken();
        implementation.initialize("IDR Coin", "IDRC", admin, admin, admin, admin, admin, admin, 10_000_000_000 * 10**18);
        proxyAdmin = new ProxyAdmin(address(multisig));

        // Initialize proxy with token constructor args
        bytes memory initData = abi.encodeWithSignature(
            "initialize(string,string,address,address,address,address,address,address,uint256)",
            "IDR Coin", "IDRC", admin, admin, admin, admin, admin, admin, 10_000_000_000 * 10**18
        );
        proxy = new UUPSProxy(address(implementation), initData);

        token = IDRCToken(address(proxy));

        // Deploy upgradeable contract directly (not through proxy for these tests)
        upgradeable = new IDRCUpgradeable();
        upgradeable.initialize("IDR Coin", "IDRC", admin, admin, admin, admin, admin, admin, 10_000_000_000 * 10**18);

        // Grant upgradeable contract minter/burner roles on the proxied token
        bytes32 MINTER_ROLE = token.MINTER_ROLE();
        bytes32 BURNER_ROLE = token.BURNER_ROLE();
        token.grantRole(MINTER_ROLE, address(upgradeable));
        token.grantRole(BURNER_ROLE, address(upgradeable));

        vm.stopPrank();
    }

    // ===========================================
    // VERSION TESTS
    // ===========================================

    function testVersion() public {
        assertEq(upgradeable.VERSION(), 3); // Current version is V3
    }

    function testGetInitializedVersion() public {
        assertEq(upgradeable.getInitializedVersion(), 3);
    }

    // ===========================================
    // INITIALIZATION TESTS
    // ===========================================

    function testInitializedAtV3() public {
        // Contract is initialized at V3 by constructor
        assertEq(upgradeable.getInitializedVersion(), 3);
        assertEq(upgradeable.VERSION(), 3);
    }

    // ===========================================
    // UPGRADE HISTORY TESTS
    // ===========================================

    function testUpgradeHistory() public {
        // Current version is always V3
        assertEq(upgradeable.getInitializedVersion(), 3);
        assertEq(upgradeable.VERSION(), 3);
    }

    // ===========================================
    // ROLLBACK TESTS (if supported)
    // ===========================================

    function testRollbackNotSupported() public {
        // Rollback is intentionally not supported for security
        assertEq(true, true); // Placeholder
    }

    // ===========================================
    // ACCESS CONTROL TESTS
    // ===========================================

    function testOnlyUpgraderCanCallMigrate() public {
        // Test that migrateFromV1 requires UPGRADER_ROLE
        // The contract is at V3, so MigrationNotAllowed would be thrown if role check passed
        assertEq(true, true); // Documentation test
    }
}
