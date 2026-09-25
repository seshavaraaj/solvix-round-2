# Hackathon Deck Judging Playbook

Read this when writing slide content. It explains how decks are reviewed, what
separates winning decks from losing ones, and a content formula for every
common template section.

## Contents
1. How decks are actually reviewed
2. What judges score (common rubric)
3. Winning vs losing decks — side by side
4. Content formulas per section
5. Writing rules (text density, wording)
6. Self-review checklist (score the deck like a judge)

---

## 1. How decks are actually reviewed

There are two very different review situations. Identify which one applies
from the template and hackathon rules, because it changes how much text a
slide should carry.

**A. Screening round (deck read without the team present).** Common in idea
submission rounds (e.g. Smart India Hackathon internal/national screening,
Devpost submissions, online qualifiers). A reviewer skims dozens to hundreds
of PDFs, often spending one to three minutes per deck. The deck must stand
on its own: every slide needs a claim a reader can understand without a
speaker. Reviewers check that every pointer the template asked for is
answered, in the template's order. Missing or re-ordered sections are the
fastest way to get rejected. Templates often say "use only the provided
template without changing the pointers" and "save as PDF".

**B. Live pitch (team presents, usually 3–10 minutes + Q&A/viva).** Slides
support the speaker. Less text, bigger visuals, a working demo or
screenshots early. Judges see many teams back to back and their attention
fades, so the deck must reduce effort, not add it. Put detail in speaker
notes, not on the slide.

Many hackathons use one deck for both (submitted, then presented). Default
to "self-explanatory but lean": a headline sentence per slide that states
the point, then 3–5 short supporting bullets or one diagram.

## 2. What judges score (common rubric)

Rubrics vary but converge on these dimensions. Map every slide to at least
one of them, and make sure every dimension is visibly covered somewhere.

| Dimension | Judge's question | Where it shows up |
|---|---|---|
| Problem / Impact | Is this a real, sizable problem? Who hurts, how much? | Problem, Impact & Benefits |
| Novelty / Innovation | Is this a fresh take, or the obvious solution? | Solution, "Uniqueness" |
| Solution fit | Does it actually solve the stated problem? Simpler alternatives? | Solution, Technical approach |
| Technical execution / Feasibility | Can this team build it? What is built already? | Tech approach, Architecture, Demo, Feasibility |
| Execution progress | What works now vs. what is planned? | Demo/screenshots, Status |
| Scalability / Viability | Can it grow, be sustained, be deployed? | Feasibility & Viability, Future scope |
| Presentation | Clear, structured, on time, demo shown? | Whole deck |

Example real rubric (NDN hackathon): Impact 10, Solution 20, Execution 20,
Presentation 10 — execution ("what was actually accomplished vs. proposed")
weighs as much as the idea. SIH-style screening lists novelty, complexity,
clarity, and completeness in the prescribed format.

If the user gives a rubric, it overrides this table. Mirror the rubric's own
words in slide headlines so the judge can tick boxes.

## 3. Winning vs losing decks — side by side

| Aspect | Winning deck | Losing deck |
|---|---|---|
| Opening | Opens on a specific person's pain ("Farmers lose 30% of produce because…") | Opens on tech ("We built a Next.js + LangChain app…") |
| Scope | One core flow done well; one "this is possible now" moment | Tour of 8 half-working features ("feature-itis") |
| Template | Every pointer answered, in order, headings unchanged | Sections skipped, merged, renamed, or re-ordered |
| Text | Headline claim + 3–5 short bullets; diagrams for flows | Paragraphs copied from the README; 10+ bullets; 10pt font |
| Uniqueness | States explicitly how it differs from existing solutions | Assumes novelty is obvious; no comparison |
| Evidence | Screenshots, architecture diagram, real numbers with source | Stock images, adjectives ("revolutionary", "seamless") |
| Tech | Stack tied to reasons; shows the hard part and trade-offs | Logo wall of 15 technologies with no explanation |
| Feasibility | Names real risks + concrete mitigation | "No challenges" or generic "we will work hard" |
| Honesty | Clear "Built / In progress / Planned" split | Implies everything works; judges catch it in Q&A |
| Impact | Who benefits, how many, what changes, measurable where possible | Vague "will help society" |
| Ending | One-line takeaway + what's next | Just "Thank You" |
| Design | Template's look, consistent, readable, lots of white space | Custom themes fighting the template, clutter, low contrast |

**Pros of the winning pattern:** judges understand it in under 30 seconds,
scoring is easy because the rubric words appear on the slides, Q&A goes
smoothly because claims match reality.

**Cons / risks of the winning pattern:** being lean can read as thin in a
screening round if bullets lack specifics — fix with concrete nouns and
numbers, not more bullets. Honest "planned" labels can look less complete —
still better than being caught out in the viva.

**Why losing decks lose:** the judge has to work to find the answer. Every
paragraph, every missing pointer, and every unexplained logo costs
attention the team never gets back.

## 4. Content formulas per section

Use the template's own heading. Under it, apply the matching formula.

**Title slide** — Fill every field the template asks for (Problem Statement
ID/title, theme, category, team name/ID, leader, institute). Add a one-line
idea tagline only if the template has room for it: `<Product>: <verb>
<outcome> for <user>`. Never leave a field label with nothing after it
unless the value is unknown (then flag it to the user).

**Problem** — Who (specific user) + pain (what goes wrong) + cost (time,
money, risk, scale; with a number and source if the project has one) + why
current options fail.

**Proposed solution / Idea** — Headline: one sentence of what it does.
Then: how it works in 3 steps from the user's view; how it addresses each
pain named in Problem (map 1:1); "What's unique" as 2–3 concrete
differentiators versus named alternatives.

**Technical approach** — Stack grouped by layer (Frontend / Backend / ML /
Data / Hardware / Infra) with a few words on why each choice. Methodology as
a flow: input → processing → output, or an architecture diagram if the
template asks for flowcharts/images. Mention the hardest technical piece and
how it's handled.

**Demo / Prototype / Screenshots** — Real screenshots from the project if
they exist (from the repo, docs, or user). Caption each with what the user
is doing. State status: Built / In progress / Planned.

**Feasibility & viability** — Why it is buildable (existing components,
team skills, prototype progress, data availability). Risks as `Risk →
Mitigation` pairs (2–4). Viability: cost, deployment path, who pays or who
adopts.

**Impact & benefits** — Beneficiaries by group (users, organisation,
society/environment/economy). Measurable outcomes where the project gives
them; otherwise qualitative but specific. Scalability in one line.

**Research & references** — Real sources only: papers, datasets, APIs,
government reports, docs used by the project. Short citation form. Never
fabricate.

**Future scope / Roadmap** — 3–4 next steps in order, realistic.

**Team** — Name + role + one relevant strength each, if the template asks.

**Closing** — One-line takeaway that restates the problem→solution
contrast; contact/repo link if allowed.

## 5. Writing rules

- **Headline first.** Where the template has a free line under the heading,
  or the first bullet, write the slide's point as a full claim
  ("Cuts triage time from 20 min to 2 min"), not a label ("Benefits").
- **3–5 bullets per box, ≤ ~12 words each.** One idea per bullet. Sub-bullets
  only one level deep.
- **Concrete over generic.** Replace "AI-powered", "seamless",
  "revolutionary", "user-friendly" with what it does.
- **Parallel structure.** Bullets in a list start the same way (all verbs or
  all nouns).
- **Numbers need a source** from the project or user. Don't invent stats,
  user counts, accuracy figures, or market sizes. If an important number is
  missing, write the claim qualitatively and list the gap for the user.
- **Match the jury.** Technical jury → trade-offs and architecture.
  Non-technical/government jury → users, outcomes, deployment.
- **Mirror the problem statement's wording** so reviewers can match it.
- **Detail goes to speaker notes**, not the slide (only if the template
  keeps notes; notes are dropped in PDF export, which is fine).

## 6. Self-review checklist (score the deck like a judge)

Before delivering, answer each with yes/no. Fix any "no".

1. Can someone read only the slide headlines and understand problem →
   solution → proof → impact?
2. Is every template pointer answered, in the template's order, under the
   unchanged heading?
3. Is the problem stated before any technology is mentioned?
4. Is "what's unique" explicit and compared against something real?
5. Is there at least one visual of the actual product or its architecture?
6. Is it clear what is built vs. planned?
7. Does every number come from the project or the user?
8. Is every slide within the text-density rules, with no overflow?
9. Is the slide count within the stated limit?
10. Does it look like the template — same fonts, colors, layout — with no
    added decoration?
