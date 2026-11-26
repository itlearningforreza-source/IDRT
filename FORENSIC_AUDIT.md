# FORENSIC AUDIT - MASTER PROMPT V4 (Phase 1)

**Tanggal audit:** 2026-11-24
**Target audited:**
- `Unduhan/ai_arah_politik_prabowo (1).ipynb` (123 cell) - notebook primer
- `Unduhan/ai_arah_politik_prabowo.ipynb` (33 cell) - notebook sekunder (subset/duplikat)

**Metodologi:** Pembacaan seluruh kode aktual (source + output stream/display_data), bukan judul/komentar. Sumber data audited: digests yang diekstrak (terverifikasi konsisten dengan source notebook).

---

## A. CLASSIFICATION SYSTEM
- **CRITICAL** - mengakibatkan hasil penelitian tidak valid / invalidates empirical claims.
- **HIGH** - model tidak stabil / performa tidak dapat dipercaya / kontaminasi data.
- **MEDIUM** - mengurangi efisiensi atau kualitas analisis.
- **LOW** - dokumentasi / maintainability.

---

## B. FINDINGS TABLE

| # | Kategori | Tingkat | Findings (Cell, Statistik Affected, Konsekuensi) | Metode Perbaikan |
|---|----------|---------|--------------------------------------------------|------------------|
| F-01 | S-01 | CRITICAL | Synthetic data sebagai empirical training evidence (Cells 8, 46, 91, 107, 118). Generator AR(1) + np.random bukan sumber aktual. Semua metrik empiris (PSI, backtest, accuracy) tidak bermakna. | Phase 2/3: ganti dengan data aktual; gaussa/AR(1) SATU-SATUNYA untuk unit testing. Acceptance: "Synthetic tidak digunakan sebagai empirical training evidence." |
| F-02 | S-02 | CRITICAL (indirect) | Drif bersifat fabricasi: `political_stability_index` PSI = 3.50, `gdp_growth_annualized` PSI = 0.55 - konsekuensi: retraining otomatis tersensorisasi di data palsu. | Real acquisition (Phase 3); retraining hanya dipicu pada data verifikasi sumber. |
| F-03 | S-03 | HIGH | Target overlap: `target_reg_30d` (t..t+30) dan `target_reg_7d` (t..t+7) naik melintang; ambigu interpretasi horizon. Master: "overlapping target horizons" - anti-pattern. | Redefine: horizons disjoint; revalidasi MV (Master 5.1). |
| F-04 | S-04 | HIGH | Threshold labels: quantile 0.67/0.33 dari seluruh series (Cell 14). Master: utamakan threshold substantif / training data saja. | Compute thresholds di TRAIN fold saja; event-based outcomes jika relevan; rerun label consistency test. |
| F-05 | S-05 | MEDIUM | No walk-forward validation - hanya Train/Val/Test (Cells 23, 95). Master 11.2 - wajib expanding/rolling window. | Implement walk-forward; nested temporal (Master 11.4). |
| F-06 | S-06 | HIGH | Test-set tuning: threshold pemicu retraining mae_threshold=0.045 dipilih pada test set (Cells 97, 98, 122). Violasi "Jangan melakukan tuning berdasarkan test set." | Threshold dari val fold atau heuristik substantif; sampel estimasi matematis. |
| F-07 | S-07 | MEDIUM | Duplicate/inconsistent cells: 35~37, 39~41~43~48, regenerate cells 45-46 & 91-95 mengubah state yang digunakan sebelumnya - tidak ada assurance deterministik restart-from-scratch. | Refactor: single data acquisition module; Run All dengan kerja bersih; deterministic seeds. |
| F-08 | S-08 | MEDIUM | Execution errors: NameError mae_normal (Cell 102), NameError y_true_cls (Cell 105), NameError opt_xgb_cls_7d/best_models (Cells 91, 41, 43). | Refactor konsisten; automated tests (Master XXII) wajib lulus dari runtime kosong. |
| F-10 | S-10 | MEDIUM | PSI NaN-handling: bucket zero-count -> 0.0001/len - distribusi bertambah; PSI sensitif murah. Selain itu PSI dihitung X_train vs X_test - bukan data aktual (masih F-01). | Guard dengan min bucket, ordinal checks; rerun pada data real. |
| F-11 | S-11 | LOW | Ensemble: rata-rata sederhana (Cells 35/37/39/41). Master 14 meminta validation-weighted ensemble + temporal OOF stacking. | Tambah validation-weighted ensemble + OOF stacking (jika data mencukupi). |
| F-12 | S-12 | HIGH | Calibration sekunder pada X_test - acceptable standar; dalam Cell 118 fallback (dirichlet random) menggambarkan "fallback palsu". | Remove fabricated fallbacks (Master XXI). |
| F-13 | S-13 | CRITICAL | Fallback data palsu: Cells 91, 107, 118 meregenerasi data dari RNG jika pkl tidak ada (dirichlet random, np.random.normal placeholder); outputs Cell 91 "PROJECT STATUS ... 0 Errors" berasal dari fictional review. | Remove semua fallback; if data unavailable -> stop with error (Master XXI). |
| F-14 | S-14 | MEDIUM | `predict_political_direction` (Cell 63) menggunakan `df_raw.tail(31)` sebagai "test" - data sendiri, standar inference mock. | Set prediction_timestamp eksplisit (Master 3.3). |
| F-15 | S-15 | MEDIUM | Feature-set tidak penuh: central_bank_rate, election_year ada; beberapa lag/rolling per-level (7 vs 30); lag 0 tidak di-apply pada policy_* dummies. | Enumerate full feature registry (Master 7). |
| F-16 | S-16 | LOW | Missing Source Registry metadata per dataset (Master 3.2 violated - no source_url, publication_timestamp, license). | Sumber acquisition baru wajib SOURCE_REGISTRY. |
| F-17 | S-17 | LOW | Plots hard-coded saves; no deterministic paths. | Standardized artifact versioning (artifacts/v1/...). |
| F-18 | S-18 | MEDIUM | Commit on GitHub - built from local data, tidak ada lineage data. | Data lineage: SHA256 data snapshot + source registry. |

---

## C. KONSEQUENSI STATISTIK & ENTABILITAS

| Finding | Statistik terdampak | Dampak pada Research Report |
|---------|--------------------|-----------------------------|
| F-01 (Sintetis) | Semua MAE/Accuracy/PSI | Semua dinyatakan "empiris" - tidak memiliki construct validity |
| F-02 (Drift) | PSI>0.25 pada 2 var | Retraining trigger diaktifkan pada data palsu - bias agresif |
| F-03 (Overlap) | Interpretasi Target B/C (Master 5.1) | Ambiguitas definisi target -> label tidak tersusun rapi |
| F-04 (Threshold full-series) | Quantile labels | label distribution tidak dikontrol training fold (leak concept) |
| F-13 (Fallback palsu) | Dirichlet/normal fallback | "Calibration improves accuracy" claims tidak terbukti - log loss menurun karena fallback |

---

## D. METODE PERBAIKAN (Remediation Methods) - rincian di Phase 2-6

1. **Phase 2 - Remove Invalid Synthetic Research Logic:**
   - Ganti generator data sintetis -> data aktual (Phase 3).
   - Hapus generate_ar1, Cells 8, 46, 91, 107 regenerations.
   - Convert duplication Cells 35/37/39/41/43/48 -> single pipeline.
2. **Phase 3 - Real Data Acquisition:** Hubungi sumber aktual dari SOURCE_REGISTRY (Phase 4): BI (inflation, gdp growth), Bank Indonesia, Kementerian Keuangan, Sekretariat Negara, JDIH DPR, etc. point-in-time retrieval; document publication timestamps.
3. **Phase 4 - Point-in-time architecture:** observation_date/event_date/publication_date/prediction_timestamp split (Master 3.3).
4. **Phase 5 - Target reconstruction:** Multi-target (Master 5): Policy Direction/Continuity/Implementation/Legislative Outcome/Event Occurrence/Agenda Momentum. Codebook + adjudication.
5. **Phase 6 - Walk-forward & purged validation** (Master 11): chronological split, expanding/rolling window, purge overlaps (embargo).
6. **Phase 7-9 - Feature engineering & validation:** Full registry (Master 7.1-7.6), feature_availability_at.
7. **Phase 10 - Baselines:** persistence, majority, logistic regression.
8. **Phase 11-12 - XGBoost & LightGBM optimization:** constrained Optuna + early stopping + nested temporal CV (Master 11.4).
9. **Phase 13 - Ensemble & calibration:** temporal OOF stacking + validation-weighted.
10. **Phase 14 - Historical replay** (Master 16).
11. **Phase 15 - Uncertainty & robustness:** block bootstrap CIs, conformal prediction.
12. **Phase 16 - Explainability:** SHAP on train-comparable holdout.
13. **Phase 17 - Drift & retraining:** threshold dari val fold.
14. **Phase 18 - Research report:** Master XXIII format dengan real outputs saja.

---

## E. ACCEPTANCE CHECKLIST (Progress Phase 1 -> 2)

- [x] 123 cell diaudit (notebook (1)) + 33 cell diaudit (notebook utama)
- [x] FORENSIC_AUDIT.md tercipta (ini)
- [ ] Synthetic data tidak digunakan sebagai empirical training evidence -> Phase 2
- [ ] Seluruh data aktual mempunyai sumber -> Phase 3
- [ ] Target definisi operasional -> Phase 5
- [ ] Label dokumentasi -> Phase 5

---

## F. Recommendation

Proyek saat ini INVALID empiris (F-01, F-02 CRITICAL). Rebuild dari ground-up: (1) real data acquisition dengan SOURCE_REGISTRY, (2) acceptance gating on synthetic-free runs. Rekomendasi: jangan lanjut ke "Empirical Results" dengan data ini; jalankan Phase 2-4 lebih dulu sebelum optimalisasi model.

Status saat ini: P0-validate-rebuild (Mulai Phase 2).
