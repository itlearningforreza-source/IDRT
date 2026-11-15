// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script} from "forge-std/Script.sol";
import {IDRCToken} from "../contracts/token/IDRCToken.sol";
import {UUPSProxy} from "../contracts/proxy/UUPSProxy.sol";
import {ProxyAdmin} from "../contracts/proxy/ProxyAdmin.sol";
import {console2} from "forge-std/console2.sol";

/**
 * @title UpgradeIDRC
 * @notice Upgrade script for IDRC token via UUPS proxy
 */
contract UpgradeIDRC is Script {
    string public constant TOKEN_NAME = "IDR Coin";
    string public constant TOKEN_SYMBOL = "IDRC";

    function run() external {
        address upgrader = vm.envAddress("UPGRADER");
        if (upgrader == address(0)) upgrader = vm.addr(0x1);

        address proxyAddress = vm.envAddress("PROXY_ADDRESS");
        address proxyAdminAddress = vm.envAddress("PROXY_ADMIN_ADDRESS");
        address newImplAddress = vm.envAddress("NEW_IMPL_ADDRESS");

        if (proxyAddress == address(0)) revert("PROXY_ADDRESS not set");
        if (proxyAdminAddress == address(0)) revert("PROXY_ADMIN_ADDRESS not set");
        if (newImplAddress == address(0)) revert("NEW_IMPL_ADDRESS not set");

        console2.log("========================================");
        console2.log("IDRC Upgrade Started");
        console2.log("Upgrader:", upgrader);
        console2.log("Proxy:", proxyAddress);
        console2.log("ProxyAdmin:", proxyAdminAddress);
        console2.log("New Implementation:", newImplAddress);
        console2.log("========================================");

        // Option 1: Upgrade via ProxyAdmin (recommended for multisig)
        vm.startBroadcast(upgrader);
        ProxyAdmin proxyAdmin = ProxyAdmin(proxyAdminAddress);
        proxyAdmin.upgrade(proxyAddress, newImplAddress);
        vm.stopBroadcast();

        // Option 2: Direct proxy upgrade (if upgrader has UPGRADER_ROLE)
        // vm.startBroadcast(upgrader);
        // UUPSProxy proxy = UUPSProxy(proxyAddress);
        // proxy.upgradeTo(newImplAddress);
        // vm.stopBroadcast();

        // Verify upgrade
        IDRCToken token = IDRCToken(proxyAddress);

        console2.log("\n========================================");
        console2.log("UPGRADE VERIFICATION");
        console2.log("========================================");
        // Get implementation from ERC1967 slot
        bytes32 implSlot = 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;
        bytes32 implBytes;
        assembly {
            implBytes := sload(implSlot)
            // Mask to extract 20-byte address from 32-byte slot
            implBytes := and(implBytes, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF)
        }
        // Return the implementation address via assembly
        address newImpl;
        assembly {
            newImpl := implBytes
        }
        console2.log("New Implementation:", newImpl);
        console2.log("Token Name:", token.name());
        console2.log("Token Symbol:", token.symbol());
        console2.log("Total Supply:", token.totalSupply());
        console2.log("Paused:", token.paused());
        console2.log("========================================");

        assert(newImpl == newImplAddress);
        assert(keccak256(bytes(token.name())) == keccak256(bytes(TOKEN_NAME)));
        assert(keccak256(bytes(token.symbol())) == keccak256(bytes(TOKEN_SYMBOL)));
        console2.log("[OK] Upgrade verified successfully");
    }
}