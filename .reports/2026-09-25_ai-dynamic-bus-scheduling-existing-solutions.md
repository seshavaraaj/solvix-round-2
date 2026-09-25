# Existing Solutions for AI-Based Dynamic Public Bus Scheduling

| Field | Value |
|---|---|
| Prepared | 2026-09-25 |
| Topic | Prior and existing solutions for AI-based dynamic bus scheduling and vehicle deployment |
| Domain | Public transport operations, intelligent transportation systems, applied AI/optimization |
| Constraints | None specified by user; defaults applied (see Assumptions and Scope) |
| Audience | Hackathon team deciding what to build and how to differentiate from existing solutions |
| File | 2026-09-25_ai-dynamic-bus-scheduling-existing-solutions.md |

## Executive Summary

The problem statement asks for a system that uses historical and real-time data to detect overcrowded routes, underused services, and emerging delays, and then recommends changes to bus frequency and deployment [1]. Many solutions already cover parts of this problem. Academic work offers strong methods for real-time headway control, reinforcement-learning timetables, and ridership forecasting, but most results come from simulations of one or a few routes [3][4][5][9][10]. Commercial platforms (Optibus, Swiftly, GIRO HASTUS, Trapeze, Via) are mature in offline scheduling, live monitoring, and on-demand routing, and they are adding AI assistants, but public material shows that network-wide, real-time frequency and fleet reallocation is still mostly a human dispatcher decision [13][14][15][16]. In India, Delhi and Bengaluru have real-time GPS and ticketing data and have announced AI programmes, but occupancy data is sparse and tracking gaps remain [22][23][24][25][26]. The clearest opening for a new solution is an explainable, network-level decision-support layer that joins demand forecasting, anomaly detection, and fleet reallocation, built on data Indian agencies already collect.

## Assumptions and Scope

Defaults applied (user replied "default"):

- Audience: hackathon team choosing what to build and how to stand out.
- Depth: standard report.
- Questions answered: what exists (academic, commercial, open-source, city deployments), which methods are used, where they fall short, and where a new solution can add value.
- Timeframe: most recent information available as of 2026-09-25; older landmark papers included where still relevant.
- Geography: global, with a dedicated India section.
- Sources: primary and authoritative sources preferred (peer-reviewed papers, arXiv preprints, agency and vendor pages, established news outlets).
- Special sections: comparison table, gap analysis, recommendations, and risks.

Out of scope: rail and metro scheduling (except where methods transfer), driver rostering and payroll in depth, fare policy, and pricing of commercial products (not publicly available).

## Methodology

- Web searches on academic, commercial, open-source, and government sources, run on 2026-09-25.
- Full pages or PDFs were read for most specific claims and numbers. Some pages blocked automated access (HTTP 403). For those, only search-result summaries were available. These sources are marked "(summary only)" in the Sources list, and claims based on them are given lower confidence.
- Vendor and agency performance figures are self-reported. They were not independently verified.
- The local file `problem-statement.md` was used as the reference definition of the problem [1].
- Limitations: search was in English only and is US-indexed. Chinese-language literature, which is large on this topic, is under-represented. Proprietary vendor algorithms are not publicly documented.

## Findings

### 1. The problem splits into planning, forecasting, and real-time control layers

A widely cited review of bus systems separates the field into planning and network design, and operation and control [2]. The problem statement touches all layers [1]:

| Layer | Time horizon | Typical question | Relevant to problem statement |
|---|---|---|---|
| Strategic/tactical planning | Months to weeks | Which routes, what frequency per time band, how many buses | "Underutilized services", "improve utilization" |
| Demand and crowding forecasting | Days to minutes | How many passengers will board where and when | "Analyze historical and real-time data", "overcrowded routes" |
| Real-time operations control | Minutes to seconds | Hold, skip stops, short-turn, dispatch extra bus | "Emerging delays", "dynamically recommend adjustments" |

Standard real-time control actions in the literature are vehicle holding, stop-skipping, speed control, short-turning, and boarding limits [12]. Most existing solutions specialise in one layer. Few join all three.

### 2. Academic solutions

#### 2.1 Classical headway and schedule control

Bus lines are naturally unstable: without control, buses bunch [3]. Xuan, Argote, and Daganzo (2011) proposed dynamic holding against a "virtual schedule". The method needs only the arrival times of the current and preceding bus at a control point. It required about 40% less slack than conventional schedule-based holding, and it outperformed headway-only methods for headway regulation [3]. This class of method is simple, needs little data, and is the practical baseline that later AI methods compare against.

#### 2.2 Reinforcement learning for dispatch timetables

Ai, Zuo, Chen, and Wu (2021) proposed DRL-TO, a Deep Q-Network that decides each minute whether to dispatch a bus from the terminal [4]. State features include load factor, capacity utilisation, and stranded passengers. The reward combines full-load rate, empty-load rate, waiting time, and stranded passengers. Against a memetic algorithm, a genetic algorithm, and manual timetables, it used 8% fewer vehicles and cut passenger waiting time by 17% [4]. The authors note that conventional timetables are set offline per time band and cannot follow sudden demand changes [4]. This is the closest academic match to "dynamic frequency adjustment", but it is per line, not network-wide.

#### 2.3 Multi-agent reinforcement learning for bunching control

- Wang and Sun (2020) framed holding control as a multi-agent deep RL problem, with each bus as an agent [5].
- Wang and Sun (2021) added asynchronous multi-agent RL with a graph-attention critic, trained on real smart-card demand. It outperformed headway-based control and earlier multi-agent RL methods [6].
- He et al. (2020) combined approximate dynamic programming, Q-learning, and multi-stage look-ahead. In simulation, it removed bunching and cut waiting time compared with terminal holding [7].

#### 2.4 LLM-enhanced reinforcement learning (2024–2026)

- Yu, Wang, and Ma (2024) used an LLM to write and iteratively refine RL reward functions for bus holding. It outperformed vanilla RL, pure LLM controllers, and physics- and optimisation-based controllers across different lines and demand patterns [8].
- Dong and Gayah (2026) used an LLM offline to create "semantic embeddings" of bus stops (location, activity context, history) as inputs to a deep Q-learning controller. In simulations calibrated on two real routes, it reduced headway variability by 32%, bunching events by 69.2%, and waiting time by 24% compared with a baseline. Zero-shot transfer to a new route was weak; fine-tuning or retraining was needed [9].

#### 2.5 Ridership and overcrowding forecasting

- Vanderbilt University and WeGo Public Transit (Nashville) built a graph convolutional network for stop-level, day-ahead ridership. The authors state that overcrowding events are rare and data is noisy and sparse. They used focal loss to focus on these rare, important overcrowding cases, and they report better accuracy and robustness than earlier baselines on real agency data [10].
- LSTM and XGBoost models on smart-card data are common in Chinese studies of hourly bus flows (summary-level evidence only; not reviewed in depth).

#### 2.6 Predict-then-optimise network redesign

Guo et al. (2026) forecast traffic with a diffusion convolutional recurrent network, then redesigned lines with NSGA-III while keeping more than 85% line overlap. On the Beijing network under high traffic variability, average travel time improved by 25.8% [11]. This shows a two-stage pattern (forecast, then optimise) that fits the problem statement well.

### 3. Commercial platforms

| Product | Main strength | Real-time features | AI/automation (public claims) | Gaps versus problem statement |
|---|---|---|---|---|
| Optibus | Planning, scheduling, rostering (cloud SaaS) | Control module (June 2025): vehicle tracking, disruption management, crew reassignment [13] | Optibus Agent (June 2026): AI agent for planning, dispatch, monitoring; evaluates routes and timetables against demand [14] | No public evidence of automatic real-time frequency reallocation across routes |
| Swiftly | Real-time data platform, arrival predictions | Bunching/gapping alerts, crowding view from APC or GTFS-RT occupancy [15][16] | Prediction algorithms; claims 40% better on-time performance [15] | Surfaces problems; dispatchers decide the action |
| GIRO HASTUS | Computer-aided scheduling for large agencies | Scheduling and dispatch modules [17] | Optimisation-based scheduling | Offline focus; complex; costly (summary only) |
| Trapeze | Scheduling, CAD/AVL, fleet management | Singapore Common Fleet Management System (procured 2014) [18] | Schedule adherence advisories to drivers | Legacy CAD/AVL; not demand-adaptive (summary only) |
| Via | On-demand microtransit | Dynamic routing and dispatch; FTA evaluation of Arlington, Texas: 28,140 rides, 99–100% on-time [19] | Demand prediction and pooling algorithms | Targets low-density on-demand service, not fixed-route frequency |
| Google Maps | Rider-side crowding prediction | Crowdedness predictions from rider reports and location history [20] | Machine learning on crowdsourced data | Informs riders; gives no operator recommendations |

Conflict noted: the Optibus Agent announcement cites deployments in "more than 7,000 cities" [14], while Optibus's own "about" page, in a search summary, cites over 450 cities. The first figure may count all cities in customer networks. Both are vendor claims.

### 4. Open-source and open data

- TheTransitClock (open source, Java) takes GTFS-realtime vehicle positions and produces arrival predictions as GTFS-realtime trip updates. It uses an adaptive Kalman filter to detect unusual conditions. Metro Transit (Twin Cities) chose it in 2020 after a one-month evaluation across 1,400 buses [21].
- GTFS and GTFS-realtime are the common data formats across vendors and open data portals [21][22].
- Open-source tooling covers prediction and data exchange well. Open-source tooling for demand-driven frequency and fleet reallocation is scarce (no mature project found in this search).

### 5. City deployments

#### 5.1 International

- Seoul (TOPIS BMS/BIS): collects and analyses real-time bus location data to manage operations, evaluate operators, optimise routes, and publish congestion information [23].
- Singapore (LTA): Trapeze Common Fleet Management System unifies operators' systems for operations control, fleet management, and passenger information [18].

#### 5.2 India

- Delhi Open Transit Data (OTD): launched in 2018 by the Delhi government with IIIT-Delhi. It publishes static GTFS and real-time bus GPS positions every 10 seconds. More than 50 organisations, including Google Maps, use the real-time feed (summary only) [22].
- Delhi Transport Corporation AI Bus Management System (tender stage, September 2026): the planned system covers real-time monitoring, delay prediction, fleet and depot optimisation to match bus supply to demand, crew scheduling, e-bus charging optimisation, predictive maintenance, and anomaly alerts including bus bunching. DTC runs about 6,269 buses (over 4,500 electric) from 52 depots, with a target of about 14,000 buses by 2028–29 [24][25].
- Bengaluru (BMTC): in a November 2025 interview, the managing director reported 65 adaptive signals with bus priority (18–22% lower signal delay at peak), smart ticketing on 100% of the fleet with 60% digital transactions, and 8–10% higher fleet productivity from AI route optimisation [26]. A 2026 news report describes app tracking glitches, buses off the ITS grid, and unused potential of real-time data for routes and frequency (summary only) [27].
- Chalo (private operator platform): live bus tracking and a live passenger indicator in many Indian cities. Operators see passenger counts, stage-wise boarding and alighting, and live camera feeds (summary only) [28].

## Analysis

**Where existing solutions are strong.** Headway control, arrival prediction, crowding display, and offline scheduling are mature. Academic methods show double-digit gains in waiting time and bunching [3][4][9]. Commercial platforms have large deployments and are moving to AI agents [14][15].

**Where the gap is.** The problem statement's core loop is: detect crowding, underuse, and delay; then recommend moving capacity [1]. Evidence shows this loop is split:

1. Detection tools (Swiftly, Chalo, Google) show the problem but leave the decision to people [15][16][20][28].
2. Academic optimisers make decisions, but mostly for one line, in simulation, and with poor transfer to new routes [4][9].
3. Scheduling suites optimise offline plans, and the new real-time modules focus on monitoring and crew disruption [13][14].
4. Network-wide real-time reallocation of spare buses between routes, under depot and fleet limits, appears rarely in published work or product material found in this search.

**India-specific conditions.** Indian cities have GPS feeds and electronic ticketing data at scale [22][26] but limited automatic passenger counters. Ticket data records boardings but often not alightings, so on-board load must be estimated. Mixed traffic, few dedicated bus lanes, and GPS gaps [27] make delay prediction harder than in the settings of most academic studies. Delhi's own tender signals demand for exactly this type of system [24][25].

**Trade-offs.** Reinforcement learning adapts well but needs a simulator and is hard to explain to dispatchers. Rule-based and optimisation methods are transparent and data-light but less adaptive. A hybrid (forecast + optimisation + simple control rules, with an explanation layer) matches current practice and published results best.

## Risks and Uncertainties

| Finding | Confidence | Reason |
|---|---|---|
| 1. Layered structure of the problem | High | Standard review literature [2][12] |
| 2. Academic methods and reported gains | Medium | Peer-reviewed or preprint results, mostly simulation; gains vary with baseline and setup |
| 3. Commercial capability gaps | Medium | Based on public material only; vendors may have undocumented features |
| 4. Open-source landscape | Medium | Search not exhaustive; smaller projects may exist |
| 5.1 International deployments | Medium | Agency pages are brief; some sources summary only |
| 5.2 India deployments | Medium–Low | Recent news and interviews; figures self-reported; some sources summary only |

Other uncertainties:

- Vendor and agency performance numbers are self-reported and not audited.
- Chinese-language research is under-represented, so some network-level solutions may have been missed.
- The DTC system is at tender stage. Final scope may change.

## Recommendations

For a hackathon team targeting this problem:

1. **Position the product as network-level decision support, not another tracker or single-line controller.** The gap is joining detection with fleet reallocation across routes (Findings 3, Analysis).
2. **Use a predict-then-optimise pipeline.** Forecast stop- or route-level demand (gradient boosting or a graph model with class-imbalance handling for rare overcrowding events), then solve a fleet reallocation problem with fleet size, depot, and minimum-frequency constraints (Findings 2.5, 2.6).
3. **Add simple real-time control as a baseline.** Implement virtual-schedule or headway holding before any RL. Show RL only as an improvement over this baseline (Findings 2.1–2.3).
4. **Build on Indian data formats.** Use Delhi OTD GTFS and GTFS-realtime feeds for real routes and live positions. Estimate loads from ticket-machine boardings when counters are missing (Findings 5.2).
5. **Make recommendations explainable and human-approved.** Show each suggestion with its reason, expected effect on waiting time and load, and a one-click approve or reject. An LLM can write the plain-language explanation, while the optimiser makes the decision (Findings 2.4, Analysis).
6. **Prove results with a simulation.** Report waiting time, load factor, bunching events, and bus utilisation against the current fixed timetable, using the same metrics as published work (Findings 2.2, 2.4).
7. **Plan for bad data.** Handle GPS gaps and missing counts explicitly, because Indian deployments report these problems (Findings 5.2).

## Conclusion Summary

Many tools already solve parts of this problem, but none found in public material joins crowding detection, delay prediction, and live reallocation of buses across a whole network in one explainable system.

- Bus scheduling has three layers: long-term planning, demand forecasting, and live control; most existing tools cover only one (see Findings 1).
- Research methods, including AI that learns by trial and error, cut passenger waiting time by about 17–24% and bus bunching sharply, but mostly in simulations of single routes (see Findings 2).
- Commercial products are strong at timetables, live tracking, and crowding display, and are adding AI assistants, but people still decide where extra buses go (see Findings 3).
- Free, open tools exist for arrival prediction and data sharing, but not for moving buses between routes based on demand (see Findings 4).
- Seoul and Singapore run central bus control systems; Delhi publishes live bus data and is buying an AI bus management system; Bengaluru reports gains from AI but still has tracking gaps (see Findings 5).
- Indian cities have plenty of GPS and ticket data but little direct passenger-count data, so bus loads must be estimated (see Analysis).
- Company and agency performance numbers are self-reported and should be treated with care (see Risks and Uncertainties).

Next step: build a decision-support prototype on Delhi's open bus data that forecasts demand, flags problem routes, and recommends moving buses, and prove it in a simulation against today's fixed timetable.

## Sources

1. Project file, "problem-statement.md", undated. Local file: `problem-statement.md` (accessed 2026-09-25)
2. O. J. Ibarra-Rojas, F. Delgado, R. Giesen, J. C. Muñoz, "Planning, operation, and control of bus transport systems: A literature review", Transportation Research Part B 77:38–75, 2015. <https://www.sciencedirect.com/science/article/abs/pii/S0191261515000454> (accessed 2026-09-25) (summary only)
3. Y. Xuan, J. Argote, C. F. Daganzo, "Dynamic bus holding strategies for schedule reliability: Optimal linear control and performance analysis", Transportation Research Part B, 2011. <https://www.ocf.berkeley.edu/~xuanyg/doc/Xuan_Argote_Daganzo_2011_TR-B.pdf> (accessed 2026-09-25)
4. G. Ai, X. Zuo, G. Chen, B. Wu, "Deep Reinforcement Learning based Dynamic Optimization of Bus Timetable", arXiv:2107.07066, 2021. <https://arxiv.org/abs/2107.07066> (accessed 2026-09-25)
5. J. Wang, L. Sun, "Dynamic holding control to avoid bus bunching: A multi-agent deep reinforcement learning framework", Transportation Research Part C 116:102661, 2020. <https://www.sciencedirect.com/science/article/abs/pii/S0968090X20305763> (accessed 2026-09-25) (summary only)
6. J. Wang, L. Sun, "Reducing Bus Bunching with Asynchronous Multi-Agent Reinforcement Learning", arXiv:2105.00376, 2021. <https://arxiv.org/abs/2105.00376> (accessed 2026-09-25)
7. S.-X. He, J.-J. He, S.-D. Liang, J. Q. Dong, P.-C. Yuan, "A Dynamic Holding Approach to Stabilizing a Bus Line Based on the Q-learning Algorithm with Multistage Look-ahead", arXiv:2006.08706, 2020. <https://arxiv.org/abs/2006.08706> (accessed 2026-09-25)
8. J. Yu, Y. Wang, W. Ma, "Large Language Model-Enhanced Reinforcement Learning for Generic Bus Holding Control Strategies", arXiv:2410.10212, 2024-10-14 (revised 2025-04-13). <https://arxiv.org/abs/2410.10212> (accessed 2026-09-25)
9. X. Dong, V. V. Gayah, "Mitigating Bus Bunching with Reinforcement Learning Enhanced by Semantic Stop Embedding", arXiv:2608.10207, 2026-08-10. <https://arxiv.org/abs/2608.10207> (accessed 2026-09-25)
10. S. Gupta, A. Khanna, J. P. Talusan, A. Said, D. Freudberg, A. Mukhopadhyay, A. Dubey (Vanderbilt University, WeGo Public Transit), "A Graph Neural Network Framework for Imbalanced Bus Ridership Forecasting", IEEE SMARTCOMP, 2024. <https://smarttransit.ai/files/samir2024smartcomp.pdf> (accessed 2026-09-25)
11. Z. Guo, A. Araldo, F. Touzout, M. El-Yacoubi, "Predict-then-Optimize Framework for Public Transport Line Redesign under Fluctuating Traffic Conditions", arXiv:2608.11405, 2026-08-11. <https://arxiv.org/abs/2608.11405> (accessed 2026-09-25)
12. K. Gkiotsalitis, O. Cats, T. Liu, "A review of public transport transfer synchronisation at the real-time control phase", Transport Reviews, 2023. <https://www.tandfonline.com/doi/pdf/10.1080/01441647.2022.2035014> (accessed 2026-09-25) (summary only)
13. Optibus, "Optibus Expands End-to-End Platform with Real-Time Control for Public Transportation", 2025-06-12. <https://blog.optibus.com/optibus-expands-end-to-end-platform-with-real-time-control-for-public-transportation> (accessed 2026-09-25)
14. Sustainable Bus, "AI-powered Optibus Agent launched: it targets planning, scheduling and real-time operations", 2026-06-18. <https://www.sustainable-bus.com/its/optibus-agent-launch/> (accessed 2026-09-25)
15. Swiftly, "Public Transit Software for Operations Teams", undated. <https://www.goswift.ly/solution-operations> (accessed 2026-09-25)
16. Swiftly Help Center, "Real-Time Crowding in Live Operations", undated. <https://swiftly.zendesk.com/hc/en-us/articles/360050585251-Real-Time-Crowding-in-Live-Operations> (accessed 2026-09-25)
17. GIRO Inc., "HASTUS – Public Transit Scheduling Software", undated. <https://www.giro.ca/en-us/our-solutions/hastus-software/hastus-for-schedulers/> (accessed 2026-09-25) (summary only)
18. Land Transport Guru, "Trapeze Common Fleet Management System (CFMS)", undated. <https://landtransportguru.net/trapeze-common-fleet-management-system/> (accessed 2026-09-25) (summary only)
19. Via Transportation, "Via Microtransit" and related agency results, undated. <https://ridewithvia.com/solutions/microtransit> (accessed 2026-09-25) (summary only)
20. Google, "Crowdsourced Transit predictions – Transit Partners Help", undated; TechCrunch, "Google Maps can now predict how crowded your bus or train will be", 2019-06-27. <https://support.google.com/transitpartners/answer/9551309?hl=en>, <https://techcrunch.com/2019/06/27/google-maps-can-now-predict-how-crowded-your-bus-or-train-will-be/> (accessed 2026-09-25) (summary only)
21. TheTransitClock project, "TheTransitClock", undated. <https://thetransitclock.github.io/> (accessed 2026-09-25)
22. Dialogue and Development Commission of Delhi, "Open Transit Data Initiative", undated; Open Transit Data Delhi portal. <https://ddc.delhi.gov.in/our-work/6/open-transit-data-initiative>, <https://otd.delhi.gov.in/data/realtime/> (accessed 2026-09-25) (summary only)
23. Seoul TOPIS, "Bus System (BMS & BIS)", undated. <https://topis.seoul.go.kr/openEngBms.do> (accessed 2026-09-25)
24. Millennium Post, "AI system planned to improve DTC bus ops", 2026-09-14. <https://www.millenniumpost.in/delhi/ai-system-planned-to-improve-dtc-bus-ops-675908> (accessed 2026-09-25)
25. EQ Mag, "Delhi Moves Toward AI-Powered Bus Management for Smarter Public Transport", 2026-09-14. <https://www.eqmagpro.com/delhi-moves-toward-ai-powered-bus-management-for-smarter-public-transport-eq/> (accessed 2026-09-25)
26. APAC News Network, "BMTC Focuses on Smarter Operations, Greener Buses and Seamless Connectivity in Bengaluru: Ramachandran R, MD, BMTC", 2025-11-06. <https://apacnewsnetwork.com/2025/11/bmtc-focuses-on-smarter-operations-greener-buses-and-seamless-connectivity-in-bengaluru-ramachandran-r-md-bmtc/> (accessed 2026-09-25)
27. Deccan Herald, "Missing buses, long waits: inside Bengaluru's BMTC app glitches and tracking woes", 2026. <https://www.deccanherald.com/india/karnataka/bengaluru/missing-buses-long-waits-inside-bengalurus-bmtc-app-glitches-and-tracking-woes-3963929> (accessed 2026-09-25) (summary only)
28. Chalo, "Live Bus Tracking, Buy Bus Tickets Online | Chalo App India", undated. <https://chalo.com/> (accessed 2026-09-25) (summary only)
