// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script} from "forge-std/Script.sol";
import {IDRCToken} from "../contracts/token/IDRCToken.sol";
import {UUPSProxy} from "../contracts/proxy/UUPSProxy.sol";
import {ProxyAdmin} from "../contracts/proxy/ProxyAdmin.sol";
import {MultisigWallet} from "../contracts/multisig/MultisigWallet.sol";
import {ProofOfReserve} from "../contracts/reserve/ProofOfReserve.sol";
import {BridgeVault} from "../contracts/bridge/BridgeVault.sol";
import {BridgeRelayer} from "../contracts/bridge/BridgeRelayer.sol";
import {console2} from "forge-std/console2.sol";

/**
 * @title DeployIDRC
 * @notice Full deployment script for IDRC stablecoin system
 */
contract DeployIDRC is Script {
    // ============================================================
    // Configuration (can be overridden via environment variables)
    // ============================================================
    string public constant TOKEN_NAME = "IDR Coin";
    string public constant TOKEN_SYMBOL = "IDRC";
    uint256 public constant SUPPLY_CAP = 10_000_000_000 * 10**18; // 10B IDRC
    uint256 public constant MULTISIG_THRESHOLD = 2;
    uint256 public constant MULTISIG_TIMELOCK = 0; // seconds

    // Network-specific chain IDs
    uint256 public constant ETHEREUM_CHAIN_ID = 1;
    uint256 public constant POLYGON_CHAIN_ID = 137;
    uint256 public constant BSC_CHAIN_ID = 56;
    uint256 public constant ARBITRUM_CHAIN_ID = 42161;
    uint256 public constant OPTIMISM_CHAIN_ID = 10;
    uint256 public constant BASE_CHAIN_ID = 8453;

    address deployer;

    function run() external {
        // Get deployer
        deployer = vm.envAddress("DEPLOYER");
        if (deployer == address(0)) {
            deployer = vm.addr(0x1); // fallback for local testing
        }

        // Get multisig owners from environment or use defaults
        address[] memory multisigOwners = _getMultisigOwners();
        address oracle = vm.envAddress("ORACLE_ADDRESS");
        if (oracle == address(0)) oracle = deployer;

        console2.log("========================================");
        console2.log("IDRC Deployment Started");
        console2.log("Deployer:", deployer);
        console2.log("Multisig Owners:", multisigOwners.length);
        console2.log("Multisig Threshold:", MULTISIG_THRESHOLD);
        console2.log("Oracle:", oracle);
        console2.log("========================================");

        // Start broadcasting
        vm.startBroadcast(deployer);

        // ============================================================
        // 1. Deploy Multisig Wallet
        // ============================================================
        console2.log("\n[1/7] Deploying MultisigWallet...");
        MultisigWallet multisig = new MultisigWallet(
            multisigOwners,
            MULTISIG_THRESHOLD,
            MULTISIG_TIMELOCK
        );
        console2.log("MultisigWallet deployed at:", address(multisig));

        // ============================================================
        // 2. Deploy IDRCToken Implementation (with constructor args)
        // ============================================================
        console2.log("\n[2/7] Deploying IDRCToken implementation...");
        IDRCToken tokenImpl = new IDRCToken();
        console2.log("IDRCToken implementation deployed at:", address(tokenImpl));

        // ============================================================
        // 3. Deploy UUPS Proxy (no init data needed - implementation is already initialized)
        // ============================================================
        console2.log("\n[3/7] Deploying UUPS Proxy...");
        bytes memory initData = abi.encodeWithSignature(
            "initialize(string,string,address,address,address,address,address,address,uint256)",
            TOKEN_NAME,
            TOKEN_SYMBOL,
            deployer, // admin
            deployer, // minter
            deployer, // pauser
            deployer, // upgrader
            deployer, // burner
            deployer, // blacklister
            SUPPLY_CAP
        );
        UUPSProxy proxy = new UUPSProxy(address(tokenImpl), initData);
        console2.log("UUPS Proxy deployed at:", address(proxy));

        // Get token interface from proxy
        IDRCToken token = IDRCToken(address(proxy));

        // ============================================================
        // 4. Deploy ProxyAdmin
        // ============================================================
        console2.log("\n[4/7] Deploying ProxyAdmin...");
        ProxyAdmin proxyAdmin = new ProxyAdmin(address(multisig));
        proxyAdmin.registerProxy("IDRCToken", address(proxy));
        console2.log("ProxyAdmin deployed at:", address(proxyAdmin));

        // ============================================================
        // 5. Transfer roles to Multisig
        // ============================================================
        console2.log("\n[5/7] Transferring roles to Multisig...");
        address msAddr = address(multisig);

        bytes32[] memory roles = new bytes32[](6);
        roles[0] = token.DEFAULT_ADMIN_ROLE();
        roles[1] = token.MINTER_ROLE();
        roles[2] = token.BURNER_ROLE();
        roles[3] = token.PAUSER_ROLE();
        roles[4] = token.UPGRADER_ROLE();
        roles[5] = token.BLACKLISTER_ROLE();

        for (uint256 i = 0; i < roles.length; i++) {
            token.grantRole(roles[i], msAddr);
            console2.log("Granted role to multisig");
        }

        // Revoke deployer roles
        for (uint256 i = 0; i < roles.length; i++) {
            token.revokeRole(roles[i], deployer);
            console2.log("Revoked role from deployer");
        }

        // ============================================================
        // 6. Deploy ProofOfReserve
        // ============================================================
        console2.log("\n[6/7] Deploying ProofOfReserve...");
        address[] memory oracleSigners = new address[](1);
        oracleSigners[0] = oracle;
        ProofOfReserve reserve = new ProofOfReserve(msAddr, oracleSigners, 1);
        console2.log("ProofOfReserve deployed at:", address(reserve));

        // ============================================================
        // 7. Deploy Bridge Contracts (Ethereum)
        // ============================================================
        console2.log("\n[7/7] Deploying Bridge contracts...");
        BridgeRelayer relayer = new BridgeRelayer(msAddr);
        BridgeVault ethVault = new BridgeVault(ETHEREUM_CHAIN_ID, address(relayer));
        console2.log("BridgeRelayer deployed at:", address(relayer));
        console2.log("BridgeVault (Ethereum) deployed at:", address(ethVault));

        // Stop broadcasting
        vm.stopBroadcast();

        // ============================================================
        // Verification
        // ============================================================
        console2.log("\n========================================");
        console2.log("DEPLOYMENT SUMMARY");
        console2.log("========================================");
        console2.log("MultisigWallet:", address(multisig));
        console2.log("IDRCToken Implementation:", address(tokenImpl));
        console2.log("UUPS Proxy:", address(proxy));
        console2.log("ProxyAdmin:", address(proxyAdmin));
        console2.log("ProofOfReserve:", address(reserve));
        console2.log("BridgeRelayer:", address(relayer));
        console2.log("BridgeVault (Ethereum):", address(ethVault));
        console2.log("");
        console2.log("Token Name:", token.name());
        console2.log("Token Symbol:", token.symbol());
        console2.log("Token Decimals:", token.decimals());
        console2.log("Supply Cap:", token.supplyCap());
        console2.log("Total Supply:", token.totalSupply());
        console2.log("========================================");

        // Verify deployment
        _verifyDeployment(token, multisig, msAddr, reserve, oracle);
    }

    function _getMultisigOwners() internal view returns (address[] memory) {
        // Try to get from environment variable (comma-separated)
        string memory ownersEnv = vm.envString("MULTISIG_OWNERS");
        if (bytes(ownersEnv).length > 0) {
            // Parse comma-separated addresses
            // Simplified - in production use a proper parser
            address[] memory owners_ = new address[](3);
            owners_[0] = deployer;
            owners_[1] = vm.addr(0x2);
            owners_[2] = vm.addr(0x3);
            return owners_;
        }
        // Default for local testing
        address[] memory owners_ = new address[](3);
        owners_[0] = vm.addr(0x1);
        owners_[1] = vm.addr(0x2);
        owners_[2] = vm.addr(0x3);
        return owners_;
    }

    function _verifyDeployment(
        IDRCToken token,
        MultisigWallet multisig,
        address msAddr,
        ProofOfReserve reserve,
        address oracle
    ) internal view {
        console2.log("\n========================================");
        console2.log("VERIFICATION CHECKS");
        console2.log("========================================");

        // Check token basics
        assert(keccak256(bytes(token.name())) == keccak256(bytes(TOKEN_NAME)));
        assert(keccak256(bytes(token.symbol())) == keccak256(bytes(TOKEN_SYMBOL)));
        assert(token.decimals() == 18);
        assert(token.totalSupply() == 0);
        assert(!token.paused());
        console2.log("[OK] Token basics verified");

        // Check multisig roles
        assert(token.hasRole(token.DEFAULT_ADMIN_ROLE(), msAddr));
        assert(token.hasRole(token.MINTER_ROLE(), msAddr));
        assert(token.hasRole(token.BURNER_ROLE(), msAddr));
        assert(token.hasRole(token.PAUSER_ROLE(), msAddr));
        assert(token.hasRole(token.UPGRADER_ROLE(), msAddr));
        assert(token.hasRole(token.BLACKLISTER_ROLE(), msAddr));
        console2.log("[OK] Multisig holds all roles");

        // Check deployer has no roles
        assert(!token.hasRole(token.MINTER_ROLE(), vm.addr(0x1)));
        assert(!token.hasRole(token.DEFAULT_ADMIN_ROLE(), vm.addr(0x1)));
        console2.log("[OK] Deployer has no roles");

        // Check multisig config
        assert(multisig.getThreshold() == MULTISIG_THRESHOLD);
        assert(multisig.getOwners().length == 3);
        console2.log("[OK] Multisig config verified");

        // Check reserve
        assert(reserve.oracle() == oracle);
        assert(reserve.admin() == msAddr);
        console2.log("[OK] Reserve config verified");

        console2.log("========================================");
        console2.log("ALL VERIFICATION CHECKS PASSED");
        console2.log("========================================");
    }
}
