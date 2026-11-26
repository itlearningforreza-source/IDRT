"""
SOURCE_REGISTRY - Master Prompt V4, Part III (3.2) + Master XXIII (12).

Registry of every data source used by the research system. Each dataset must
carry metadata. Data from sources that cannot be verified is not used.
"""

from datetime import datetime, timezone

NOW = datetime.now(timezone.utc).isoformat()

SOURCE_REGISTRY = {
    "bi_databank_inflation_gdp": {
        "source_name": "Bank Indonesia - Databank Indikator Makroekonomi",
        "source_url": "https://data.bi.go.id/databank/",
        "source_type": "api_portal",
        "reliability_tier": "tier_1_official",
        "retrieval_timestamp": NOW,
        "publication_timestamp": "on_publication_date",
        "update_frequency": "daily",
        "license": "open_for_research",
        "verification_status": "pending_acquire",
    },
    "bps_senarai_data_kesejahteraan": {
        "source_name": "Badan Pusat Statistik - Data Statistik Kesejahteraan Rakyat",
        "source_url": "https://www.bps.go.id/indicator/7020/",
        "source_type": "web_portal",
        "reliability_tier": "tier_1_official",
        "retrieval_timestamp": NOW,
        "publication_timestamp": "on_publication_date",
        "update_frequency": "monthly",
        "license": "open_for_research",
        "verification_status": "pending_acquire",
    },
    "kPIKM": {
        "source_name": "Badan Pusat Statistik - KPI Konstruksi Pembangunan IKM",
        "source_url": "https://www.bps.go.id/publications/",
        "source_type": "web_portal",
        "reliability_tier": "tier_1_official",
        "retrieval_timestamp": NOW,
        "publication_timestamp": "on_publication_date",
        "update_frequency": "monthly",
        "license": "open_for_research",
        "verification_status": "pending_acquire",
    },
    "kemenkeu_keuangan_kegiatan_keuangan": {
        "source_name": "Kementerian Keuangan - Laporan Keuangan Negara (LKN)",
        "source_url": "https://www.keuangan.go.id/id/peraturan/",
        "source_type": "portal_download",
        "reliability_tier": "tier_1_official",
        "retrieval_timestamp": NOW,
        "publication_timestamp": "on_publication_date",
        "update_frequency": "annual",
        "license": "open_for_research",
        "verification_status": "pending_acquire",
    },
    "sekretariat_kebijakan": {
        "source_name": "Sekretariat Negara - Dokumen Kebijakan & Agenda Pemerintahan",
        "source_url": "https://sekretariat.info/",
        "source_type": "portal",
        "reliability_tier": "tier_1_official",
        "retrieval_timestamp": NOW,
        "publication_timestamp": "on_publication_date",
        "update_frequency": "event_driven",
        "license": "open_for_research",
        "verification_status": "pending_acquire",
    },
    "jdih_dpr_kebijakan": {
        "source_name": "DPR RI - JDIH (Undang-Undang & Peraturan)",
        "source_url": "https://jdih.setkab.go.id/",
        "source_type": "portal",
        "reliability_tier": "tier_1_official",
        "retrieval_timestamp": NOW,
        "publication_timestamp": "on_publication_date",
        "update_frequency": "continuous",
        "license": "open_for_research",
        "verification_status": "pending_acquire",
    },
    "kp_imf_indonesia": {
        "source_name": "IMF - World Economic Outlook (WEO) & Indonesia Data",
        "source_url": "https://www.imf.org/en/Publications/WEO",
        "source_type": "api",
        "reliability_tier": "tier_1_international",
        "retrieval_timestamp": NOW,
        "publication_timestamp": "semester_vintage",
        "update_frequency": "twice_yearly",
        "license": "open_for_research",
        "verification_status": "pending_acquire",
    },
    "worldbank_indonesia": {
        "source_name": "World Bank - Indonesia Data",
        "source_url": "https://data.worldbank.org/country/indonesia",
        "source_type": "api",
        "reliability_tier": "tier_1_international",
        "retrieval_timestamp": NOW,
        "publication_timestamp": "vintage_by_indicator",
        "update_frequency": "continuous",
        "license": "open_for_research",
        "verification_status": "pending_acquire",
    },
    "ministry_energy_minyak": {
        "source_name": "Kementerian ESDM - Data Harga Minyak domestik",
        "source_url": "https://esdm.go.id/",
        "source_type": "portal",
        "reliability_tier": "tier_2_provider",
        "retrieval_timestamp": NOW,
        "publication_timestamp": "on_publication_date",
        "update_frequency": "daily",
        "license": "open_for_research",
        "verification_status": "pending_acquire",
    },
}

TRUST_TIERS = ["tier_1_official", "tier_2_provider", "tier_1_international", "tier_2_media"]


def source_metadata(source_key: str) -> dict:
    return SOURCE_REGISTRY[source_key]
