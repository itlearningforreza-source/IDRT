"""
Blockchain Connection - Web3 contract instances and providers
"""
import os
import json
from typing import Dict, Optional
from web3 import Web3
from web3.contract import Contract
from web3.middleware import geth_poa_middleware

# Global contract instances
_contracts: Dict[str, Contract] = {}
_providers: Dict[int, Web3] = {}


# Contract ABIs (simplified - in production load from artifacts)
def _load_abi(name: str) -> list:
    """Load contract ABI from artifacts"""
    abi_path = os.getenv("ABI_PATH", "./out")
    try:
        with open(f"{abi_path}/{name}.sol/{name}.json") as f:
            artifact = json.load(f)
            return artifact["abi"]
    except FileNotFoundError:
        # Return minimal ABI for development
        return _get_minimal_abi(name)


def _get_minimal_abi(name: str) -> list:
    """Minimal ABIs for development"""
    abis = {
        "IDRCToken": [
            {"inputs": [], "name": "name", "outputs": [{"internalType": "string", "name": "", "type": "string"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "symbol", "outputs": [{"internalType": "string", "name": "", "type": "string"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "decimals", "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "totalSupply", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "owner", "type": "address"}, {"internalType": "address", "name": "spender", "type": "address"}], "name": "allowance", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "to", "type": "address"}, {"internalType": "uint256", "name": "amount", "type": "uint256"}], "name": "mint", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "from", "type": "address"}, {"internalType": "uint256", "name": "amount", "type": "uint256"}], "name": "issuerBurn", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"internalType": "uint256", "name": "amount", "type": "uint256"}], "name": "burn", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "to", "type": "address"}, {"internalType": "uint256", "name": "amount", "type": "uint256"}], "name": "transfer", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "spender", "type": "address"}, {"internalType": "uint256", "name": "amount", "type": "uint256"}], "name": "approve", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [], "name": "paused", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "account", "type": "address"}], "name": "isBlacklisted", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "bytes32", "name": "role", "type": "bytes32"}, {"internalType": "address", "name": "account", "type": "address"}], "name": "hasRole", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "account", "type": "address"}], "name": "blacklist", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "account", "type": "address"}], "name": "unblacklist", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [], "name": "pause", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [], "name": "unpause", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [], "name": "supplyCap", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "reserveProofHash", "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}], "stateMutability": "view", "type": "function"},
        ],
        "MultisigWallet": [
            {"inputs": [], "name": "getOwners", "outputs": [{"internalType": "address[]", "name": "", "type": "address[]"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "getThreshold", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "account", "type": "address"}], "name": "isOwner", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "getTransactionCount", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "uint256", "name": "transactionId", "type": "uint256"}], "name": "transactions", "outputs": [{"internalType": "address", "name": "to", "type": "address"}, {"internalType": "uint256", "name": "value", "type": "uint256"}, {"internalType": "bytes", "name": "data", "type": "bytes"}, {"internalType": "bool", "name": "executed", "type": "bool"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "uint256", "name": "transactionId", "type": "uint256"}], "name": "getConfirmations", "outputs": [{"internalType": "address[]", "name": "confirmations", "type": "address[]"}, {"internalType": "bool", "name": "executed", "type": "bool"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "to", "type": "address"}, {"internalType": "uint256", "name": "value", "type": "uint256"}, {"internalType": "bytes", "name": "data", "type": "bytes"}], "name": "submitTransaction", "outputs": [{"internalType": "uint256", "name": "transactionId", "type": "uint256"}], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"internalType": "uint256", "name": "transactionId", "type": "uint256"}], "name": "confirmTransaction", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"internalType": "uint256", "name": "transactionId", "type": "uint256"}], "name": "revokeConfirmation", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"internalType": "uint256", "name": "transactionId", "type": "uint256"}], "name": "executeTransaction", "outputs": [{"internalType": "bool", "name": "success", "type": "bool"}], "stateMutability": "payable", "type": "function"},
        ],
        "ProofOfReserve": [
            {"inputs": [], "name": "fiatBalanceIdr", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "lastOracleUpdate", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "latestProofHash", "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "auditReportCount", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "uint256", "name": "seq", "type": "uint256"}], "name": "getAuditReport", "outputs": [{"internalType": "uint256", "name": "seq", "type": "uint256"}, {"internalType": "bytes32", "name": "proofHash", "type": "bytes32"}, {"internalType": "uint256", "name": "reportedFiatIdr", "type": "uint256"}, {"internalType": "address", "name": "submittedBy", "type": "address"}, {"internalType": "uint256", "name": "timestamp", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "uint256", "name": "tokenTotalSupply", "type": "uint256"}], "name": "reserveRatio", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "uint256", "name": "tokenTotalSupply", "type": "uint256"}], "name": "checkCollateralisation", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "bytes32", "name": "proofHash", "type": "bytes32"}, {"internalType": "uint256", "name": "reportedFiatIdr", "type": "uint256"}], "name": "submitAuditProof", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"internalType": "uint256", "name": "newBalanceIdr", "type": "uint256"}], "name": "updateFiatBalance", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "oracle", "type": "address"}], "name": "setOracle", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
        ],
        "BridgeVault": [
            {"inputs": [], "name": "chainId", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "relayer", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "totalLocked", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "uint256", "name": "bridgeNonce", "type": "uint256"}], "name": "isNonceProcessed", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "token", "type": "address"}, {"internalType": "address", "name": "sender", "type": "address"}, {"internalType": "address", "name": "recipient", "type": "address"}, {"internalType": "uint256", "name": "amount", "type": "uint256"}, {"internalType": "uint256", "name": "dstChainId", "type": "uint256"}], "name": "lock", "outputs": [{"internalType": "uint256", "name": "bridgeNonce", "type": "uint256"}], "stateMutability": "nonpayable", "type": "function"},
        ],
        "BridgeRelayer": [
            {"inputs": [{"internalType": "uint256", "name": "srcChainId", "type": "uint256"}, {"internalType": "uint256", "name": "bridgeNonce", "type": "uint256"}], "name": "processedMessages", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "uint256", "name": "bridgeNonce", "type": "uint256"}, {"internalType": "uint256", "name": "srcChainId", "type": "uint256"}, {"internalType": "uint256", "name": "dstChainId", "type": "uint256"}, {"internalType": "address", "name": "recipient", "type": "address"}, {"internalType": "uint256", "name": "amount", "type": "uint256"}, {"internalType": "address", "name": "token", "type": "address"}], "name": "relay", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
        ],
        "ProxyAdmin": [
            {"inputs": [{"internalType": "string", "name": "name", "type": "string"}], "name": "getProxy", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "string", "name": "name", "type": "string"}], "name": "upgrade", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"internalType": "string", "name": "name", "type": "string"}, {"internalType": "address", "name": "implementation", "type": "address"}, {"internalType": "bytes", "name": "data", "type": "bytes"}], "name": "upgradeAndCall", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
        ],
    }
    return abis.get(name, [])


def get_provider(chain_id: int) -> Web3:
    """Get or create Web3 provider for chain"""
    if chain_id not in _providers:
        rpc_url = _get_rpc_url(chain_id)
        w3 = Web3(Web3.HTTPProvider(rpc_url))

        # Add POA middleware for BSC, Polygon, etc.
        if chain_id in [56, 97, 137, 80002, 42161, 421614, 10, 11155420, 8453, 84532]:
            w3.middleware_onion.inject(geth_poa_middleware, layer=0)

        _providers[chain_id] = w3

    return _providers[chain_id]


def _get_rpc_url(chain_id: int) -> str:
    """Get RPC URL for chain from environment"""
    urls = {
        1: os.getenv("ETHEREUM_MAINNET_RPC_URL", "https://eth.llamarpc.com"),
        11155111: os.getenv("ETHEREUM_SEPOLIA_RPC_URL", "https://rpc.sepolia.org"),
        137: os.getenv("POLYGON_MAINNET_RPC_URL", "https://polygon-rpc.com"),
        80002: os.getenv("POLYGON_AMOY_RPC_URL", "https://rpc-amoy.polygon.technology"),
        56: os.getenv("BSC_MAINNET_RPC_URL", "https://bsc-dataseed.binance.org"),
        97: os.getenv("BSC_TESTNET_RPC_URL", "https://data-seed-prebsc-1-s1.binance.org:8545"),
        42161: os.getenv("ARBITRUM_MAINNET_RPC_URL", "https://arb1.arbitrum.io/rpc"),
        421614: os.getenv("ARBITRUM_SEPOLIA_RPC_URL", "https://sepolia-rollup.arbitrum.io/rpc"),
        10: os.getenv("OPTIMISM_MAINNET_RPC_URL", "https://mainnet.optimism.io"),
        11155420: os.getenv("OPTIMISM_SEPOLIA_RPC_URL", "https://sepolia.optimism.io"),
        8453: os.getenv("BASE_MAINNET_RPC_URL", "https://mainnet.base.org"),
        84532: os.getenv("BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org"),
    }
    return urls.get(chain_id, os.getenv("DEFAULT_RPC_URL", "http://localhost:8545"))


def get_contract_address(chain_id: int, contract_name: str) -> str:
    """Get deployed contract address for chain"""
    # In production, load from deployment artifacts or config
    env_var = f"{contract_name.upper()}_{chain_id}_ADDRESS"
    return os.getenv(env_var, "")


async def init_blockchain() -> None:
    """Initialize all blockchain connections"""
    # Pre-load providers for common chains
    for chain_id in [1, 11155111, 137, 80002, 56, 97, 42161, 421614, 10, 11155420, 8453, 84532]:
        try:
            get_provider(chain_id)
        except Exception as e:
            print(f"Warning: Failed to initialize provider for chain {chain_id}: {e}")


async def get_blockchain_status() -> dict:
    """Get blockchain connectivity status"""
    status = {"connected": False, "chains": {}}
    for chain_id in [11155111]:  # Check Sepolia by default
        try:
            w3 = get_provider(chain_id)
            block = w3.eth.get_block("latest")
            status["chains"][chain_id] = {
                "connected": True,
                "latest_block": block.number,
                "chain_id": w3.eth.chain_id
            }
            status["connected"] = True
        except Exception as e:
            status["chains"][chain_id] = {"connected": False, "error": str(e)}
    return status


def _get_contract(chain_id: int, contract_name: str, address: str = None) -> Contract:
    """Get or create contract instance"""
    key = f"{contract_name}_{chain_id}"
    if key not in _contracts:
        if not address:
            address = get_contract_address(chain_id, contract_name)
        if not address:
            raise ValueError(f"No address for {contract_name} on chain {chain_id}")

        w3 = get_provider(chain_id)
        abi = _load_abi(contract_name)
        _contracts[key] = w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)
    return _contracts[key]


async def get_token_contract(chain_id: int) -> Contract:
    return _get_contract(chain_id, "IDRCToken")


async def get_multisig_contract(chain_id: int) -> Contract:
    return _get_contract(chain_id, "MultisigWallet")


async def get_reserve_contract(chain_id: int) -> Contract:
    return _get_contract(chain_id, "ProofOfReserve")


async def get_bridge_contracts(chain_id: int = None) -> Dict[str, Contract]:
    contracts = {}
    chains = [chain_id] if chain_id else [1, 11155111, 137, 80002, 56, 97, 42161, 421614, 10, 11155420, 8453, 84532]

    for cid in chains:
        try:
            vault_addr = get_contract_address(cid, "BridgeVault")
            relayer_addr = get_contract_address(cid, "BridgeRelayer")
            token_addr = get_contract_address(cid, "IDRCToken")

            if vault_addr:
                contracts[f"vault_{cid}"] = _get_contract(cid, "BridgeVault", vault_addr)
            if relayer_addr:
                contracts[f"relayer_{cid}"] = _get_contract(cid, "BridgeRelayer", relayer_addr)
            if token_addr:
                contracts[f"token_{cid}"] = _get_contract(cid, "IDRCToken", token_addr)
        except Exception as e:
            print(f"Warning: Failed to load bridge contracts for chain {cid}: {e}")

    return contracts


async def get_proxy_admin_contract(chain_id: int) -> Contract:
    return _get_contract(chain_id, "ProxyAdmin")