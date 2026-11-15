// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script} from "forge-std/Script.sol";
import {IDRCToken} from "../contracts/token/IDRCToken.sol";
import {MultisigWallet} from "../contracts/multisig/MultisigWallet.sol";
import {ProofOfReserve} from "../contracts/reserve/ProofOfReserve.sol";
import {BridgeVault} from "../contracts/bridge/BridgeVault.sol";
import {BridgeRelayer} from "../contracts/bridge/BridgeRelayer.sol";
import {ProxyAdmin} from "../contracts/proxy/ProxyAdmin.sol";
import {UUPSProxy} from "../contracts/proxy/UUPSProxy.sol";
import {console2} from "forge-std/console2.sol";

/**
 * @title VerifyContracts
 * @notice Verification script for Etherscan/Blockscout
 */
contract VerifyContracts is Script {
    function run() external {
        console2.log("========================================");
        console2.log("CONTRACT VERIFICATION");
        console2.log("========================================");

        // Get addresses from environment
        address tokenProxy = vm.envAddress("TOKEN_PROXY_ADDRESS");
        address tokenImpl = vm.envAddress("TOKEN_IMPL_ADDRESS");
        address multisigAddr = vm.envAddress("MULTISIG_ADDRESS");
        address reserveAddr = vm.envAddress("RESERVE_ADDRESS");
        address proxyAdminAddr = vm.envAddress("PROXY_ADMIN_ADDRESS");
        address relayerAddr = vm.envAddress("RELAYER_ADDRESS");
        address vaultAddr = vm.envAddress("VAULT_ADDRESS");

        // Verify IDRCToken implementation
        if (tokenImpl != address(0)) {
            console2.log("\nVerifying IDRCToken implementation at:", tokenImpl);
            // forge verify-contract --chain-id <chain> <address> contracts/token/IDRCToken.sol:IDRCToken
        }

        // Verify UUPS Proxy
        if (tokenProxy != address(0)) {
            console2.log("\nVerifying UUPS Proxy at:", tokenProxy);
            // forge verify-contract --chain-id <chain> <address> contracts/proxy/UUPSProxy.sol:UUPSProxy
        }

        // Verify MultisigWallet
        if (multisigAddr != address(0)) {
            console2.log("\nVerifying MultisigWallet at:", multisigAddr);
            // forge verify-contract --chain-id <chain> <address> contracts/multisig/MultisigWallet.sol:MultisigWallet
        }

        // Verify ProofOfReserve
        if (reserveAddr != address(0)) {
            console2.log("\nVerifying ProofOfReserve at:", reserveAddr);
            // forge verify-contract --chain-id <chain> <address> contracts/reserve/ProofOfReserve.sol:ProofOfReserve
        }

        // Verify ProxyAdmin
        if (proxyAdminAddr != address(0)) {
            console2.log("\nVerifying ProxyAdmin at:", proxyAdminAddr);
            // forge verify-contract --chain-id <chain> <address> contracts/proxy/ProxyAdmin.sol:ProxyAdmin
        }

        // Verify BridgeRelayer
        if (relayerAddr != address(0)) {
            console2.log("\nVerifying BridgeRelayer at:", relayerAddr);
            // forge verify-contract --chain-id <chain> <address> contracts/bridge/BridgeRelayer.sol:BridgeRelayer
        }

        // Verify BridgeVault
        if (vaultAddr != address(0)) {
            console2.log("\nVerifying BridgeVault at:", vaultAddr);
            // forge verify-contract --chain-id <chain> <address> contracts/bridge/BridgeVault.sol:BridgeVault
        }

        console2.log("\n========================================");
        console2.log("VERIFICATION COMMANDS GENERATED");
        console2.log("Run the above commands with forge verify-contract");
        console2.log("========================================");
    }
}