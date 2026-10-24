"""Extra sections for the synthetic notes, so each note reads like real research: several
sections, several paragraphs each, which gives paragraph-level chunking something to work with.

Rules (checked by generate_notes.py): the added text contains no digits, so it never introduces
a price target, date or figure that could compete with the facts the evals test; the original
sections stay verbatim. Each entry: note_id -> list of (heading, [paragraphs]), inserted before
the note's Risks section (or at the end).
"""

from __future__ import annotations

EXPANSIONS: dict[str, list[tuple[str, list[str]]]] = {
    # ---------------------------------------------------------------- ASML
    "asml-2026-01-14": [
        ("Key debates", [
            "The bull case rests on lithography intensity rising with every node: more EUV layers "
            "per wafer at the leading edge, and High-NA eventually replacing multi-patterning. We "
            "agree with the direction but not the timing, because customers are digesting tools "
            "bought during the China pull-forward.",
            "The bear case is that China demand was borrowed from future years and that the "
            "installed-base business cannot fully offset the gap. We think servicing revenue is "
            "more resilient than the market assumes, which is why we stop short of a Sell.",
        ]),
        ("What would change our view", [
            "We would turn more positive on clear evidence that a second High-NA customer has "
            "committed to volume insertion, or on a sustained rebound in logic orders outside "
            "the largest foundry.",
        ]),
    ],
    "asml-2026-04-16": [
        ("Order book quality", [
            "The mix of the order book matters as much as its size. Memory customers have returned "
            "to EUV for advanced DRAM, which broadens the customer base and makes the backlog less "
            "dependent on a single foundry's capex plans.",
            "We also note shorter lead times on immersion tools, which suggests the China-driven "
            "congestion of last year has cleared and that the remaining backlog is weighted "
            "towards higher-value systems.",
        ]),
        ("Estimate changes", [
            "We raise our revenue and margin assumptions for next year to reflect the stronger "
            "order intake, and lift our long-term High-NA unit forecasts modestly.",
            "Our gross margin assumptions remain below management's aspiration because the early "
            "High-NA systems carry lower margins until volumes build.",
        ]),
    ],
    "asml-2026-07-16": [
        ("Management commentary", [
            "Management struck a confident tone on the growth outlook and stressed that customer "
            "conversations have shifted from whether to adopt High-NA to when. That is the change "
            "in language we were waiting for at the start of the year.",
            "On China, management described demand as normalising rather than collapsing, with "
            "mature-node customers still placing orders for immersion tools at a steadier pace.",
        ]),
        ("What we are watching", [
            "The next catalysts are memory capex budgets for next year and any update on High-NA "
            "insertion timing at the leading logic customers. Both feed directly into our unit "
            "forecasts.",
        ]),
    ],
    "asml-2026-09-24": [
        ("Field check detail", [
            "Our conversations with equipment engineers and supply-chain contacts point to the "
            "leading foundry extending current EUV multi-patterning for longer before switching "
            "to High-NA. The reason given is cost per layer rather than any technical problem.",
            "Memory customers appear more willing to move early, which partly offsets the foundry "
            "delay. We see this as a timing shift within the High-NA ramp rather than a change "
            "to its eventual size.",
        ]),
        ("Why we stay Buy", [
            "Low-NA EUV demand remains strong and the installed base keeps growing, which supports "
            "servicing revenue regardless of High-NA timing. The investment case does not depend "
            "on any single year of High-NA shipments.",
        ]),
    ],
    # ---------------------------------------------------------------- TSMC
    "tsm-2026-01-16": [
        ("Growth drivers", [
            "AI accelerators are the main driver of this year's growth, through both leading-edge "
            "wafers and advanced packaging. Smartphone and PC demand is stable but no longer the "
            "swing factor in the outlook.",
            "Pricing is a second lever. TSMC has raised prices on its most advanced nodes, and "
            "customers have accepted the increases because there is no credible alternative at "
            "comparable yields.",
        ]),
        ("Capacity plans", [
            "Capital spending stays elevated to keep pace with AI demand, with a growing share "
            "going to advanced packaging and overseas fabs. We think the overseas expansion dilutes "
            "margins slightly but reduces geopolitical risk for customers.",
        ]),
    ],
    "tsm-2026-04-17": [
        ("Margin drivers", [
            "Gross margin strength came from higher utilisation on leading-edge nodes and favourable "
            "pricing. Currency also helped, though we do not treat that as repeatable.",
            "The dilution from overseas fabs was smaller than feared, as early yields at the new "
            "sites have improved faster than the company guided.",
        ]),
        ("Next-node ramp", [
            "The next-generation node remains on schedule for a second-half ramp, with the first "
            "customers in smartphones followed by AI accelerators. Early design wins look broader "
            "than they were for the previous node at the same stage.",
        ]),
    ],
    "tsm-2026-07-17": [
        ("Advanced packaging", [
            "Advanced packaging has become a bottleneck for AI accelerator supply, so capacity "
            "additions here matter as much as wafer capacity. TSMC is adding capacity faster than "
            "we expected and is partnering with outside assembly firms for overflow work.",
            "We expect packaging to remain tight into next year, which supports pricing and gives "
            "TSMC unusual visibility on demand from its largest AI customers.",
        ]),
        ("Estimate changes", [
            "We raise our revenue forecasts for next year and nudge up our long-term margin "
            "assumptions, which drives the higher price target.",
        ]),
    ],
    # ---------------------------------------------------------------- NVIDIA
    "nvda-2026-02-26": [
        ("Demand picture", [
            "Hyperscaler demand remains the core of data center revenue, but sovereign AI projects "
            "and large enterprises are becoming a meaningful second leg. That diversification "
            "makes the revenue base less exposed to any one customer's capex cycle.",
            "Networking is growing faster than compute, as customers buy complete rack-scale "
            "systems rather than individual accelerators.",
        ]),
        ("Product cadence", [
            "The annual product cadence is intact. The next platform is on track, and early "
            "customer engagement suggests the transition will be smoother than the last one, "
            "which was held back by rack-level integration issues.",
        ]),
    ],
    "nvda-2026-05-28": [
        ("Margins and mix", [
            "Gross margin held at a very high level despite the ramp of complex rack-scale systems, "
            "which carry more third-party content. Pricing power remains strong because supply "
            "is still the binding constraint for most customers.",
            "Operating expenses are rising quickly as the company invests in software and "
            "networking, but revenue growth continues to outpace cost growth.",
        ]),
        ("China", [
            "Management now excludes China from guidance entirely. We see that as a sensible "
            "simplification: any approved shipments become upside rather than a source of "
            "uncertainty in the forecast.",
        ]),
    ],
    "nvda-2026-08-27": [
        ("New platform ramp", [
            "First shipments of the new platform have begun, and management described the ramp as "
            "faster than the previous generation's. Customers are taking full racks, which raises "
            "the revenue content per deployment.",
            "Supply of advanced packaging and high-bandwidth memory remains the gating factor, "
            "not end demand.",
        ]),
        ("Capex outlook", [
            "Hyperscaler commentary on next year's capital spending has strengthened through the "
            "summer. We think the debate has shifted from whether AI spending peaks next year to "
            "how quickly it broadens beyond the largest buyers.",
        ]),
    ],
    # ---------------------------------------------------------------- AMD
    "amd-2026-02-04": [
        ("The accelerator question", [
            "AMD's data center GPU roadmap is credible on paper, but timing of its next-generation "
            "accelerator is the key uncertainty. Customers want confidence in rack-scale "
            "availability, not just chip specifications.",
            "Software maturity is improving. Several large customers now run production inference "
            "workloads on AMD hardware, which was not the case a year ago.",
        ]),
        ("CPU franchise", [
            "The server CPU business continues to take share, providing a stable earnings base "
            "while the accelerator story develops.",
        ]),
    ],
    "amd-2026-05-06": [
        ("Customer traction", [
            "The large AI lab deployment starting in the second half is an important validation, "
            "because it involves rack-scale systems rather than evaluation clusters. We will watch "
            "for follow-on orders from other hyperscalers.",
            "Gaming and embedded remain soft, which masks some of the data center progress in the "
            "group totals.",
        ]),
        ("Why we stay Hold", [
            "We want evidence that rack-scale shipments are on schedule before upgrading. The "
            "valuation already discounts a good part of the accelerator opportunity.",
        ]),
    ],
    "amd-2026-08-05": [
        ("What changed", [
            "Rack-scale shipments have started on time, removing the main execution risk we "
            "flagged earlier in the year. Customer feedback on performance and software has been "
            "better than we expected.",
            "The order pipeline now includes several hyperscalers as well as the large AI lab, "
            "which gives us more confidence in next year's data center revenue.",
        ]),
        ("Estimate changes", [
            "We raise our data center GPU forecasts for next year and beyond, which drives the "
            "upgrade and the higher price target.",
        ]),
    ],
    # ---------------------------------------------------------------- Microsoft
    "msft-2026-01-29": [
        ("Azure", [
            "Azure growth remains capacity-constrained, meaning revenue would have been higher "
            "with more data center space and power available. That supports continued heavy "
            "capital spending.",
            "AI services are a growing share of Azure consumption, but traditional cloud migration "
            "also continues at a healthy pace.",
        ]),
        ("Capital intensity", [
            "The capex run-rate is high, and investors worry about depreciation pressure on "
            "margins. We think pricing and utilisation will keep returns attractive.",
        ]),
    ],
    "msft-2026-04-30": [
        ("Copilot adoption", [
            "Copilot seat growth is accelerating as enterprises move from pilots to broader "
            "deployments. Usage data shared by management suggests seats are being used, not "
            "just bought.",
            "The pricing model is evolving, with more consumption-based options alongside "
            "per-seat licences.",
        ]),
        ("Cloud", [
            "Azure growth was steady, with AI services again contributing a larger share. "
            "Capacity constraints are easing gradually as new data centers come online.",
        ]),
    ],
    "msft-2026-07-30": [
        ("Capex and margins", [
            "Management signalled that capex growth will slow next fiscal year, though from a "
            "very high base. Investors welcomed the message because it eases concerns about "
            "depreciation overwhelming margins.",
            "Operating margins held up well, helped by cost discipline outside AI investments.",
        ]),
        ("Our view", [
            "We remain Buy. Microsoft combines visible AI monetisation in both cloud and "
            "productivity software with a balance sheet that can fund the build-out comfortably.",
        ]),
    ],
    # ---------------------------------------------------------------- SAP
    "sap-2026-01-30": [
        ("Cloud transition", [
            "The migration of the on-premise base to cloud subscriptions continues to drive "
            "backlog growth. Large customers are committing to multi-year contracts, which gives "
            "good revenue visibility.",
            "Operating margin expansion is coming from lower restructuring costs and the shift to "
            "higher-margin cloud revenue.",
        ]),
        ("AI products", [
            "SAP's business AI features are an upsell opportunity within existing cloud contracts. "
            "Early uptake is encouraging but still a small contributor.",
        ]),
    ],
    "sap-2026-04-23": [
        ("Deal timing", [
            "Several public sector deals in the US slipped out of the quarter, which management "
            "attributed to procurement delays rather than lost business. We accept that "
            "explanation but think it signals a longer sales cycle.",
            "Private sector demand in Europe remained solid, so the weakness is concentrated "
            "rather than broad-based.",
        ]),
        ("Valuation premium", [
            "SAP trades at a premium to software peers that assumed backlog growth would stay "
            "elevated. With that assumption under pressure, we see limited upside from here.",
        ]),
    ],
    "sap-2026-07-22": [
        ("Data platform", [
            "Business Data Cloud is gaining traction as customers consolidate their SAP data for "
            "analytics and AI use cases. It deepens SAP's position in customers' data strategies.",
            "Backlog growth stabilised but has not re-accelerated, which keeps us at Hold.",
        ]),
        ("What would make us more positive", [
            "We would want evidence that backlog growth is re-accelerating, ideally driven by "
            "upsell of AI features into the existing cloud base.",
        ]),
    ],
    # ---------------------------------------------------------------- JPMorgan
    "jpm-2026-01-14": [
        ("Franchise strength", [
            "JPMorgan continues to lead its peers on returns, deposit franchise and technology "
            "investment. We do not doubt the quality of the business.",
            "Our concern is valuation. The shares already price in sustained outperformance, "
            "leaving little room for upside if the credit cycle turns.",
        ]),
        ("What we are watching", [
            "Credit quality in consumer lending and the pace of capital return are the two "
            "variables most likely to move the shares.",
        ]),
    ],
    "jpm-2026-04-14": [
        ("Investment banking", [
            "Investment banking fees recovered strongly as M&A and equity issuance picked up. "
            "Pipelines remain healthy, though market volatility could delay deal completions.",
            "Markets revenue was solid, with fixed income benefiting from rate volatility.",
        ]),
        ("Consumer credit", [
            "Card charge-offs have risen, but in line with management's guidance and from "
            "historically low levels. We see normalisation rather than deterioration.",
        ]),
    ],
    "jpm-2026-07-15": [
        ("Capital", [
            "JPMorgan holds substantial excess capital above regulatory requirements, which "
            "supports large buybacks. Proposed regulatory changes could release more capital "
            "over time.",
            "Management remains cautious about deploying capital at current valuations, "
            "preferring to hold a buffer for opportunities.",
        ]),
        ("Our view", [
            "We stay at Hold. The business is excellent, but the valuation leaves limited upside "
            "relative to European banks with similar return trajectories.",
        ]),
    ],
    # ---------------------------------------------------------------- HSBC
    "hsba-2026-02-25": [
        ("Strategy", [
            "HSBC's simplification strategy is delivering cost savings and a sharper focus on its "
            "core Asian and wealth businesses. Exits from smaller markets are largely complete.",
            "Wealth management in Asia is a key growth driver, benefiting from rising affluence "
            "and the bank's strong Hong Kong franchise.",
        ]),
        ("Capital return", [
            "Capital return remains generous, combining dividends with buybacks. We see "
            "dependable distributions as a core part of the investment case.",
        ]),
    ],
    "hsba-2026-05-05": [
        ("Hong Kong property", [
            "Provisions against Hong Kong commercial real estate rose, but remain manageable "
            "relative to earnings and capital. The exposure is concentrated in a small number "
            "of borrowers.",
            "We think the market has already priced in further provisions, so additional charges "
            "would not change our view.",
        ]),
        ("Earnings", [
            "Net interest income held up better than expected, supported by deposit growth and "
            "structural hedges.",
        ]),
    ],
    "hsba-2026-07-30": [
        ("Net interest income", [
            "The higher NII guide reflects stronger deposit balances and a slower pass-through of "
            "rate cuts than the bank assumed. Structural hedges also lock in income for longer.",
            "Fee income from wealth management continued to grow, diversifying revenue away from "
            "rate-sensitive income.",
        ]),
        ("Our view", [
            "We remain Buy. HSBC offers an attractive combination of earnings momentum, capital "
            "return and a valuation discount to peers.",
        ]),
    ],
    # ---------------------------------------------------------------- Novo Nordisk
    "novo-2026-02-05": [
        ("Oral Wegovy", [
            "The oral formulation broadens the addressable market to patients reluctant to use "
            "injections. Early prescription trends are encouraging, and manufacturing capacity "
            "appears sufficient.",
            "Pricing for the oral version is positioned to encourage uptake rather than maximise "
            "price per patient.",
        ]),
        ("Competition", [
            "Competition in obesity remains intense, but we think the market is large enough "
            "for two leading players to grow strongly for several years.",
        ]),
    ],
    "novo-2026-03-19": [
        ("US pricing", [
            "The new pricing agreement in the US cuts net prices more deeply than we had modelled. "
            "Volume growth will offset part of the impact, but not all of it.",
            "Compounded versions of semaglutide continue to take share at the lower end of the "
            "market despite regulatory efforts to curb them.",
        ]),
        ("Pipeline", [
            "CagriSema's latest data were good in absolute terms but did not clearly beat the "
            "leading competitor, which weakens the case for a pipeline-driven re-rating.",
        ]),
    ],
    "novo-2026-06-18": [
        ("Launch progress", [
            "Weekly prescriptions for oral Wegovy continue to climb, and the launch is tracking "
            "ahead of our expectations. Physicians report good tolerability.",
            "Outside the US, patent expiries in several markets will bring generic competition, "
            "adding pressure to international sales.",
        ]),
        ("Our view", [
            "We stay at Hold. The launch is a positive, but pricing pressure in both the US and "
            "international markets limits earnings upgrades.",
        ]),
    ],
    "novo-2026-09-10": [
        ("Pipeline", [
            "The start of late-stage trials for amycretin is an important pipeline milestone. "
            "Early-stage data suggested strong weight loss, but late-stage results are still "
            "some way off.",
            "Management narrowed full-year guidance, reducing uncertainty without changing the "
            "overall outlook.",
        ]),
        ("Our view", [
            "We remain at Hold. Pipeline progress is encouraging, but near-term earnings remain "
            "constrained by pricing.",
        ]),
    ],
    # ---------------------------------------------------------------- AstraZeneca
    "azn-2026-02-10": [
        ("Pipeline breadth", [
            "AstraZeneca's long-term ambition rests on a broad pipeline across oncology, "
            "cardiovascular and rare diseases. No single launch carries the target.",
            "Oncology remains the largest contributor, with antibody-drug conjugates an "
            "increasingly important platform.",
        ]),
        ("Our view", [
            "We remain Buy. Pipeline delivery has been consistent, and we think the market still "
            "underestimates the breadth of late-stage assets.",
        ]),
    ],
    "azn-2026-04-29": [
        ("Regulatory progress", [
            "The baxdrostat filing is an important step for the cardiovascular franchise, "
            "targeting patients with hard-to-control hypertension.",
            "Enhertu continues to grow strongly as it moves into earlier lines of breast cancer "
            "treatment.",
        ]),
        ("Our view", [
            "We remain Buy, with several catalysts ahead in the second half of the year.",
        ]),
    ],
    "azn-2026-07-29": [
        ("Corporate developments", [
            "The direct listing in New York broadens the investor base and may narrow the "
            "valuation gap with US peers over time.",
            "Camizestrant's approval adds a new oral option in breast cancer and strengthens the "
            "oncology franchise.",
        ]),
    ],
    # ---------------------------------------------------------------- Shell
    "shel-2026-02-05": [
        ("Integrated gas", [
            "LNG is Shell's main growth engine, supported by long-term contracts and new "
            "liquefaction capacity. We see integrated gas as the most valuable part of the "
            "portfolio.",
            "Upstream oil production is managed for value rather than volume, with disciplined "
            "capital allocation.",
        ]),
        ("Capital return", [
            "Buybacks remain a core part of the investment case, backed by strong free cash flow "
            "and a balance sheet that has improved steadily.",
        ]),
    ],
    "shel-2026-05-07": [
        ("Lower oil price deck", [
            "We cut our oil price assumptions to reflect a softer market. Shell's buyback is "
            "trimmed in our model, but remains generous by sector standards.",
            "Management has signalled flexibility to adjust buybacks with commodity prices rather "
            "than add debt to sustain them.",
        ]),
        ("Our view", [
            "We remain Buy, since Shell's cost discipline and LNG growth make it more resilient "
            "than peers in a lower price environment.",
        ]),
    ],
    "shel-2026-07-31": [
        ("Quarter detail", [
            "Integrated gas carried the quarter, with strong LNG trading results offsetting "
            "weaker refining margins. The diversity of the portfolio helped earnings stability.",
            "Net debt was stable, and the balance sheet remains in good shape to absorb "
            "commodity volatility.",
        ]),
        ("Our view", [
            "We stay Buy, given dependable cash returns and a portfolio weighted towards gas.",
        ]),
    ],
    # ---------------------------------------------------------------- BP
    "bp-2026-02-11": [
        ("Balance sheet", [
            "BP's gearing is too high for the strategy reset to work without asset sales. Until "
            "debt falls, we expect cash returns to come under pressure.",
            "The renewed focus on oil and gas improves near-term cash flow, but the benefits will "
            "take time to show.",
        ]),
        ("Our view", [
            "We stay at Sell. We prefer peers with stronger balance sheets and more predictable "
            "capital returns.",
        ]),
    ],
    "bp-2026-05-06": [
        ("Capital return", [
            "The cut to the buyback confirms our concern that capital return is not sustainable "
            "at the current level of debt.",
            "Asset sales are progressing, but the proceeds are needed to reduce debt rather than "
            "fund distributions.",
        ]),
        ("Our view", [
            "We remain at Sell until gearing shows a clear and sustained improvement.",
        ]),
    ],
    "bp-2026-08-05": [
        ("Castrol sale", [
            "Completing the Castrol sale is an important milestone for deleveraging, bringing "
            "gearing towards management's target range.",
            "With balance sheet risk reduced, the downside case we flagged earlier in the year "
            "is less likely.",
        ]),
    ],
    # ---------------------------------------------------------------- LVMH
    "mc-2026-01-28": [
        ("China", [
            "Chinese consumer demand for luxury goods remains weak, both at home and through "
            "travel spending abroad. Fashion and leather goods, LVMH's largest division, is "
            "most exposed.",
            "Other divisions, such as perfumes and cosmetics, are holding up better but cannot "
            "offset the weakness in fashion and leather goods.",
        ]),
        ("Our view", [
            "We stay at Hold until there are signs of stabilisation in Chinese demand.",
        ]),
    ],
    "mc-2026-04-15": [
        ("Tariffs", [
            "US tariffs on European goods have added pressure, with LVMH absorbing part of the "
            "cost rather than passing it fully to customers.",
            "Organic sales declined in the quarter, reflecting both tariffs and continued "
            "weakness in China.",
        ]),
        ("Our view", [
            "We remain at Hold. The brand portfolio is strong, but near-term trends remain "
            "challenging.",
        ]),
    ],
    "mc-2026-07-24": [
        ("Fashion and leather turns", [
            "Fashion and leather goods returned to positive growth, led by the largest brands. "
            "Early signs of recovery in Chinese demand contributed.",
            "Pricing discipline has protected margins through the downturn, positioning LVMH "
            "well for the recovery.",
        ]),
        ("Why upgrade now", [
            "We upgrade to Buy because the turn in fashion and leather goods marks the start of "
            "an earnings recovery that the market has not yet priced in.",
        ]),
    ],
    # ---------------------------------------------------------------- sector and strategy
    "sector-semis-2026-03-05": [
        ("Equipment demand", [
            "Semiconductor equipment demand is split. EUV tools for leading-edge logic and memory "
            "are in high demand, while mature-node tools face normalising China orders.",
            "Memory capex is recovering, which supports both lithography and deposition "
            "equipment suppliers.",
        ]),
        ("Our preferences", [
            "We prefer companies exposed to leading-edge technology transitions over those "
            "dependent on mature-node China demand.",
        ]),
    ],
    "sector-semis-2026-09-15": [
        ("AI capex durability", [
            "Our check of hyperscaler commentary suggests AI capital spending will keep growing "
            "next year, though at a slower pace than this year.",
            "Spending is broadening from the largest cloud providers to sovereign projects and "
            "enterprises, which supports durability.",
        ]),
        ("Our preferences", [
            "We favour suppliers with exposure to both compute and networking, since networking "
            "spend is growing faster as clusters scale.",
        ]),
    ],
    "sector-banks-2026-03-12": [
        ("Rates and earnings", [
            "Falling rates will pressure net interest income, but structural hedges and deposit "
            "repricing should cushion the impact for most European banks.",
            "Fee income from wealth and asset management is becoming more important as rate "
            "tailwinds fade.",
        ]),
        ("Capital return", [
            "Most banks hold excess capital, supporting continued buybacks and dividends. We "
            "favour banks that combine generous distributions with resilient earnings.",
        ]),
    ],
    "sector-pharma-2026-05-20": [
        ("Price erosion", [
            "Obesity drug prices are falling as competition intensifies and payers push back. "
            "Volume growth should offset much of the price decline over time.",
            "Oral formulations and next-generation drugs could support pricing by offering "
            "differentiated benefits.",
        ]),
        ("Scenarios", [
            "Our scenarios range from moderate price erosion with strong volume growth to "
            "steeper price cuts that compress margins for the leading players.",
        ]),
    ],
    "sector-energy-2026-06-10": [
        ("Buyback sustainability", [
            "At lower oil prices, majors with strong balance sheets can sustain buybacks, while "
            "those with high debt may need to cut.",
            "Integrated gas and trading businesses provide resilience when oil prices are weak.",
        ]),
        ("Our preferences", [
            "We favour majors with low gearing and significant LNG exposure.",
        ]),
    ],
    "sector-software-2026-06-24": [
        ("Seat-based pricing", [
            "AI tools threaten seat-based pricing models, since fewer human users may be needed "
            "for the same work. Software vendors are experimenting with consumption-based pricing.",
            "Vendors with strong data platforms are better positioned to capture AI value "
            "through new products.",
        ]),
        ("Our preferences", [
            "We prefer companies that can monetise AI through consumption models rather than "
            "relying on seat growth.",
        ]),
    ],
    "sector-luxury-2026-09-03": [
        ("China recovery", [
            "Early signals point to a recovery in Chinese luxury demand, led by younger "
            "consumers and domestic travel.",
            "The recovery is uneven across brands, with the strongest brands benefiting first.",
        ]),
        ("Our preferences", [
            "We favour brands with pricing power and strong exposure to Chinese consumers.",
        ]),
    ],
    "strategy-2026-01-07": [
        ("Themes", [
            "Our top picks for the year reflect three themes: AI infrastructure, capital return "
            "in financials, and resilient pharmaceutical pipelines.",
            "We favour companies with visible earnings growth and strong balance sheets, given "
            "uncertainty about the macro outlook.",
        ]),
    ],
    "strategy-2026-07-08": [
        ("Changes", [
            "The changes to our top picks reflect shifts in the investment case for individual "
            "companies rather than a change in our broad themes.",
            "AI infrastructure remains our largest theme, and we continue to favour financials "
            "with strong capital return.",
        ]),
    ],
}
