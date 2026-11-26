from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
import idrc
from idrc import deploy_idrc, IDRCMonitor
from services.api.auth import get_current_user
import os

app = FastAPI(title="IDRC Web Dashboard", description="API for IDR Coin Simulation")

# Global deployment state
deployment = deploy_idrc(
    deployer="0xDeployer",
    multisig_owners=["BankIndonesia", "Kemenkeu", "OJK"],
    multisig_threshold=2,
    network="mainnet-simulation"
)
token = deployment.token
reserve = deployment.reserve
multisig = deployment.multisig
monitor = IDRCMonitor(token, reserve)

# Serve static files for UI
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

class ActionRequest(BaseModel):
    # Caller identity is NEVER taken from client input.
    # Derived from the authenticated session via get_current_user.
    target: str = ""
    amount: str = "0"

@app.get("/")
def read_root():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/status")
def get_status():
    monitor.sync()
    
    supply = token.total_supply
    fiat_reserve = reserve.latest_fiat_balance if reserve.latest_fiat_balance else 0
    
    # Calculate ratio safely
    if supply == 0:
        ratio = 100.0 if fiat_reserve >= 0 else 0.0
    else:
        ratio = (fiat_reserve / supply) * 100.0

    return {
        "supply": supply / 10**18,
        "fiat_reserve": fiat_reserve / 10**18,
        "reserve_ratio": round(ratio, 2),
        "is_paused": token.paused,
        "name": token.name,
        "symbol": token.symbol,
        "alerts": [
            {"level": a.level, "code": a.code, "message": a.message}
            for a in monitor.alerts
        ],
        "recent_events": [str(e) for e in token.events[-5:]]
    }

@app.get("/api/balance/{address}")
def get_balance(address: str):
    balance = token.balance_of(address)
    return {"address": address, "balance": balance / 10**18}

def _parse_amount(raw: str) -> int:
    """Fixed-point amount conversion: no float, 18-decimal precision."""
    try:
        d = Decimal(raw)
        q = d.quantize(Decimal("1"))
        if d < 0:
            raise ValueError
        return int(d * (10**18))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid amount")


@app.post("/api/multisig/propose_mint")
async def propose_mint(req: ActionRequest, user=Depends(get_current_user)):
    amount_raw = _parse_amount(req.amount)
    if amount_raw <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    caller = user.address  # Authenticated principal; NOT client-supplied
    tx_id = multisig.propose(
        description=f"Mint {req.amount} IDRC to {req.target}",
        fn=token.mint,
        fn_kwargs={"to": req.target, "amount": amount_raw},
        caller=caller
    )
    return {"tx_id": tx_id, "message": f"Transaction {tx_id} proposed successfully."}

@app.post("/api/multisig/approve")
async def approve_tx(tx_id: str, user=Depends(get_current_user)):
    caller = user.address
    try:
        multisig.approve(tx_id, caller=caller)
        return {"message": f"Approved transaction {tx_id} by {caller}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/multisig/execute")
async def execute_tx(tx_id: str, user=Depends(get_current_user)):
    caller = user.address
    try:
        multisig.execute(tx_id, caller=caller)
        return {"message": f"Executed transaction {tx_id} successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/multisig/pending")
def pending_txs():
    pending = []
    for tx_id, tx in multisig._txs.items():
        if tx.status.name == "PENDING":
            pending.append({
                "id": tx_id,
                "description": tx.description,
                "proposed_by": tx.proposed_by,
                "approvals": list(tx.approvals),
                "threshold": multisig.threshold
            })
    return {"pending_transactions": pending}

@app.post("/api/transfer")
async def transfer(req: ActionRequest, user=Depends(get_current_user)):
    amount_raw = _parse_amount(req.amount)
    if amount_raw <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    caller = user.address  # Authenticated principal; NOT client-supplied
    try:
        token.transfer(req.target, amount_raw, caller=caller)
        return {"message": f"Transferred {req.amount} IDRC to {req.target}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/oracle/update")
async def oracle_update(balance: str, user=Depends(get_current_user)):
    # Oracle endpoints require authentication; caller is never taken from input
    amount_raw = _parse_amount(balance)
    try:
        reserve.update_fiat_balance(amount_raw, caller=user.address)
        return {"message": f"Oracle updated reserve balance to {Decimal(balance)} IDR"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
