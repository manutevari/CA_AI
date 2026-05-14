"""Official Income Tax Department ITR filing links for the Streamlit UI."""

from __future__ import annotations

from dataclasses import dataclass


OFFICIAL_DOWNLOADS_URL = "https://www.incometax.gov.in/iec/foportal/downloads/income-tax-returns"
OFFICIAL_ONLINE_ITR_URL = "https://www.incometax.gov.in/iec/foportal/newdownloads/itr"
EFILE_LOGIN_URL = "https://eportal.incometax.gov.in/iec/foservices/#/login"
EFILE_HOME_URL = "https://www.incometax.gov.in/iec/foportal/?nextPage=efileForms"
NOTIFIED_FORMS_URL = "https://incometaxindia.gov.in/Pages/downloads/income-tax-return.aspx"


@dataclass(frozen=True)
class ITRFormLink:
    form: str
    title: str
    applies_to: str
    online_help_url: str | None = None
    download_url: str | None = None
    schema_url: str | None = None
    latest_release: str | None = None
    notes: str = ""


CURRENT_ONLINE_FORMS = [
    ITRFormLink(
        form="ITR-1",
        title="SAHAJ",
        applies_to="Resident individuals with income up to Rs.50 lakh from salary/pension, one house property, other sources, eligible 112A LTCG up to Rs.1.25 lakh, and agricultural income up to Rs.5,000.",
        online_help_url="https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/file-itr-1-sahaj-online",
        notes="Use only if there is no business/profession income and no disqualifying foreign/director/unlisted equity cases.",
    ),
    ITRFormLink(
        form="ITR-2",
        title="Individuals / HUF without business income",
        applies_to="Individuals and HUFs not having income from profits and gains of business or profession.",
        online_help_url="https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/file-itr-2-online",
        notes="Typical upgrade path when ITR-1 is not eligible, for example multiple house properties or broader capital gains.",
    ),
    ITRFormLink(
        form="ITR-3",
        title="Individuals / HUF with business income",
        applies_to="Individuals and HUFs having income from profits and gains of business or profession.",
        online_help_url=OFFICIAL_ONLINE_ITR_URL,
        notes="Select inside the e-filing portal if business/profession schedules are needed.",
    ),
    ITRFormLink(
        form="ITR-4",
        title="SUGAM",
        applies_to="Resident individuals, HUFs, and firms other than LLP with total income up to Rs.50 lakh and presumptive business/profession income under sections 44AD, 44ADA, or 44AE.",
        online_help_url="https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/file-itr-4-sugam-online",
        notes="Use for eligible presumptive taxation cases only.",
    ),
]


LATEST_DOWNLOAD_UTILITIES = [
    ITRFormLink(
        form="Common Offline Utility",
        title="ITR-1 to ITR-4",
        applies_to="Common offline utility for ITR-1, ITR-2, ITR-3, and ITR-4.",
        download_url="https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-01/ITDe-Filing-2025-Setup-1.2.9.zip",
        latest_release="27-Jan-2026",
        notes="Latest offline utility listed on the official downloads page for AY 2025-26.",
    ),
    ITRFormLink(
        form="ITR-1",
        title="Excel utility",
        applies_to="Resident individuals eligible for SAHAJ.",
        download_url="https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-04/ITR1_AY_25-26_V1.7.zip",
        schema_url=OFFICIAL_DOWNLOADS_URL,
        latest_release="09-Apr-2026",
        notes="Excel utility listed by the portal for AY 2025-26.",
    ),
    ITRFormLink(
        form="ITR-2",
        title="Excel utility",
        applies_to="Individuals and HUFs without business/profession income.",
        download_url="https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-04/ITR2_AY_25-26_V1.5_0.zip",
        schema_url=OFFICIAL_DOWNLOADS_URL,
        latest_release="24-Feb-2026",
        notes="Excel utility listed by the portal for AY 2025-26.",
    ),
    ITRFormLink(
        form="ITR-3",
        title="Excel utility",
        applies_to="Individuals and HUFs with business/profession income.",
        download_url=OFFICIAL_DOWNLOADS_URL,
        schema_url=OFFICIAL_DOWNLOADS_URL,
        latest_release="27-Feb-2026",
        notes="Open official downloads page if the direct asset path changes.",
    ),
    ITRFormLink(
        form="ITR-4",
        title="Excel utility",
        applies_to="Eligible presumptive taxation cases.",
        download_url="https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-01/ITR4_AY_25-26_V1.6.zip",
        schema_url=OFFICIAL_DOWNLOADS_URL,
        latest_release="06-Jan-2026",
        notes="Excel utility listed by the portal for AY 2025-26.",
    ),
]


def recommend_itr_form(
    *,
    has_business_income: bool,
    presumptive_taxation: bool,
    has_capital_gains: bool,
    total_income: float,
) -> str:
    if has_business_income:
        return "ITR-4" if presumptive_taxation and total_income <= 5_000_000 else "ITR-3"
    if has_capital_gains or total_income > 5_000_000:
        return "ITR-2"
    return "ITR-1"
