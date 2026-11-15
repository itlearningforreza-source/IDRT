# IDRC Smart Contracts (Solidity Reference Implementation)

This directory contains the **Solidity reference implementation** of the IDR Coin (IDRC) stablecoin system. The Python simulation in `../idrc/` serves as the formal specification and test oracle.

## Contract Architecture

```
contracts/
├── IDRCToken.sol          # Main ERC-20 token with AccessControl, Pausable, Blacklist, EIP-2612
├── IDRCProxy.sol          # UUPS Upgradeable Proxy (to be implemented)
├── IDRCProxyAdmin.sol     # Proxy Admin (Owner: Multisig)
├── IDRCMultisig.sol       # M-of-N Multisig Wallet (Gnosis Safe style)
├── IDRCReserve.sol        # Proof of Reserve (Audit Proofs + Oracle)
├── IDRCBridge.sol         # Cross-Chain Bridge (Burn-and-Mint)
└── interfaces/
    ├── IIDRCToken.sol
    ├── IIDRCProxy.sol
    ├── IIDRCMultisig.sol
    ├── IIDRCReserve.sol
    └── IIDRCBridge.sol
```

## Key Features Implemented

### IDRCToken.sol ✅
- **ERC-20 Standard**: transfer, approve, transferFrom, balanceOf, totalSupply
- **EIP-2612 Permit**: Gasless approvals via EIP-712 signatures
- **AccessControl (RBAC)**: DEFAULT_ADMIN_ROLE, MINTER_ROLE, PAUSER_ROLE, UPGRADER_ROLE, BURNER_ROLE, BLACKLISTER_ROLE
- **Pausable**: Emergency halt of all transfers/minting/burning
- **Blacklist**: Address freezing for sanctions compliance
- **Supply Cap**: Maximum supply limit (10B IDRC)
- **Events**: Full event emission for indexing/monitoring

### Security Patterns
- **Checks-Effects-Interactions (CEI)**: Reentrancy protection
- **Replay Protection**: Nonce-based permit validation
- **Zero Address Checks**: All sensitive operations
- **Role-Based Access**: Strict `onlyRole` modifiers
- **Pausable Guards**: All state-changing functions

## Development Setup (Foundry)

```bash
# Install Foundry
curl -L https://foundry.paradigm.xyz | bash
foundryup

# Initialize project
forge init --force

# Install OpenZeppelin Contracts
forge install OpenZeppelin/openzeppelin-contracts@v5.0.0

# Compile
forge build

# Test
forge test -vvv

# Coverage
forge coverage

# Gas Snapshots
forge snapshot
```

## Deployment Pipeline

The deployment follows this sequence:

1. **Deploy IDRCToken Implementation** (Logic Contract)
2. **Deploy MultiSig Wallet** (Governance - 3-of-5 default)
3. **Deploy ProxyAdmin** (Owner: MultiSig)
4. **Deploy UUPS Proxy** (Implementation: IDRCToken, Admin: ProxyAdmin)
5. **Initialize Token via Proxy** (Grant all roles to MultiSig)
6. **Deploy Reserve Contract** (Admin: MultiSig, Oracle: Trusted Oracle)
7. **Deploy Bridge Contracts** (Per chain)

## Role Distribution (Post-Deployment)

| Role | Holder | Purpose |
|------|--------|---------|
| DEFAULT_ADMIN_ROLE | MultiSig | Manage all other roles |
| MINTER_ROLE | MultiSig | Mint new IDRC (backed by fiat) |
| PAUSER_ROLE | MultiSig | Emergency pause/unpause |
| UPGRADER_ROLE | MultiSig | Authorize contract upgrades |
| BURNER_ROLE | MultiSig | Institutional burns (redemptions) |
| BLACKLISTER_ROLE | MultiSig | Sanctions compliance |
| ORACLE_ROLE | Trusted Oracle | Update fiat reserve balances |

## Verification Checklist

- [ ] All roles granted to MultiSig (not deployer)
- [ ] ProxyAdmin owner is MultiSig
- [ ] Token initialized with correct parameters
- [ ] Supply cap set to 10B IDRC
- [ ] Reserve oracle configured
- [ ] Bridge vaults registered (per chain)
- [ ] Deployment record saved

## Testing Strategy

1. **Unit Tests** (Foundry): Individual function behavior
2. **Integration Tests**: Full deployment flow, mint/burn/pause cycles
3. **Fuzz Tests**: Property-based testing for invariants
4. **Invariant Tests**: Supply conservation, role integrity, pause/blacklist enforcement

## Gas Optimization Notes

- Use `uint256` for all balances (Solidity 0.8+ has built-in overflow checks)
- Pack bools (`paused`, `blacklisted`) into single storage slots where possible
- Minimize external calls in mint/burn (CEI pattern)
- Use `calldata` for read-only parameters

## Upgrade Process (UUPS)

```solidity
// Only UPGRADER_ROLE (MultiSig) can call
function upgradeToAndCall(address newImplementation, bytes calldata data)
    external
    onlyRole(UPGRADER_ROLE)
{
    _authorizeUpgrade(newImplementation);
    _upgradeToAndCallUUPS(newImplementation, data, true);
}
```

---

**Next Steps**: Complete remaining contract implementations (`IDRCProxy.sol`, `IDRCMultisig.sol`, `IDRCReserve.sol`, `IDRCBridge.sol`) and write Foundry test suite.