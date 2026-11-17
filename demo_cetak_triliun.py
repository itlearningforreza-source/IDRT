
from idrc import IDRCMonitor, deploy_idrc


def main():
    print("🚀 [1] Memulai simulasi deployment IDRC...")
    deployment = deploy_idrc(
        deployer="0xDeployer",
        multisig_owners=["BankIndonesia", "Kemenkeu", "OJK"],
        multisig_threshold=2,
        network="mainnet-simulation"
    )

    ms = deployment.multisig
    ms_addr = deployment.multisig_address
    token = deployment.token
    reserve = deployment.reserve

    # 10.371,1 Triliun = 10.371.100.000.000.000 IDRC
    # Ditambah 18 desimal (standar ERC-20)
    jumlah_idrc = 10_371_100_000_000_000
    jumlah_raw = jumlah_idrc * 10**18
    penerima = "0xKasNegara"

    print(f"\n💸 [2] Kemenkeu mengusulkan pencetakan {jumlah_idrc:,.0f} IDRC...")
    tx_id = ms.propose(
        description=f"Cetak 10.371,1 Triliun IDRC ke {penerima}",
        fn=token.mint,
        fn_kwargs={"to": penerima, "amount": jumlah_raw, "caller": ms_addr},
        caller="Kemenkeu"
    )

    print("✅ [3] BankIndonesia menyetujui transaksi tersebut...")
    ms.approve(tx_id, caller="BankIndonesia")

    print("⚡ [4] Kemenkeu mencoba mengeksekusi transaksi pencetakan...")
    try:
        ms.execute(tx_id, caller="Kemenkeu")
    except Exception as e:
        print(f"❌ TRANSAKSI GAGAL DITOLAK SMART CONTRACT: {e}")
        return

    print(f"💰 Saldo {penerima} sekarang: {token.balance_of(penerima) / 10**18:,.0f} IDRC")

    print("\n🔍 [5] Mengaktifkan IDRC Monitor & Engine Peringatan...")
    monitor = IDRCMonitor(token, reserve)
    monitor.sync()

    # Cetak dashboard
    monitor.print_dashboard()

if __name__ == "__main__":
    main()
