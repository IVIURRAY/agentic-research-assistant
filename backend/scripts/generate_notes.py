"""Generate the synthetic research-note corpus in data/notes/.

All companies' numbers, ratings and events here are fictional, written for a demo; they are not
real research or investment advice. The corpus is deliberately shaped for evaluation: ratings
and price targets move over time (multi-hop "how has our view changed" questions), sector and
strategy notes have no ticker (filter-by-sector questions), and specific numbers appear in one
note only (precise retrieval questions).

Run:  python scripts/generate_notes.py [--out ../data/notes]
"""

from __future__ import annotations

import argparse
from pathlib import Path

DISCLAIMER = (
    "_Synthetic note for demonstration purposes. Fictional figures; not investment advice._"
)

COMPANIES = {
    "ASML": ("ASML Holding", "Semiconductors", "EUR", "Priya Raman"),
    "TSM": ("Taiwan Semiconductor Manufacturing (TSMC)", "Semiconductors", "USD", "Priya Raman"),
    "NVDA": ("NVIDIA", "Semiconductors", "USD", "Daniel Okafor"),
    "AMD": ("Advanced Micro Devices", "Semiconductors", "USD", "Daniel Okafor"),
    "MSFT": ("Microsoft", "Software", "USD", "Elena Vasquez"),
    "SAP": ("SAP", "Software", "EUR", "Elena Vasquez"),
    "JPM": ("JPMorgan Chase", "Banks", "USD", "Marcus Feld"),
    "HSBA": ("HSBC Holdings", "Banks", "GBp", "Marcus Feld"),
    "NOVO": ("Novo Nordisk", "Pharmaceuticals", "DKK", "Hannah Lindqvist"),
    "AZN": ("AstraZeneca", "Pharmaceuticals", "GBp", "Hannah Lindqvist"),
    "SHEL": ("Shell", "Energy", "GBp", "Tom Achebe"),
    "BP": ("BP", "Energy", "GBp", "Tom Achebe"),
    "MC": ("LVMH", "Luxury", "EUR", "Claire Dubois"),
}

# Each note: (note_id, date, ticker, rating, previous_rating, price_target, title, sections)
# sections: list of (heading, text). ticker None => sector/strategy note with its own fields.
NOTES: list[dict] = [
    # ---------------------------------------------------------------- ASML
    dict(
        note_id="asml-2026-01-14", date="2026-01-14", ticker="ASML", rating="Hold",
        previous_rating="Hold", price_target=880,
        title="ASML: China export curbs cap 2026 upside; stay Hold",
        sections=[
            ("Summary", "We keep ASML at Hold with a EUR 880 price target. China was 41% of 2025 "
             "system sales and new Dutch licensing rules for immersion DUV tools should pull that "
             "share down sharply in 2026. We model 2026 revenue roughly flat at EUR 32.5bn."),
            ("Thesis", "The long-term EUV franchise is intact, but 2026 is a digestion year: China "
             "DUV normalisation offsets AI-driven logic demand. We want to see order intake "
             "re-accelerate and High-NA adoption broaden beyond a single customer before turning "
             "more constructive."),
            ("Valuation", "Our EUR 880 target is 30x 2027E EPS of EUR 29.3, in line with the "
             "five-year average multiple."),
            ("Risks", "Upside risks: faster High-NA adoption at memory customers, and a stronger "
             "AI capex cycle at TSMC. Downside risks: broader US export restrictions covering "
             "servicing of the installed base in China."),
        ],
    ),
    dict(
        note_id="asml-2026-04-16", date="2026-04-16", ticker="ASML", rating="Buy",
        previous_rating="Hold", price_target=1050,
        title="ASML: Upgrade to Buy as orders inflect and High-NA broadens",
        sections=[
            ("Summary", "We upgrade ASML to Buy from Hold and raise our price target to EUR 1,050 "
             "from EUR 880. Q1 2026 net bookings were EUR 7.1bn against consensus of EUR 5.4bn, "
             "and the order book now includes two High-NA EXE:5200 systems from a memory customer."),
            ("What changed", "Our January caution rested on China normalisation. China fell to 29% "
             "of system sales in Q1, faster than we expected, yet total revenue held up because "
             "EUV demand from leading-edge logic and DRAM filled the gap. High-NA now has more "
             "than one customer, which was our key condition for turning positive."),
            ("Valuation", "EUR 1,050 is 32x 2027E EPS of EUR 32.8 (raised from EUR 29.3)."),
            ("Risks", "Order lumpiness; a pause in DRAM capex; further export restrictions."),
        ],
    ),
    dict(
        note_id="asml-2026-07-16", date="2026-07-16", ticker="ASML", rating="Buy",
        previous_rating="Buy", price_target=1120,
        title="ASML: Q2 beat, 2027 growth reaffirmed; PT to EUR 1,120",
        sections=[
            ("Summary", "Q2 2026 gross margin was 53.8%, above guidance of 51-52%, and management "
             "reaffirmed that 2027 will be a growth year. We raise our price target to EUR 1,120 "
             "and reiterate Buy."),
            ("Details", "The EUV backlog stands at EUR 38bn. Installed-base management revenue "
             "grew 14% year on year. China was 27% of system sales."),
            ("Valuation", "EUR 1,120 is 32x 2027E EPS of EUR 35.0."),
            ("Risks", "Customer timing of High-NA insertion; currency."),
        ],
    ),
    dict(
        note_id="asml-2026-09-24", date="2026-09-24", ticker="ASML", rating="Buy",
        previous_rating="Buy", price_target=1120,
        title="ASML: Field check flags High-NA timing at TSMC; stay Buy",
        sections=[
            ("Summary", "Our supply-chain checks suggest TSMC will not insert High-NA EUV at the "
             "A14 node until 2028, a year later than some investors assume. We see this as a "
             "modest risk to 2027 High-NA unit forecasts, not to the thesis, and keep Buy with "
             "an unchanged EUR 1,120 price target."),
            ("Implications", "Low-NA EUV multi-patterning at A14 is EUV-intensive in its own right, "
             "so total EUV layer counts still rise. We trim 2027 High-NA units from 14 to 11."),
            ("Risks", "If memory customers also delay High-NA, 2027 consensus would need to fall."),
        ],
    ),
    # ---------------------------------------------------------------- TSMC
    dict(
        note_id="tsm-2026-01-16", date="2026-01-16", ticker="TSM", rating="Buy",
        previous_rating="Buy", price_target=260,
        title="TSMC: AI accelerators drive ~25% 2026 growth guide",
        sections=[
            ("Summary", "TSMC guided 2026 USD revenue growth of close to 25%, with AI accelerator "
             "revenue expected to roughly double. 2026 capex guidance is USD 52-56bn. Buy, price "
             "target USD 260."),
            ("Thesis", "Leading-edge share near 100% for AI accelerators and pricing power at N3 "
             "and N2 support margins above 56% despite overseas fab dilution."),
            ("Risks", "Geopolitics across the Taiwan Strait; tariff risk on US-bound chips."),
        ],
    ),
    dict(
        note_id="tsm-2026-04-17", date="2026-04-17", ticker="TSM", rating="Buy",
        previous_rating="Buy", price_target=285,
        title="TSMC: Q1 margin strength; N2 ramp in H2; PT to USD 285",
        sections=[
            ("Summary", "Q1 2026 gross margin was 58.6%. N2 enters volume ramp in H2 2026. We "
             "raise our price target to USD 285 from USD 260; Buy."),
            ("Details", "Management expects Arizona fabs to dilute gross margin by 2-3 points in "
             "2026, more than offset by N3 utilisation and price increases."),
            ("Risks", "Tariffs; overseas cost inflation."),
        ],
    ),
    dict(
        note_id="tsm-2026-07-17", date="2026-07-17", ticker="TSM", rating="Buy",
        previous_rating="Buy", price_target=300,
        title="TSMC: CoWoS capacity to 110k wafers/month; PT to USD 300",
        sections=[
            ("Summary", "We now expect TSMC's CoWoS advanced packaging capacity to reach about "
             "110k wafers per month by end-2026, up from roughly 75k at end-2025. We raise our "
             "price target to USD 300 and keep Buy."),
            ("Details", "Advanced packaging is the binding constraint on AI accelerator supply; "
             "the expansion supports our view that AI revenue doubles again in 2027."),
            ("Risks", "Packaging yield on larger interposers; customer concentration."),
        ],
    ),
    # ---------------------------------------------------------------- NVDA
    dict(
        note_id="nvda-2026-02-26", date="2026-02-26", ticker="NVDA", rating="Buy",
        previous_rating="Buy", price_target=230,
        title="NVIDIA: Data center beats again; Rubin on track for H2",
        sections=[
            ("Summary", "Fiscal Q4 data center revenue was USD 62bn. Management said the Rubin "
             "platform is on track for H2 2026 shipments. Buy, price target USD 230."),
            ("Thesis", "Full-stack advantage (CUDA, networking, systems) keeps NVIDIA the default "
             "for frontier training and increasingly for inference."),
            ("Risks", "Custom ASIC competition at hyperscalers; export controls."),
        ],
    ),
    dict(
        note_id="nvda-2026-05-28", date="2026-05-28", ticker="NVDA", rating="Buy",
        previous_rating="Buy", price_target=250,
        title="NVIDIA: 74% gross margin, China excluded from guide",
        sections=[
            ("Summary", "Gross margin was 74.1%. Guidance assumes zero China data center revenue. "
             "We raise our price target to USD 250; Buy."),
            ("Details", "Networking revenue grew faster than compute for the second quarter in a "
             "row as customers build larger clusters."),
            ("Risks", "Power availability limiting data center build-outs."),
        ],
    ),
    dict(
        note_id="nvda-2026-08-27", date="2026-08-27", ticker="NVDA", rating="Buy",
        previous_rating="Buy", price_target=265,
        title="NVIDIA: Rubin shipments begin; 2027 hyperscaler capex up ~30%",
        sections=[
            ("Summary", "Rubin shipments began in the quarter. Our hyperscaler capex tracker now "
             "points to roughly 30% growth in 2027. Price target to USD 265; Buy."),
            ("Risks", "Digestion after two years of extreme growth; ASIC share gains."),
        ],
    ),
    # ---------------------------------------------------------------- AMD
    dict(
        note_id="amd-2026-02-04", date="2026-02-04", ticker="AMD", rating="Hold",
        previous_rating="Hold", price_target=190,
        title="AMD: MI400 timing uncertain; stay Hold",
        sections=[
            ("Summary", "Hold, USD 190 price target. Client CPU share gains continue, but we lack "
             "visibility on the timing of the MI400 accelerator ramp."),
            ("Risks", "Upside: an anchor hyperscaler or AI lab deployment at scale."),
        ],
    ),
    dict(
        note_id="amd-2026-05-06", date="2026-05-06", ticker="AMD", rating="Hold",
        previous_rating="Hold", price_target=200,
        title="AMD: DC GPU USD 3.1bn; OpenAI deployment starts H2",
        sections=[
            ("Summary", "Data center GPU revenue was USD 3.1bn in Q1. The OpenAI deployment starts "
             "in H2 2026. PT to USD 200; Hold until we see rack-scale shipments."),
            ("Risks", "Software ecosystem maturity (ROCm) versus CUDA."),
        ],
    ),
    dict(
        note_id="amd-2026-08-05", date="2026-08-05", ticker="AMD", rating="Buy",
        previous_rating="Hold", price_target=240,
        title="AMD: Upgrade to Buy on Helios rack-scale shipments",
        sections=[
            ("Summary", "We upgrade AMD to Buy from Hold with a USD 240 price target (from USD 200). "
             "The catalyst is the start of MI450 Helios rack-scale shipments and H2 2026 data "
             "center GPU guidance above USD 6bn."),
            ("Risks", "Execution on rack-scale systems; customer concentration."),
        ],
    ),
    # ---------------------------------------------------------------- MSFT
    dict(
        note_id="msft-2026-01-29", date="2026-01-29", ticker="MSFT", rating="Buy",
        previous_rating="Buy", price_target=600,
        title="Microsoft: Azure +38% cc; capex USD 35bn a quarter",
        sections=[
            ("Summary", "Azure grew 38% in constant currency. Capex is running at about USD 35bn "
             "per quarter. Buy, USD 600 price target."),
            ("Risks", "Capacity constraints delaying Azure revenue; capex returns."),
        ],
    ),
    dict(
        note_id="msft-2026-04-30", date="2026-04-30", ticker="MSFT", rating="Buy",
        previous_rating="Buy", price_target=620,
        title="Microsoft: Copilot reaches 30m seats; Azure +37%",
        sections=[
            ("Summary", "Microsoft 365 Copilot reached 30 million paid seats. Azure growth eased "
             "slightly to 37% in constant currency from 38%. PT to USD 620; Buy."),
            ("Risks", "Seat-based monetisation pressure as agents replace users."),
        ],
    ),
    dict(
        note_id="msft-2026-07-30", date="2026-07-30", ticker="MSFT", rating="Buy",
        previous_rating="Buy", price_target=650,
        title="Microsoft: FY27 capex growth to slow; margins hold at 46%",
        sections=[
            ("Summary", "Management said FY27 capex growth will slow from FY26 levels. Operating "
             "margin held at 46%. PT to USD 650; Buy."),
        ],
    ),
    # ---------------------------------------------------------------- SAP
    dict(
        note_id="sap-2026-01-30", date="2026-01-30", ticker="SAP", rating="Buy",
        previous_rating="Buy", price_target=300,
        title="SAP: Cloud backlog EUR 78bn, +28%",
        sections=[
            ("Summary", "Total cloud backlog reached EUR 78bn, up 28%. Current cloud backlog grew "
             "27%. Buy, EUR 300 price target."),
            ("Risks", "Deal slippage in public sector; AI disrupting seat-based ERP pricing."),
        ],
    ),
    dict(
        note_id="sap-2026-04-23", date="2026-04-23", ticker="SAP", rating="Hold",
        previous_rating="Buy", price_target=250,
        title="SAP: Downgrade to Hold as backlog growth decelerates",
        sections=[
            ("Summary", "We downgrade SAP to Hold from Buy and cut our price target to EUR 250 from "
             "EUR 300. Current cloud backlog growth decelerated to 22% from 27%, and several US "
             "public sector deals slipped out of the quarter."),
            ("Why now", "Our Buy case relied on backlog growth staying above 25% through 2026. "
             "With that broken, the valuation premium to software peers looks hard to defend."),
            ("Risks", "Upside: re-acceleration from Business Data Cloud."),
        ],
    ),
    dict(
        note_id="sap-2026-07-22", date="2026-07-22", ticker="SAP", rating="Hold",
        previous_rating="Hold", price_target=245,
        title="SAP: Business Data Cloud traction, backlog growth 21%",
        sections=[
            ("Summary", "Business Data Cloud is gaining traction, but current cloud backlog growth "
             "slowed again to 21%. PT to EUR 245; Hold."),
        ],
    ),
    # ---------------------------------------------------------------- JPM
    dict(
        note_id="jpm-2026-01-14", date="2026-01-14", ticker="JPM", rating="Hold",
        previous_rating="Hold", price_target=310,
        title="JPMorgan: Best-in-class, fully valued at 2.4x TBV",
        sections=[
            ("Summary", "NII ex-markets guidance is about USD 95bn for 2026. The franchise is best "
             "in class but the stock trades at 2.4x tangible book. Hold, USD 310 price target."),
        ],
    ),
    dict(
        note_id="jpm-2026-04-14", date="2026-04-14", ticker="JPM", rating="Hold",
        previous_rating="Hold", price_target=315,
        title="JPMorgan: IB fees +18%; card charge-offs 3.6%",
        sections=[
            ("Summary", "Investment banking fees rose 18% year on year. Card net charge-offs were "
             "3.6%. PT to USD 315; Hold."),
        ],
    ),
    dict(
        note_id="jpm-2026-07-15", date="2026-07-15", ticker="JPM", rating="Hold",
        previous_rating="Hold", price_target=320,
        title="JPMorgan: CET1 15.5%, buybacks USD 8bn a quarter",
        sections=[
            ("Summary", "CET1 ratio of 15.5% supports buybacks of about USD 8bn per quarter. "
             "PT to USD 320; Hold. We have not changed our rating this year."),
        ],
    ),
    # ---------------------------------------------------------------- HSBA
    dict(
        note_id="hsba-2026-02-25", date="2026-02-25", ticker="HSBA", rating="Buy",
        previous_rating="Buy", price_target=1150,
        title="HSBC: Mid-teens RoTE target, USD 3bn buyback",
        sections=[
            ("Summary", "HSBC targets a mid-teens return on tangible equity for 2026-28 and "
             "announced a USD 3bn buyback. Buy, 1,150p price target."),
            ("Risks", "Hong Kong commercial real estate; lower HIBOR compressing NII."),
        ],
    ),
    dict(
        note_id="hsba-2026-05-05", date="2026-05-05", ticker="HSBA", rating="Buy",
        previous_rating="Buy", price_target=1200,
        title="HSBC: Hong Kong CRE provisions manageable",
        sections=[
            ("Summary", "Hong Kong commercial real estate provisions of USD 0.9bn in Q1 were "
             "manageable relative to pre-provision profit. PT to 1,200p; Buy."),
            ("Risks", "Further CRE stress; China growth."),
        ],
    ),
    dict(
        note_id="hsba-2026-07-30", date="2026-07-30", ticker="HSBA", rating="Buy",
        previous_rating="Buy", price_target=1250,
        title="HSBC: NII guide raised to USD 43bn+",
        sections=[
            ("Summary", "HSBC raised 2026 banking NII guidance to USD 43bn or more. PT to 1,250p; "
             "Buy."),
        ],
    ),
    # ---------------------------------------------------------------- NOVO
    dict(
        note_id="novo-2026-02-05", date="2026-02-05", ticker="NOVO", rating="Buy",
        previous_rating="Buy", price_target=520,
        title="Novo Nordisk: Oral Wegovy launch supports 2026 guide",
        sections=[
            ("Summary", "Novo guided 2026 sales growth of 5-9% at constant exchange rates. The oral "
             "Wegovy pill launched in the US in January. Buy, DKK 520 price target."),
            ("Risks", "US pricing; compounded semaglutide; competition from tirzepatide."),
        ],
    ),
    dict(
        note_id="novo-2026-03-19", date="2026-03-19", ticker="NOVO", rating="Hold",
        previous_rating="Buy", price_target=400,
        title="Novo Nordisk: Downgrade to Hold on US pricing and CagriSema",
        sections=[
            ("Summary", "We downgrade Novo Nordisk to Hold from Buy and cut our price target to "
             "DKK 400 from DKK 520. US net price cuts under the most-favoured-nation agreement are "
             "deeper than we modelled, compounded semaglutide persists, and CagriSema's REDEFINE 4 "
             "head-to-head data underwhelmed against tirzepatide."),
            ("Risks", "Upside: faster oral Wegovy uptake."),
        ],
    ),
    dict(
        note_id="novo-2026-06-18", date="2026-06-18", ticker="NOVO", rating="Hold",
        previous_rating="Hold", price_target=380,
        title="Novo Nordisk: Oral Wegovy at 250k weekly scripts; patent cliffs abroad",
        sections=[
            ("Summary", "Oral Wegovy reached about 250k weekly US prescriptions. Semaglutide patent "
             "expiries in Canada, China and Brazil during 2026 add generic pressure. PT to "
             "DKK 380; Hold."),
        ],
    ),
    dict(
        note_id="novo-2026-09-10", date="2026-09-10", ticker="NOVO", rating="Hold",
        previous_rating="Hold", price_target=360,
        title="Novo Nordisk: Amycretin phase 3 starts; guide narrowed",
        sections=[
            ("Summary", "Amycretin entered phase 3 and Novo narrowed its 2026 guidance to the lower "
             "half of the range. PT to DKK 360; Hold."),
        ],
    ),
    # ---------------------------------------------------------------- AZN
    dict(
        note_id="azn-2026-02-10", date="2026-02-10", ticker="AZN", rating="Buy",
        previous_rating="Buy", price_target=15500,
        title="AstraZeneca: On track for USD 80bn 2030 ambition",
        sections=[
            ("Summary", "AstraZeneca reiterated its USD 80bn 2030 revenue ambition and guided 2026 "
             "to high-single-digit growth. Buy, 15,500p price target."),
        ],
    ),
    dict(
        note_id="azn-2026-04-29", date="2026-04-29", ticker="AZN", rating="Buy",
        previous_rating="Buy", price_target=16000,
        title="AstraZeneca: Baxdrostat filed; Enhertu +30%",
        sections=[
            ("Summary", "Baxdrostat was filed for hypertension and Enhertu grew 30%. PT to "
             "16,000p; Buy."),
        ],
    ),
    dict(
        note_id="azn-2026-07-29", date="2026-07-29", ticker="AZN", rating="Buy",
        previous_rating="Buy", price_target=16500,
        title="AstraZeneca: NYSE listing done, camizestrant approved",
        sections=[
            ("Summary", "AstraZeneca completed its NYSE direct listing and camizestrant was "
             "approved. We raise our price target to 16,500p; Buy."),
            ("Valuation", "16,500p is a sum-of-the-parts DCF assuming 8% revenue CAGR to 2030 and "
             "a 7.5% WACC."),
        ],
    ),
    # ---------------------------------------------------------------- SHEL
    dict(
        note_id="shel-2026-02-05", date="2026-02-05", ticker="SHEL", rating="Buy",
        previous_rating="Buy", price_target=3100,
        title="Shell: USD 3.5bn buyback, LNG growth 4-5% a year",
        sections=[
            ("Summary", "Shell kept its quarterly buyback at USD 3.5bn and targets LNG volume growth "
             "of 4-5% a year. Buy, 3,100p price target."),
        ],
    ),
    dict(
        note_id="shel-2026-05-07", date="2026-05-07", ticker="SHEL", rating="Buy",
        previous_rating="Buy", price_target=3050,
        title="Shell: Brent deck cut to USD 65; buyback trimmed",
        sections=[
            ("Summary", "We cut our Brent assumption to USD 65/bbl from USD 72. Shell trimmed its "
             "quarterly buyback to USD 3.0bn with Q1 results. PT to 3,050p; Buy."),
        ],
    ),
    dict(
        note_id="shel-2026-07-31", date="2026-07-31", ticker="SHEL", rating="Buy",
        previous_rating="Buy", price_target=3050,
        title="Shell: Integrated gas carries the quarter; net debt USD 41bn",
        sections=[
            ("Summary", "Integrated gas margins carried Q2. Net debt was USD 41bn. Buy, 3,050p "
             "unchanged."),
        ],
    ),
    # ---------------------------------------------------------------- BP
    dict(
        note_id="bp-2026-02-11", date="2026-02-11", ticker="BP", rating="Sell",
        previous_rating="Sell", price_target=380,
        title="BP: Gearing too high for the reset to work; Sell",
        sections=[
            ("Summary", "Gearing of 25% leaves little room for the strategy reset. Proceeds from a "
             "Castrol sale are the key swing factor. Sell, 380p price target."),
        ],
    ),
    dict(
        note_id="bp-2026-05-06", date="2026-05-06", ticker="BP", rating="Sell",
        previous_rating="Sell", price_target=370,
        title="BP: Buyback cut to USD 0.75bn; gearing 26%",
        sections=[
            ("Summary", "BP cut its quarterly buyback to USD 0.75bn and gearing rose to 26%. PT to "
             "370p; Sell."),
        ],
    ),
    dict(
        note_id="bp-2026-08-05", date="2026-08-05", ticker="BP", rating="Hold",
        previous_rating="Sell", price_target=420,
        title="BP: Upgrade to Hold as Castrol sale closes",
        sections=[
            ("Summary", "We upgrade BP to Hold from Sell and raise our price target to 420p from "
             "370p. The USD 10bn Castrol sale closed and gearing fell to 21%."),
            ("Why now", "Balance sheet repair was our main concern; with gearing at 21% the "
             "downside case is less likely. Activist pressure from Elliott keeps capital "
             "discipline in focus."),
        ],
    ),
    # ---------------------------------------------------------------- LVMH
    dict(
        note_id="mc-2026-01-28", date="2026-01-28", ticker="MC", rating="Hold",
        previous_rating="Hold", price_target=620,
        title="LVMH: Weak China keeps Fashion & Leather negative",
        sections=[
            ("Summary", "Fashion & Leather organic sales fell 3% in Q4 2025 on weak Chinese demand. "
             "Hold, EUR 620 price target."),
        ],
    ),
    dict(
        note_id="mc-2026-04-15", date="2026-04-15", ticker="MC", rating="Hold",
        previous_rating="Hold", price_target=600,
        title="LVMH: Q1 organic -2%; US tariffs bite",
        sections=[
            ("Summary", "Group organic sales fell 2% in Q1 2026. A 15% US tariff on EU goods is a "
             "headwind to margins. PT to EUR 600; Hold."),
        ],
    ),
    dict(
        note_id="mc-2026-07-24", date="2026-07-24", ticker="MC", rating="Buy",
        previous_rating="Hold", price_target=680,
        title="LVMH: Upgrade to Buy as Fashion & Leather turns positive",
        sections=[
            ("Summary", "We upgrade LVMH to Buy from Hold with a EUR 680 price target. Fashion & "
             "Leather returned to +1% organic growth in Q2 2026 and we think margins have "
             "troughed."),
        ],
    ),
    # ---------------------------------------------------------------- Sector / strategy
    dict(
        note_id="sector-semis-2026-03-05", date="2026-03-05", ticker=None, sector="Semiconductors",
        analyst="Priya Raman",
        title="Semicap 2026 outlook: EUV strength versus China DUV normalisation",
        sections=[
            ("Summary", "China equipment spending should fall 20-25% in 2026 as stockpiling ends, "
             "while leading-edge EUV demand rises. We prefer EUV-exposed names over China-exposed "
             "deposition and etch suppliers."),
        ],
    ),
    dict(
        note_id="sector-semis-2026-09-15", date="2026-09-15", ticker=None, sector="Semiconductors",
        analyst="Daniel Okafor",
        title="AI capex: second-half 2026 check",
        sections=[
            ("Summary", "Our H2 2026 check shows no sign of an AI capex slowdown: the top four "
             "hyperscalers are on track for about USD 520bn of 2026 capex and early 2027 budgets "
             "imply roughly 30% growth. Power and packaging, not demand, are the constraints."),
            ("Risks", "A financing pullback by neoclouds; inference efficiency gains reducing "
             "compute needs."),
        ],
    ),
    dict(
        note_id="sector-banks-2026-03-12", date="2026-03-12", ticker=None, sector="Banks",
        analyst="Marcus Feld",
        title="European banks: Rate cuts and capital return",
        sections=[
            ("Summary", "European bank NII has proven more resilient to rate cuts than feared due to "
             "structural hedges. Capital return yields of 8-10% remain attractive; we prefer "
             "banks with excess capital and hedge tailwinds such as HSBC."),
        ],
    ),
    dict(
        note_id="sector-pharma-2026-05-20", date="2026-05-20", ticker=None,
        sector="Pharmaceuticals", analyst="Hannah Lindqvist",
        title="Obesity market: price erosion scenarios",
        sections=[
            ("Summary", "We model US GLP-1 net prices falling 35-45% by 2030 as volume expands "
             "through oral formulations and Medicare coverage. In our base case the obesity "
             "market still reaches USD 120bn by 2030, but the incumbents' share falls as "
             "competition and generics in ex-US markets arrive."),
        ],
    ),
    dict(
        note_id="sector-energy-2026-06-10", date="2026-06-10", ticker=None, sector="Energy",
        analyst="Tom Achebe",
        title="Oil majors: Buyback sustainability at USD 65 Brent",
        sections=[
            ("Summary", "At USD 65 Brent, we estimate Shell can sustain buybacks of about USD 3bn a "
             "quarter from free cash flow, while BP cannot fund more than USD 0.75bn without "
             "raising gearing. Balance sheet strength is the key differentiator."),
        ],
    ),
    dict(
        note_id="sector-software-2026-06-24", date="2026-06-24", ticker=None, sector="Software",
        analyst="Elena Vasquez",
        title="Software: Seat-based pricing under AI pressure",
        sections=[
            ("Summary", "AI agents threaten seat-based pricing as headcount stops tracking usage. "
             "Vendors with consumption or outcome-based pricing (hyperscalers, data platforms) "
             "are better placed than per-seat application vendors. We expect a shift to hybrid "
             "seat-plus-consumption models through 2027."),
        ],
    ),
    dict(
        note_id="sector-luxury-2026-09-03", date="2026-09-03", ticker=None, sector="Luxury",
        analyst="Claire Dubois",
        title="Luxury: Early China recovery signals",
        sections=[
            ("Summary", "Mainland China luxury spending stabilised in July and August, with Hainan "
             "duty-free sales up for the first time in eight quarters. We see this as an early "
             "recovery signal, supporting our Buy on LVMH."),
        ],
    ),
    dict(
        note_id="strategy-2026-01-07", date="2026-01-07", ticker=None, sector="Strategy",
        analyst="Research Committee",
        title="2026 house view: Top picks",
        sections=[
            ("Summary", "Our six top picks for 2026 are TSMC, NVIDIA, Microsoft, SAP, HSBC and "
             "AstraZeneca. The theme is AI infrastructure plus quality compounders with "
             "visible capital return."),
        ],
    ),
    dict(
        note_id="strategy-2026-07-08", date="2026-07-08", ticker=None, sector="Strategy",
        analyst="Research Committee",
        title="Mid-year top picks update",
        sections=[
            ("Summary", "We remove SAP from our top picks following our April downgrade and add "
             "ASML after its upgrade to Buy. The updated list is TSMC, NVIDIA, ASML, Microsoft, "
             "HSBC and AstraZeneca."),
        ],
    ),
]


def render(note: dict) -> str:
    ticker = note.get("ticker")
    lines = ["---", f"note_id: {note['note_id']}", f"title: \"{note['title']}\""]
    if ticker:
        company, sector, ccy, analyst = COMPANIES[ticker]
        lines += [
            f"ticker: {ticker}",
            f"company: \"{company}\"",
            f"sector: {sector}",
            f"rating: {note['rating']}",
            f"previous_rating: {note['previous_rating']}",
            f"price_target: {note['price_target']}",
            f"currency: {ccy}",
            f"analyst: \"{analyst}\"",
        ]
    else:
        lines += [f"sector: {note['sector']}", f"analyst: \"{note['analyst']}\""]
    lines += [f"date: {note['date']}", "---", "", f"# {note['title']}", ""]
    for heading, text in note["sections"]:
        lines += [f"## {heading}", "", text, ""]
    lines += [DISCLAIMER, ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "data/notes"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for note in NOTES:
        (out / f"{note['note_id']}.md").write_text(render(note))
    print(f"wrote {len(NOTES)} notes to {out}")


if __name__ == "__main__":
    main()
