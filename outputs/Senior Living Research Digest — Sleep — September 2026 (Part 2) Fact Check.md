# Fact-Check Report: Senior Living Research Digest — Sleep — September 2026
**Checked:** 2026-09-15 | **Studies reviewed:** 20
**Primary audience:** older adults and seniors | **Secondary audience:** families, caregivers, and senior living professionals

---

### Study 1: Sleeping Nine Hours or More May Signal Trouble: Large Chinese Study Links Sleep Extremes to Earlier Death
**PMID:** 42648048 | **Verdict:** ⚠️ Minor issues

**Issue A. Null finding framed as reassurance** — Severity: Minor

- **As written:** "This study cannot show that changing your hours changes your risk, but it does suggest long sleep deserves a conversation, and that a routine nap is not something to worry about."
- **Abstract says:** "Daytime napping and sleep disturbance were not significantly associated with mortality."
- **Problem:** A non-significant association in one self-report cohort is absence of evidence, not evidence that napping is safe; other studies in this same digest (#9, #14) link napping to worse cognitive and kidney outcomes, so blanket reassurance goes beyond the data.
- **Suggested fix:** "Reword to: "...and that in this study napping was not associated with higher mortality risk, though that does not settle the question.""

### Study 2: Heart and Metabolic Conditions Make Depression Stickier — And Bad Sleep Makes It Worse
**PMID:** 42628578 | **Verdict:** ⚠️ Minor issues

**Issue A. Interaction described as significant in each country** — Severity: Minor

- **As written:** "Sleeping less than 6 or 9 or more hours amplified these associations, with a statistically significant additive interaction in both countries."
- **Abstract says:** "Significant additive interactions between CMM and unhealthy sleep duration were observed (P for additive interaction <0.001)."
- **Problem:** The abstract reports significant additive interactions without breaking them down by cohort, so "in both countries" cannot be confirmed from the abstract alone.
- **Suggested fix:** "Say "with a statistically significant additive interaction between multimorbidity and unhealthy sleep duration" and drop "in both countries," or mark it as unverified."

### Study 3: One Pill Leads to Another: Dementia Drugs Followed by Sleep Medications in 1 in 10 Older Adults
**PMID:** 42727946 | **Verdict:** ⚠️ Minor issues

**Issue A. Dose-timing advice not studied** — Severity: Minor

- **As written:** "ask your prescriber or pharmacist whether the timing of that dose can be changed before you accept a sleeping pill"
- **Abstract says:** "The study measured population prevalence, cascade incidence and adjusted sequence ratios for 65 expert-nominated prescribing cascades; it did not evaluate dose timing or any management strategy."
- **Problem:** A specific management suggestion (changing dose timing) is presented as flowing from a study that only quantified prescribing sequences.
- **Suggested fix:** "Keep the general prompt ("Is this new symptom a side effect of something I'm already taking?") and attribute dose-timing options to general prescribing guidance rather than this study."

**Issue B. Drug named that the abstract does not name** — Severity: Minor

- **As written:** "especially a dementia drug like donepezil"
- **Abstract says:** "The abstract refers to the drug class "cholinesterase inhibitor" only."
- **Problem:** The specific agent is a reasonable class example but is not verifiable from the abstract.
- **Suggested fix:** "Write "a cholinesterase inhibitor (the class that includes donepezil)" to make clear the example is editorial."

### Study 4: For Older Adults With Advanced Cognitive Impairment, Sleep Hours Were the Strongest Clue to Depression
**PMID:** 42727201 | **Verdict:** ⚠️ Minor issues

**Issue A. Predictor importance recast as diagnostic value** — Severity: Minor

- **As written:** "observable behaviors like how long they sleep may carry more diagnostic weight than the usual mood questions"
- **Abstract says:** "'sleep duration per day' was the top predictor in the severely impaired group; "Further external validation is needed before implementation in routine clinical practice.""
- **Problem:** Feature importance inside an XGBoost risk model is not diagnostic weight, and sleep duration in this survey was itself reported (self or proxy), not objectively observed.
- **Suggested fix:** "Reword to "sleep duration ranked as the most informative variable in the model for this group" and keep the external-validation caveat prominent."

### Study 5: Long daytime naps linked to slower thinking speed in older adults, new sleep study finds
**PMID:** 42596580 | **Verdict:** ✅ Accurate

No factual errors found. Framing is consistent with the abstract.

### Study 6: One in five older New Yorkers surveyed used cannabis in the past year — and half reported using it to sleep
**PMID:** 42712247 | **Verdict:** ⚠️ Minor issues

**Issue A. Side effects listed in wrong order of frequency** — Severity: Minor

- **As written:** "Drowsiness and dry mouth were the most frequently reported side effects"
- **Abstract says:** "Dry mouth (41.4%) and drowsiness (18.6%) were the most reported adverse effects."
- **Problem:** Listing drowsiness first implies it was the most common effect, when dry mouth was reported more than twice as often — and the digest's "why it matters" leans on drowsiness.
- **Suggested fix:** "Write "Dry mouth (41.4%) and drowsiness (18.6%) were the most frequently reported side effects.""

**Issue B. Denominator for past-24-hour use** — Severity: Minor

- **As written:** "Past-year cannabis use was reported by 22.2%, and 11.1% had used within the previous 24 hours"
- **Abstract says:** "22.2% of participants (n = 70) reported past-year cannabis use, and among them, 11.1% (n = 35) reported past 24-h use."
- **Problem:** The abstract attributes the 11.1% to past-year users ("among them"), though the accompanying n = 35 implies 11.1% of the full 315-person sample. The digest silently picks one reading.
- **Suggested fix:** "State "35 participants (11.1% of the full sample as reported) had used in the previous 24 hours" or flag the abstract's ambiguity."

### Study 7: How seniors rate their own sleep sits at the center of their mental health — at least at home
**PMID:** 42711172 | **Verdict:** ✅ Accurate

No factual errors found. Framing is consistent with the abstract.

### Study 8: Vitamin D Levels Track With Longer, Less Broken Sleep in Older Adults
**PMID:** 42696426 | **Verdict:** ⚠️ Minor issues

**Issue A. Unverified novelty claim** — Severity: Minor

- **As written:** "this is some of the first evidence tying it to objectively recorded sleep rather than self-report"
- **Abstract says:** ""Low vitamin D and B12 levels are linked to low self-reported sleep quality... We examined the associations between serum vitamin D and B12 levels with actigraphic sleep indices...""
- **Problem:** The abstract notes prior work used self-report but makes no claim to being first or among the first with actigraphy.
- **Suggested fix:** "Change to "this study used wrist actigraphy rather than questionnaires, unlike much of the earlier work.""

**Issue B. Effect size presented without its unit** — Severity: Minor

- **As written:** "Higher vitamin D was associated with about 24 more minutes of total sleep time per night"
- **Abstract says:** "Higher vitamin D concentration was associated with longer total sleep time (B = 23.63 minutes, 95% CI: 9.62, 37.64)."
- **Problem:** The 23.63-minute figure is a regression coefficient per unit of vitamin D concentration, not a difference between high- and low-vitamin-D people; readers may take it as a group contrast.
- **Suggested fix:** "Say "each increment in vitamin D level was associated with roughly 24 more minutes of sleep" and note the deficiency comparison separately."

### Study 9: Sleeping 10 Hours or More — and Regular Daytime Napping — Flag Lower Cognitive Scores in 89,000 Europeans
**PMID:** 42690762 | **Verdict:** ⚠️ Minor issues

**Issue A. Interviews described as individuals in headline** — Severity: Minor

- **As written:** "Flag Lower Cognitive Scores in 89,000 Europeans"
- **Abstract says:** "88,889 interviews were included (55% females; mean age 68.88)"
- **Problem:** The unit of analysis was pooled interviews across two waves, which can include the same respondent twice; the body text gets this right but the headline converts them to distinct people.
- **Suggested fix:** "Headline: "...in Nearly 89,000 Interviews Across Europe.""

**Issue B. Napping outcome slightly recast** — Severity: Minor

- **As written:** "Among other sleep complaints — recent trouble sleeping, weekly sleep medication use, and daytime napping — only napping survived adjustment."
- **Abstract says:** "Cognitive impairment was significantly associated with subjective reports of recent trouble sleeping, weekly use of medication to aid sleep, and daytime napping, although only the association with daytime napping remained statistically significant after adjusting for potential confounders."
- **Problem:** Accurate in substance, but the napping result concerns cognitive impairment status rather than "lower cognitive scores" as the headline pairs it with long sleep.
- **Suggested fix:** "Specify that ≥10-hour sleep tracked with lower cognitive scores while napping remained associated with cognitive impairment status."

### Study 10: 'Circadian Syndrome' — Poor Sleep Plus Metabolic Problems Plus Low Mood — Linked to Memory Complaints, Especially in Men
**PMID:** 42567211 | **Verdict:** ⚠️ Minor issues

**Issue A. Biomarkers loosely labeled** — Severity: Minor

- **As written:** "circadian syndrome also tracked with blood markers of brain injury and inflammation (GFAP, and nonlinearly with Aβ42/40 and NfL)"
- **Abstract says:** "CircS was dose-responsively linked to GFAP and nonlinearly to Aβ42/40 (Pnonlinear = 0.029) and NfL (Pnonlinear = 0.030)."
- **Problem:** Aβ42/40 is an amyloid ratio, not a marker of brain injury or inflammation, so the umbrella description misdescribes one of the three markers.
- **Suggested fix:** "Write "blood markers used in Alzheimer's research — GFAP (astrocyte activation), NfL (nerve cell damage) and the Aβ42/40 amyloid ratio.""

**Issue B. Sex-specific biomarker direction omitted** — Severity: Minor

- **As written:** "The association with self-reported cognitive domains was stronger in men"
- **Abstract says:** "Subgroup analysis revealed that CircS was associated with higher SCD-domain in males (β = 0.32; P for interaction = 0.003), and lower GFAP levels in females (β = -0.25; P for interaction = 0.021)."
- **Problem:** The digest reports only half of the sex-stratified result; the female-specific finding was in the opposite direction for GFAP, which slightly complicates the 'clustered risk profile' narrative.
- **Suggested fix:** "Add that in women circadian syndrome was associated with lower GFAP levels, underscoring that the sex-stratified results are exploratory."

### Study 11: New Pill for Narcolepsy Restores Daytime Wakefulness in Two Large Trials
**PMID:** 42714024 | **Verdict:** ⚠️ Minor issues

**Issue A. Cataplexy reduction reported without placebo comparator** — Severity: Moderate

- **As written:** "weekly cataplexy attacks dropped 79% to 89%"
- **Abstract says:** "Median percent reductions in the weekly cataplexy rate ranged from 79.0 to 88.8% with oveporexton, as compared with 27.7 to 39.1% with placebo"
- **Problem:** Omitting the 28-39% placebo reduction makes the drug's net benefit on cataplexy look substantially larger than the between-group difference reported.
- **Suggested fix:** "Add the comparator: "weekly cataplexy attacks dropped 79% to 89%, compared with 28% to 39% on placebo.""

**Issue B. Investigational status not disclosed** — Severity: Moderate

- **As written:** "If you live with narcolepsy and have been managing on stimulants for years, this is worth asking your sleep specialist about"
- **Abstract says:** "Oveporexton (TAK-861), an oral orexin receptor 2-selective agonist ... We conducted two phase 3, randomized, placebo-controlled trials ... (Funded by Takeda Development Center Americas; ... ClinicalTrials.gov numbers, NCT06470828 and NCT06505031.)"
- **Problem:** The abstract describes phase 3 trial results for an experimental compound; nothing indicates the drug is available for prescription. Readers could be led to ask for a medication that cannot yet be prescribed.
- **Suggested fix:** "Note that oveporexton is still investigational and not yet approved or available outside trials."

**Issue C. "Normal range" claim unsupported** — Severity: Minor

- **As written:** "with effect sizes large enough to bring many patients back into the normal range"
- **Abstract says:** "Maintenance of Wakefulness Test (MWT; range, 0 to 40 minutes; normal, ≥20) ... Mean changes from baseline to week 12 in mean sleep latency on the MWT ranged from 14.3 to 19.8 minutes"
- **Problem:** The abstract reports change from baseline, not baseline values or the proportion of participants reaching normal thresholds. Unverifiable from abstract only.
- **Suggested fix:** "Drop the "normal range" framing or state simply that mean improvements were large on both the MWT and ESS."

**Issue D. "First drug class" claim** — Severity: Minor

- **As written:** "this is the first drug class to target the underlying orexin deficiency rather than simply stimulating alertness"
- **Abstract says:** "Oveporexton (TAK-861), an oral orexin receptor 2-selective agonist, reduced symptoms of narcolepsy type 1 in a previous phase 2 trial."
- **Problem:** The abstract does not establish first-in-class status. Unverifiable from abstract only.
- **Suggested fix:** "Say the drug targets orexin signalling directly rather than claiming it is the first class to do so."

**Issue E. Hype in headline** — Severity: Minor

- **As written:** "New Pill for Narcolepsy Restores Daytime Wakefulness in Two Large Trials"
- **Abstract says:** "oveporexton significantly improved measures of wakefulness, sleepiness, and cataplexy in participants with narcolepsy type 1"
- **Problem:** "Restores" implies return to normal function; the abstract reports improvement over 12 weeks. The trials (168 and 105 participants) are also modest rather than "large."
- **Suggested fix:** ""Experimental Pill Sharply Improved Daytime Wakefulness in Two Phase 3 Narcolepsy Trials.""

### Study 12: A Pre-Surgery Snapshot Including Sleep and Body Clock Predicts Who Struggles After Cancer Surgery
**PMID:** 42600483 | **Verdict:** ⚠️ Minor issues

**Issue A. Study setting/country omitted** — Severity: Minor

- **As written:** "In a prospective study of 450 adults aged 60 and older undergoing curative gastrointestinal cancer surgery"
- **Abstract says:** "Department of General Surgery, The First Affiliated Hospital of Soochow University, Suzhou, 215006, Jiangsu, China ... 450 adults aged ≥60 years undergoing curative gastrointestinal cancer surgery were enrolled and followed for 3 years."
- **Problem:** The digest flags single-centre limits but never tells readers the cohort was Chinese, which is relevant to generalizability and is stated elsewhere in the digest for other Chinese cohorts.
- **Suggested fix:** "Add "at a single hospital in Suzhou, China" to the study description or caveats."

### Study 13: Expert Panel Issues New Roadmap for Bladder Problems in Parkinson's — Including the Nighttime Trips That Wreck Sleep
**PMID:** 42716874 | **Verdict:** ⚠️ Minor issues

**Issue A. Direction of the symptom–mobility relationship reversed** — Severity: Minor

- **As written:** "urinary urgency, frequency, nocturia, incontinence, and voiding problems compound mobility impairment, disrupt sleep, and contribute to falls"
- **Abstract says:** "These symptoms may be compounded by mobility impairment disrupt sleep and contribute to falls."
- **Problem:** The abstract says urinary symptoms are compounded BY mobility impairment; the digest flips the direction so that urinary symptoms worsen mobility.
- **Suggested fix:** ""...urinary symptoms are compounded by mobility impairment, disrupt sleep, and contribute to falls.""

**Issue B. "Screening" vs "evaluation" domain** — Severity: Minor

- **As written:** "The statements cover screening, disease-specific contributors, diagnostic work-up, and interventions and rehabilitation"
- **Abstract says:** "Draft statements were developed across four clinical domains: evaluation, PD-specific contributors, diagnostic work-up, and interventions and rehabilitation."
- **Problem:** The first domain is labelled "evaluation" in the abstract, not "screening" (screening appears only in the objective/results).
- **Suggested fix:** "Use "evaluation" for the first domain."

### Study 14: A Steady Daily Rhythm — Not Just More Sleep — Tracked With Healthier Kidneys in Older Adults
**PMID:** 42686460 | **Verdict:** ⚠️ Minor issues

**Issue A. Measurement device not stated in abstract** — Severity: Minor

- **As written:** "using wearable-derived measures of sleep and 24-hour rest-activity rhythms alongside kidney function"
- **Abstract says:** "Sleep and 24-hour rest-activity rhythm parameters, including total sleep time (TST), wakefulness after sleep onset (WASO), interdaily stability (IS), intradaily variability (IV), Least active 5 h span (L5), Most active 10 h span (M10), and relative amplitude (RA)."
- **Problem:** The abstract names the rhythm metrics but never says how they were collected. Unverifiable from abstract only (though these metrics are conventionally actigraphy-based).
- **Suggested fix:** "Say "rest-activity rhythm measures (interdaily stability, intradaily variability, most/least active hours)" without specifying the device, or verify from the full text."

### Study 15: A Subtle Sleep Brain-Wave Pattern Is Weakened in Alzheimer's — and May Reflect the Brain's Overnight Cleaning Cycle
**PMID:** 42708477 | **Verdict:** ✅ Accurate

No factual errors found. Framing is consistent with the abstract.

### Study 16: Sleep Experts Issue 114 Consensus Recommendations for Parkinson's-Related Sleep Problems
**PMID:** 42731925 | **Verdict:** ✅ Accurate

No factual errors found. Framing is consistent with the abstract.

### Study 17: Medicare's Free Annual Wellness Visit Was Linked to Catching Mild Cognitive Impairment Sooner
**PMID:** 42456217 | **Verdict:** ✅ Accurate

No factual errors found. Framing is consistent with the abstract.

### Study 18: Weighted Blankets for Dementia: Safe and Well Tolerated, but No Proof They Improve Sleep
**PMID:** 42679410 | **Verdict:** ⚠️ Minor issues

**Issue A. Staff acceptability attribution** — Severity: Minor

- **As written:** "Nobody withdrew, there were no adverse events, and staff found the intervention practical to deliver."
- **Abstract says:** "Weighted blankets were considered feasible and acceptable with high recruitment rates, nil participant withdrawals and no adverse outcomes, however there was variable compliance to the intervention protocol"
- **Problem:** The abstract reports feasibility and acceptability in general terms and notes variable protocol compliance; it does not attribute a judgement of practicality specifically to staff.
- **Suggested fix:** ""...and the intervention was judged feasible and acceptable overall, though compliance with the protocol varied.""

### Study 19: In Frail Older Adults, Mood and Sleep — Not Physical Limits — Sit at the Center of Quality of Life
**PMID:** 42716517 | **Verdict:** ✅ Accurate

No factual errors found. Framing is consistent with the abstract.

### Study 20: An Eight-Week Lifestyle Program — by App or by Booklet — Eased Depression, and the Booklet Helped Insomnia
**PMID:** 42503319 | **Verdict:** ✅ Accurate

No factual errors found. Framing is consistent with the abstract.

## Issue Summary

| Study # | Headline | Verdict | Notes |
|---------|----------|---------|-------|
| 1 | Sleeping Nine Hours or More May Signal Trouble: Large Chinese Study Links Sleep Extremes to Earlier Death | ⚠️ Minor issues | Sample size, hazard ratios, U-shaped pattern and null napping/disturbance findings all match. Only issue is turning a null result into active reassurance about napping. |
| 2 | Heart and Metabolic Conditions Make Depression Stickier — And Bad Sleep Makes It Worse | ⚠️ Minor issues | Ns, mean ages, and the 21-29% / 21-26% hazard ranges match the abstract exactly; only the country-specific claim about the interaction is not stated in the abstract. |
| 3 | One Pill Leads to Another: Dementia Drugs Followed by Sleep Medications in 1 in 10 Older Adults | ⚠️ Minor issues | Cohort size, age threshold, 65 candidate cascades, 24 prioritized, the 10.3% cholinesterase inhibitor-to-sleep-agent incidence and the top temporal signals all check out; CIHR funding correctly disclosed. Dose-timing advice is an extrapolation. |
| 4 | For Older Adults With Advanced Cognitive Impairment, Sleep Hours Were the Strongest Clue to Depression | ⚠️ Minor issues | N=5,798, accuracy range 0.755-0.767, and the split of top predictors ('feeling energetic' vs 'sleep duration per day') are all reported correctly; the 'diagnostic weight' framing overreaches slightly. |
| 5 | Long daytime naps linked to slower thinking speed in older adults, new sleep study finds | ✅ Accurate | N=686, nap definition, processing-speed association, the non-significant apnea interaction, the apnea-plus-under-represented-group executive function finding, exploratory framing and the Axsome/Eli Lilly disclosures all match the abstract. |
| 6 | One in five older New Yorkers surveyed used cannabis in the past year — and half reported using it to sleep | ⚠️ Minor issues | Sample, 22.2% past-year use, reasons for use, 32.9%/5.7% CUD figures and the consulting disclosure are all correct; the side-effect ordering is reversed and the 24-hour figure's denominator is presented without noting the abstract's wording. |
| 7 | How seniors rate their own sleep sits at the center of their mental health — at least at home | ✅ Accurate | Sample sizes, network density/core-node descriptions, the non-significant Network Comparison Test results (p = 0.233 and p = 0.124) and the institutional network's limited stability are all represented faithfully, and the digest explicitly flags the non-significance. |
| 8 | Vitamin D Levels Track With Longer, Less Broken Sleep in Older Adults | ⚠️ Minor issues | N=460, demographics, the +23.63 and -23.03 minute estimates, stronger associations in Black participants and the sex-divergent B12 results all match; the novelty claim and the effect-size framing need softening. |
| 9 | Sleeping 10 Hours or More — and Regular Daytime Napping — Flag Lower Cognitive Scores in 89,000 Europeans | ⚠️ Minor issues | 88,889 interviews, waves 8-9 (2019-2022), mean age 68.88, 55% women, 7%/12%/81% cognitive categories, and the adjusted findings for ≥10-hour sleep and napping are all correct; the headline counts interviews as people. |
| 10 | 'Circadian Syndrome' — Poor Sleep Plus Metabolic Problems Plus Low Mood — Linked to Memory Complaints, Especially in Men | ⚠️ Minor issues | N=2,008 cognitively normal HMACS participants, the dose-response link to SCD severity, the male-stronger SCD-domain association, the GFAP/Aβ42-40/NfL patterns and the null indirect-effect analysis are all reported correctly; only the biomarker labeling is loose. |
| 11 | New Pill for Narcolepsy Restores Daytime Wakefulness in Two Large Trials | ⚠️ Minor issues | Core trial facts and MWT/ESS/adverse-event numbers match, but the cataplexy result omits the sizeable placebo response, the drug's investigational (not yet approved) status is never stated, and "Restores" plus the "first drug class" and "normal range" claims go beyond the abstract. |
| 12 | A Pre-Surgery Snapshot Including Sleep and Body Clock Predicts Who Struggles After Cancer Surgery | ⚠️ Minor issues | Design, N, index construction, effect sizes and the three recovery trajectories all match the abstract; the only gap is that the cohort's country (China) is never stated despite a generalizability caveat. |
| 13 | Expert Panel Issues New Roadmap for Bladder Problems in Parkinson's — Including the Nighttime Trips That Wreck Sleep | ⚠️ Minor issues | Panel composition, Delphi method, domains and algorithm are accurately described; one sentence reverses the abstract's stated direction between urinary symptoms and mobility impairment. |
| 14 | A Steady Daily Rhythm — Not Just More Sleep — Tracked With Healthier Kidneys in Older Adults | ⚠️ Minor issues | All directions of association (IS, L5, M10 protective; IV and total sleep time adverse) and the joint-analysis finding match the abstract; the description of the measures as "wearable-derived" is not stated in the abstract. |
| 15 | A Subtle Sleep Brain-Wave Pattern Is Weakened in Alzheimer's — and May Reflect the Brain's Overnight Cleaning Cycle | ✅ Accurate | Findings on reduced ISO amplitude with preserved frequency and bandwidth, the trend-level amyloid association and the bandwidth–NfL link are all faithfully reported, and the digest appropriately flags the mechanistic, non-clinical nature of the work. |
| 16 | Sleep Experts Issue 114 Consensus Recommendations for Parkinson's-Related Sleep Problems | ✅ Accurate | Panel size, four Delphi rounds, 100% agreement threshold, 114 statements, subtopics and the handling of non-unanimous statements all match; disclosures listed in the caveats correspond to the abstract's competing-interest statement. |
| 17 | Medicare's Free Annual Wellness Visit Was Linked to Catching Mild Cognitive Impairment Sooner | ✅ Accurate | Data sources, matching approach, two-year window, higher MCI diagnosis rate with similar time to dementia diagnosis, and the caveat about higher baseline cognitive scores in the AWV group all track the abstract. |
| 18 | Weighted Blankets for Dementia: Safe and Well Tolerated, but No Proof They Improve Sleep | ⚠️ Minor issues | N, crossover design, outcomes, null efficacy result, feasibility findings, Withings limitation and Dementia Australia funding are all accurate; only the claim that staff found delivery practical goes slightly beyond the abstract. |
| 19 | In Frail Older Adults, Mood and Sleep — Not Physical Limits — Sit at the Center of Quality of Life | ✅ Accurate | Sample, survey years, HINT-8 network analysis, the depression–happiness and stairs–pain links, central domains in each group, and the shared correlates of better HRQoL are all accurately reported; the story angle correctly notes the centrality of "working" in both groups. |
| 20 | An Eight-Week Lifestyle Program — by App or by Booklet — Eased Depression, and the Booklet Helped Insomnia | ✅ Accurate | Three-arm design, N=122, response rates (78%/55% vs 19.5%), maintenance at 1- and 3-month follow-up, the booklet-only insomnia effect (d=0.83) and the app's additional gains all match, and the caveats correctly flag the waitlist control, Hong Kong setting and non-geriatric sample. |

**Total issues:** 23 (21 Minor, 2 Moderate, 0 Major)
**Entries requiring revision:** 13
**Entries cleared:** 7
