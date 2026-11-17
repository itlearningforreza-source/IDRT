from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
import idrc
from idrc import deploy_idrc, IDRCMonitor
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
    caller: str
    target: str = ""
    amount: float = 0.0

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

@app.post("/api/multisig/propose_mint")
def propose_mint(req: ActionRequest):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    amount_raw = int(req.amount * 10**18)
    tx_id = multisig.propose(
        description=f"Mint {req.amount} IDRC to {req.target}",
        fn=token.mint,
        fn_kwargs={"to": req.target, "amount": amount_raw, "caller": deployment.multisig_address},
        caller=req.caller
    )
    return {"tx_id": tx_id, "message": f"Transaction {tx_id} proposed successfully."}

@app.post("/api/multisig/approve")
def approve_tx(tx_id: str, caller: str):
    try:
        multisig.approve(tx_id, caller=caller)
        return {"message": f"Approved transaction {tx_id} by {caller}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/multisig/execute")
def execute_tx(tx_id: str, caller: str):
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
def transfer(req: ActionRequest):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    amount_raw = int(req.amount * 10**18)
    try:
        token.transfer(req.target, amount_raw, caller=req.caller)
        return {"message": f"Transferred {req.amount} IDRC to {req.target}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/oracle/update")
def oracle_update(balance: float):
    try:
        amount_raw = int(balance * 10**18)
        reserve.update_fiat_balance(amount_raw, caller="0xOracle")
        return {"message": f"Oracle updated reserve balance to {balance:,.0f} IDR"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
