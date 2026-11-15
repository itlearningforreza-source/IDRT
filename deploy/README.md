# IDRC Deployment Scripts

Automated deployment and verification scripts for the IDR Coin (IDRC) stablecoin system.

## Files

- `deploy_idrc.py` - Full deployment pipeline (Python simulation)
- `verify_deployment.py` - Post-deployment verification

## Usage

```bash
# Run full deployment simulation
python deploy/deploy_idrc.py

# Verify existing deployment
python deploy/verify_deployment.py <deployment_file.json>
```

## Deployment Pipeline

The script simulates the complete production deployment:

1. **Token Implementation** → Logic contract deployment
2. **Multisig Wallet** → Gnosis Safe simulation (M-of-N)
3. **ProxyAdmin** → Owner: Multisig
4. **UUPS Proxy** → Points to Token Implementation, Admin: ProxyAdmin
5. **Token Initialization** → Via Proxy, all roles → Multisig
6. **Proof of Reserve** → Oracle integration
7. **Bridge Vaults** → Cross-chain registration

## Output

Deployment records are saved to `deployments/deployment_{network}_{timestamp}.json` containing:
- All contract addresses
- Role assignments
- Network metadata
- Timestamp

## Production Deployment (Solidity/Foundry)

For actual Mainnet/Testnet deployment, use Foundry scripts:

```bash
# Deploy to Sepolia
forge script script/DeployIDRC.s.sol --rpc-url $SEPOLIA_RPC --broadcast --verify

# Deploy to Polygon Amoy
forge script script/DeployIDRC.s.sol --rpc-url $AMOY_RPC --broadcast --verify
```

## Verification Checklist

After deployment, verify:

- [ ] All roles held by Multisig (not deployer)
- [ ] ProxyAdmin owner is Multisig
- [ ] Token name/symbol/decimals correct
- [ ] Supply cap = 10B IDRC
- [ ] Reserve oracle configured
- [ ] Bridge vaults registered
- [ ] Deployment record saved to secure storage