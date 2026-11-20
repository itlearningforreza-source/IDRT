# blockchain_config.py
# Blockchain Configuration - Chain definitions, contract addresses, RPC endpoints
"""Blockchain configuration for IDRC multi-chain deployment"""
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class Environment(str, Enum):
    DEVELOPMENT = "development"
    TESTNET = "testnet"
    STAGING = "staging"
    PRODUCTION = "production"


class ChainType(str, Enum):
    EVM = "evm"


@dataclass
class ChainConfig:
    """Configuration for a single blockchain network"""
    chain_id: int
    name: str
    rpc_urls: List[str]  # Multiple for failover
    chain_type: ChainType = ChainType.EVM
    is_testnet: bool = False
    native_currency: str = "ETH"
    block_time_seconds: int = 12
    finality_blocks: int = 12  # Blocks to wait for finality
    explorer_url: str = ""
    api_key: Optional[str] = None  # For Etherscan-like APIs
    
    # Contract addresses (loaded from env or deployment artifacts)
    contracts: Dict[str, str] = field(default_factory=dict)
    
    # Gas settings
    gas_limit_multiplier: float = 1.2
    max_gas_price_gwei: int = 500
    priority_fee_gwei: int = 2
    
    # Retry settings
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 30.0
    
    # POA middleware required
    requires_poa_middleware: bool = False


# ============================================================
# CHAIN DEFINITIONS
# ============================================================

CHAINS: Dict[int, ChainConfig] = {
    # Ethereum Mainnet
    1: ChainConfig(
        chain_id=1,
        name="Ethereum Mainnet",
        rpc_urls=[
            os.getenv("ETHEREUM_MAINNET_RPC_URL_1", "https://eth.llamarpc.com"),
            os.getenv("ETHEREUM_MAINNET_RPC_URL_2", "https://ethereum-rpc.publicnode.com"),
            os.getenv("ETHEREUM_MAINNET_RPC_URL_3", "https://rpc.ankr.com/eth"),
        ],
        is_testnet=False,
        native_currency="ETH",
        block_time_seconds=12,
        finality_blocks=64,  # ~12.8 minutes (2 epochs)
        explorer_url="https://etherscan.io",
        api_key=os.getenv("ETHERSCAN_API_KEY"),
        requires_poa_middleware=False,
    ),
    
    # Ethereum Sepolia Testnet
    11155111: ChainConfig(
        chain_id=11155111,
        name="Ethereum Sepolia",
        rpc_urls=[
            os.getenv("ETHEREUM_SEPOLIA_RPC_URL_1", "https://rpc.sepolia.org"),
            os.getenv("ETHEREUM_SEPOLIA_RPC_URL_2", "https://ethereum-sepolia-rpc.publicnode.com"),
            os.getenv("ETHEREUM_SEPOLIA_RPC_URL_3", "https://rpc.ankr.com/eth_sepolia"),
        ],
        is_testnet=True,
        native_currency="ETH",
        block_time_seconds=12,
        finality_blocks=64,
        explorer_url="https://sepolia.etherscan.io",
        api_key=os.getenv("ETHERSCAN_API_KEY"),
        requires_poa_middleware=False,
    ),
    
    # Polygon Mainnet
    137: ChainConfig(
        chain_id=137,
        name="Polygon Mainnet",
        rpc_urls=[
            os.getenv("POLYGON_MAINNET_RPC_URL_1", "https://polygon-rpc.com"),
            os.getenv("POLYGON_MAINNET_RPC_URL_2", "https://polygon-rpc.publicnode.com"),
            os.getenv("POLYGON_MAINNET_RPC_URL_3", "https://rpc.ankr.com/polygon"),
        ],
        is_testnet=False,
        native_currency="MATIC",
        block_time_seconds=2,
        finality_blocks=128,  # ~4 minutes
        explorer_url="https://polygonscan.com",
        api_key=os.getenv("POLYGONSCAN_API_KEY"),
        requires_poa_middleware=True,
    ),
    
    # Polygon Amoy Testnet
    80002: ChainConfig(
        chain_id=80002,
        name="Polygon Amoy",
        rpc_urls=[
            os.getenv("POLYGON_AMOY_RPC_URL_1", "https://rpc-amoy.polygon.technology"),
            os.getenv("POLYGON_AMOY_RPC_URL_2", "https://polygon-amoy-rpc.publicnode.com"),
        ],
        is_testnet=True,
        native_currency="MATIC",
        block_time_seconds=2,
        finality_blocks=128,
        explorer_url="https://amoy.polygonscan.com",
        api_key=os.getenv("POLYGONSCAN_API_KEY"),
        requires_poa_middleware=True,
    ),
    
    # BSC Mainnet
    56: ChainConfig(
        chain_id=56,
        name="BSC Mainnet",
        rpc_urls=[
            os.getenv("BSC_MAINNET_RPC_URL_1", "https://bsc-dataseed.binance.org"),
            os.getenv("BSC_MAINNET_RPC_URL_2", "https://bsc-rpc.publicnode.com"),
        ],
        is_testnet=False,
        native_currency="BNB",
        block_time_seconds=3,
        finality_blocks=15,  # ~45 seconds
        explorer_url="https://bscscan.com",
        api_key=os.getenv("BSCSCAN_API_KEY"),
        requires_poa_middleware=True,
    ),
    
    # BSC Testnet
    97: ChainConfig(
        chain_id=97,
        name="BSC Testnet",
        rpc_urls=[
            os.getenv("BSC_TESTNET_RPC_URL_1", "https://data-seed-prebsc-1-s1.binance.org:8545"),
            os.getenv("BSC_TESTNET_RPC_URL_2", "https://bsc-testnet-rpc.publicnode.com"),
        ],
        is_testnet=True,
        native_currency="BNB",
        block_time_seconds=3,
        finality_blocks=15,
        explorer_url="https://testnet.bscscan.com",
        api_key=os.getenv("BSCSCAN_API_KEY"),
        requires_poa_middleware=True,
    ),
    
    # Arbitrum Mainnet
    42161: ChainConfig(
        chain_id=42161,
        name="Arbitrum One",
        rpc_urls=[
            os.getenv("ARBITRUM_MAINNET_RPC_URL_1", "https://arb1.arbitrum.io/rpc"),
            os.getenv("ARBITRUM_MAINNET_RPC_URL_2", "https://arbitrum-rpc.publicnode.com"),
        ],
        is_testnet=False,
        native_currency="ETH",
        block_time_seconds=0.25,  # ~250ms
        finality_blocks=64,  # Inherits Ethereum finality
        explorer_url="https://arbiscan.io",
        api_key=os.getenv("ARBISCAN_API_KEY"),
        requires_poa_middleware=False,
    ),
    
    # Arbitrum Sepolia
    421614: ChainConfig(
        chain_id=421614,
        name="Arbitrum Sepolia",
        rpc_urls=[
            os.getenv("ARBITRUM_SEPOLIA_RPC_URL_1", "https://sepolia-rollup.arbitrum.io/rpc"),
            os.getenv("ARBITRUM_SEPOLIA_RPC_URL_2", "https://arbitrum-sepolia-rpc.publicnode.com"),
        ],
        is_testnet=True,
        native_currency="ETH",
        block_time_seconds=0.25,
        finality_blocks=64,
        explorer_url="https://sepolia.arbiscan.io",
        api_key=os.getenv("ARBISCAN_API_KEY"),
        requires_poa_middleware=False,
    ),
    
    # Optimism Mainnet
    10: ChainConfig(
        chain_id=10,
        name="Optimism Mainnet",
        rpc_urls=[
            os.getenv("OPTIMISM_MAINNET_RPC_URL_1", "https://mainnet.optimism.io"),
            os.getenv("OPTIMISM_MAINNET_RPC_URL_2", "https://optimism-rpc.publicnode.com"),
        ],
        is_testnet=False,
        native_currency="ETH",
        block_time_seconds=2,
        finality_blocks=64,
        explorer_url="https://optimistic.etherscan.io",
        api_key=os.getenv("OPTIMISTIC_ETHERSCAN_API_KEY"),
        requires_poa_middleware=False,
    ),
    
    # Optimism Sepolia
    11155420: ChainConfig(
        chain_id=11155420,
        name="Optimism Sepolia",
        rpc_urls=[
            os.getenv("OPTIMISM_SEPOLIA_RPC_URL_1", "https://sepolia.optimism.io"),
            os.getenv("OPTIMISM_SEPOLIA_RPC_URL_2", "https://optimism-sepolia-rpc.publicnode.com"),
        ],
        is_testnet=True,
        native_currency="ETH",
        block_time_seconds=2,
        finality_blocks=64,
        explorer_url="https://sepolia-optimistic.etherscan.io",
        api_key=os.getenv("OPTIMISTIC_ETHERSCAN_API_KEY"),
        requires_poa_middleware=False,
    ),
    
    # Base Mainnet
    8453: ChainConfig(
        chain_id=8453,
        name="Base Mainnet",
        rpc_urls=[
            os.getenv("BASE_MAINNET_RPC_URL_1", "https://mainnet.base.org"),
            os.getenv("BASE_MAINNET_RPC_URL_2", "https://base-rpc.publicnode.com"),
        ],
        is_testnet=False,
        native_currency="ETH",
        block_time_seconds=2,
        finality_blocks=64,
        explorer_url="https://basescan.org",
        api_key=os.getenv("BASESCAN_API_KEY"),
        requires_poa_middleware=False,
    ),
    
    # Base Sepolia
    84532: ChainConfig(
        chain_id=84532,
        name="Base Sepolia",
        rpc_urls=[
            os.getenv("BASE_SEPOLIA_RPC_URL_1", "https://sepolia.base.org"),
            os.getenv("BASE_SEPOLIA_RPC_URL_2", "https://base-sepolia-rpc.publicnode.com"),
        ],
        is_testnet=True,
        native_currency="ETH",
        block_time_seconds=2,
        finality_blocks=64,
        explorer_url="https://sepolia.basescan.org",
        api_key=os.getenv("BASESCAN_API_KEY"),
        requires_poa_middleware=False,
    ),
}


# ============================================================
# ENVIRONMENT-SPECIFIC CHAIN SETS
# ============================================================

ENVIRONMENT_CHAINS: Dict[Environment, List[int]] = {
    Environment.DEVELOPMENT: [11155111, 80002, 97, 421614, 11155420, 84532],  # Testnets only
    Environment.TESTNET: [11155111, 80002, 97, 421614, 11155420, 84532],
    Environment.STAGING: [11155111, 80002, 97, 421614, 11155420, 84532, 1, 137, 56, 42161, 10, 8453],
    Environment.PRODUCTION: [1, 137, 56, 42161, 10, 8453],  # Mainnets only
}


def get_chains_for_environment(env: Environment) -> List[ChainConfig]:
    """Get chain configurations for a specific environment"""
    chain_ids = ENVIRONMENT_CHAINS.get(env, [])
    return [CHAINS[cid] for cid in chain_ids if cid in CHAINS]


def get_chain_config(chain_id: int) -> Optional[ChainConfig]:
    """Get chain configuration by chain ID"""
    return CHAINS.get(chain_id)


def validate_environment_config(env: Environment) -> List[str]:
    """Validate that all required configuration is present for environment"""
    errors = []
    chains = get_chains_for_environment(env)
    
    for chain in chains:
        # Check RPC URLs
        if not chain.rpc_urls or all(not url or url.startswith("http://localhost") for url in chain.rpc_urls):
            if env == Environment.PRODUCTION:
                errors.append(f"Chain {chain.name} ({chain.chain_id}): No production RPC URLs configured")
            elif env != Environment.DEVELOPMENT:
                errors.append(f"Chain {chain.name} ({chain.chain_id}): No valid RPC URLs")
        
        # Check contract addresses for production
        if env == Environment.PRODUCTION:
            required_contracts = ["IDRCToken", "BridgeVault", "ProofOfReserve", "MultisigWallet"]
            for contract in required_contracts:
                if contract not in chain.contracts or not chain.contracts[contract]:
                    errors.append(f"Chain {chain.name}: Missing {contract} address")
        
        # Check explorer API keys for production
        if env == Environment.PRODUCTION and not chain.api_key:
            errors.append(f"Chain {chain.name}: Missing explorer API key")
    
    return errors


# ============================================================
# CONTRACT ADDRESS MANAGEMENT
# ============================================================

CONTRACT_NAMES = [
    "IDRCToken",
    "BridgeVault",
    "BridgeRelayer",
    "ProofOfReserve",
    "MultisigWallet",
    "ProxyAdmin",
    "UUPSProxy",
]


def load_contract_addresses_from_env(chain_id: int) -> Dict[str, str]:
    """Load contract addresses from environment variables"""
    addresses = {}
    chain_config = get_chain_config(chain_id)
    if not chain_config:
        return addresses
    
    for contract_name in CONTRACT_NAMES:
        env_var = f"{contract_name.upper()}_{chain_id}_ADDRESS"
        address = os.getenv(env_var)
        if address:
            addresses[contract_name] = address
    
    return addresses


def load_contract_addresses_from_deployment(chain_id: int, deployment_file: str) -> Dict[str, str]:
    """Load contract addresses from deployment artifact file"""
    import json
    try:
        with open(deployment_file) as f:
            data = json.load(f)
        return data.get(str(chain_id), {}).get("contracts", {})
    except Exception:
        return {}


# Export
__all__ = [
    "Environment",
    "ChainType",
    "ChainConfig",
    "CHAINS",
    "ENVIRONMENT_CHAINS",
    "CONTRACT_NAMES",
    "get_chains_for_environment",
    "get_chain_config",
    "validate_environment_config",
    "load_contract_addresses_from_env",
    "load_contract_addresses_from_deployment",
]
