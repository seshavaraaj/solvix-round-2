---
name: presentation-helper
description: Prepares a presenter for a talk by studying their slide deck (.pptx, .pdf, .key export, or slide notes) together with the project behind it, researching the topic, and writing a comprehensive rehearsal Q&A file of likely audience questions, tough critiques, and model answers, saved to the .presentation-helper/ folder in the project root as numbered question-and-answer-N.md files. Use this skill whenever the user wants to prepare for, rehearse, practice, or "warm up" for a presentation, demo, pitch, thesis/viva defense, project review, interview presentation, or conference talk, or asks things like "what will they ask me", "help me get ready for my presentation", "anticipate questions on my slides", "play devil's advocate on my deck", or "make me feel confident presenting this", even if they don't mention Q&A explicitly.
---

# Presentation Helper

Help the user walk into their presentation feeling prepared and confident. The deliverable is a single Markdown rehearsal file containing the questions the audience is most likely to ask, the hardest critiques they might raise, and clear, honest answers the presenter can adapt in their own words.

The file is a warm-up tool, not a script. Answers should be short enough to say out loud, grounded in the user's actual deck and project, and honest about weaknesses. A presenter who has already heard the hardest question in private is far calmer when it comes up in public, so do not soften the critiques.

## Workflow

### 1. Locate the inputs

Find three things before writing anything:

- **The deck.** Use the file the user names. Otherwise look in the project root for `*.pptx`, `*.pdf`, `*.key`, or a `slides/`, `docs/`, or `presentation/` folder. If there are several candidates, ask which one. If there are none, ask the user to share the deck or paste an outline.
- **The project.** The project root is the current working directory (or the git root, via `git rev-parse --show-toplevel`, if one exists). Skim the README, docs, key source files, data or results folders, and config files, so answers reflect what was actually built, not only what the slides claim.
- **The context.** Who is the audience, how long is the talk, and what is at stake? If the user hasn't said, infer from the deck (a thesis title slide, a "The Ask" slide, a sprint-demo layout), state the assumption at the top of the report, and ask at most one short question if the audience genuinely can't be inferred. Audience changes the questions a great deal (see the table in step 4).

### 2. Extract the deck content

Pull out the text of every slide **and the speaker notes**, keeping slide numbers so questions can be tied back to specific slides.

For `.pptx`:

```bash
pip install python-pptx --quiet 2>/dev/null || pip install python-pptx --break-system-packages --quiet
python3 - "$DECK" <<'PY'
import sys
from pptx import Presentation
prs = Presentation(sys.argv[1])
for i, slide in enumerate(prs.slides, 1):
    print(f"\n=== Slide {i} ===")
    for shape in slide.shapes:
        if shape.has_text_frame and shape.text_frame.text.strip():
            print(shape.text_frame.text.strip())
        if getattr(shape, "has_table", False) and shape.has_table:
            for row in shape.table.rows:
                print(" | ".join(c.text.strip() for c in row.cells))
    if slide.has_notes_slide:
        notes = slide.notes_slide.notes_text_frame.text.strip()
        if notes:
            print(f"[Notes] {notes}")
PY
```

For `.pdf`, use `pdftotext -layout deck.pdf -` or `pypdf`. Keynote files must be exported to PDF or PPTX first; tell the user if that is needed.

Charts and images carry no extractable text. If a slide is mostly visual, render it (e.g. `soffice --headless --convert-to pdf` then `pdftoppm -png -r 60`) and look at it, because charts are where the sharpest questions come from ("why does the y-axis start at 40?", "what's the sample size?").

### 3. Analyse before researching

Build a quick internal map of the talk:

- The core claim or ask in one sentence.
- The evidence offered for it (numbers, benchmarks, user quotes, demos).
- Assumptions that are stated, and assumptions that are silently relied on.
- Gaps between the slides and the project (a feature claimed on slide 6 that is half-built in the code, a metric with no source, a result that differs from the data folder).
- Jargon, acronyms, and numbers the presenter must be able to explain instantly.
- The single slide most likely to draw fire.

The gaps are the most valuable part of this step: they are exactly what a sharp audience member will find, and the presenter would much rather hear about them now.

### 4. Research the topic

Use web search (if available) to learn what a well-informed audience already knows and doubts about this subject. Aim for roughly 4–10 searches, scaled to the depth of the topic. Look for:

- **Common criticisms** of the approach, technology, or business model in the field.
- **Competing or prior work** the audience may compare against ("how is this different from X?").
- **Recent developments** that might date the deck or undercut a claim.
- **Standard questions** typical of this presentation format (e.g. viva questions on methodology, investor questions on market size and moat).
- **Facts to verify**: check any statistic or claim in the deck that can be checked, and flag ones that look wrong or outdated.

Record sources as links so the presenter can read further. If web search is unavailable, say so in the report and rely on domain knowledge, marking those points as unverified.

Tailor the emphasis to the audience:

| Audience | What they push on |
|---|---|
| Academic panel / thesis defense | Methodology, validity, sample size, related work, limitations, contribution, "what would you do differently" |
| Investors | Market size, traction, moat, competition, unit economics, team, use of funds, why now |
| Executives / stakeholders | Cost, ROI, risk, timeline, resourcing, what decision is needed from them |
| Technical peers / engineering review | Architecture choices, scalability, edge cases, security, alternatives considered, tech debt |
| Clients / customers | Fit to their problem, pricing, support, integration effort, proof it works |
| Class / course project | Understanding of fundamentals, individual contribution, design choices, what was learned |
| Job interview presentation | Your role and reasoning, trade-offs, how you handle pushback, fit with the team |

### 5. Write the report

Determine the file number: list `<project-root>/.presentation-helper/`, find existing `question-and-answer-<N>.md` files, and use the highest `N` plus one (start at `1`). Never overwrite an earlier report; the user may want to compare rehearsal rounds. Create the directory if it does not exist.

Write the report using the template below. Guidelines for the content:

- **Answers are spoken, not written.** Aim for 2–5 sentences per answer: a direct response first, then one supporting point, then (optionally) a bridge back to the presenter's key message. Use first person ("we chose…", "I found…") so the user can rehearse it aloud.
- **Ground every answer in the deck or project.** Cite the slide or file it relies on, e.g. `(Slide 7)` or `(src/model.py)`. If an answer needs a fact that is not in the materials, write the best answer possible and mark it `[VERIFY: …]` rather than inventing a number, name, or result. A confident-sounding fabricated answer is the worst thing this report could contain, because the presenter may repeat it in front of the audience.
- **Critiques must be real.** Write each one the way a skeptical but fair expert would actually phrase it, then give the strongest honest response. If a critique is simply correct, say so and give a graceful acknowledgement plus what the presenter would do about it; conceding a fair point well builds more credibility than defending a weak one.
- **Prioritise.** Mark each question with likelihood (🔥 very likely, ⚡ possible, 🧊 unlikely but dangerous). The presenter may only have time to rehearse the top ten.
- **Cover breadth.** Aim for roughly 30–50 questions total for a typical 10–20 slide deck; fewer for a short deck, more for a defense or high-stakes pitch. Quantity is less important than covering every slide and every major claim.

## Report template

Use this structure. Omit a section only if it truly doesn't apply, and say why in one line.

```markdown
# Presentation Q&A Prep — Report <N>

**Deck:** <file name> · **Slides:** <count> · **Generated:** <date>
**Audience (assumed/confirmed):** <audience> · **Format:** <length, setting>

## 1. The talk in one breath
- **Core message:** <one sentence>
- **The ask / takeaway:** <what the audience should do or believe>
- **30-second version:** <a short paragraph the presenter can say if the time is cut or someone asks "so what is this, in short?">

## 2. Top 10 questions to rehearse first
The ten most likely or most dangerous questions, each with a short answer. Rehearse these out loud before anything else.

### Q1 🔥 <question>
**Answer:** <spoken answer> (Slide X)
**If they push further:** <one-line follow-up>

## 3. Slide-by-slide questions
### Slide 1 — <title>
- **Q:** … 
  **A:** …
(Repeat for each slide that invites questions; group trivial slides together.)

## 4. Tough critiques and how to respond
### Critique 1: <the critique, phrased as the skeptic would say it>
- **Why they'd raise it:** <what in the deck or field prompts it>
- **Honest response:** <answer>
- **Concede or hold:** <Hold firm / Partially concede / Concede, with the one-line version>

## 5. Comparison and "why not X?" questions
Competing approaches, products, or prior work from the research, with a crisp differentiator for each.

## 6. Weak spots found in the deck and project
Issues the presenter should fix before presenting, or at least be ready for: unsupported claims, inconsistent numbers, outdated facts, slide-vs-project mismatches, confusing visuals. Give a suggested fix for each.

## 7. Numbers, terms, and facts to know cold
A compact table of every key figure, acronym, and definition in the deck, with where it comes from.

| Item | Value / meaning | Source |
|---|---|---|

## 8. Rapid-fire drill
15–20 short questions with one-line answers, for a final five-minute warm-up.

## 9. Handling the unexpected
- How to answer when you don't know (e.g. "That's a good question; I haven't measured that directly, but based on X I'd expect Y. I'm happy to follow up.").
- How to handle a hostile or off-topic question, a question that's really a comment, and running out of time.
- 2–3 bridge phrases tailored to this talk's key message.

## 10. Confidence checklist
- [ ] Can say the 30-second version without notes
- [ ] Rehearsed the Top 10 out loud
- [ ] Fixed or prepared for every item in Weak spots
- [ ] Knows every number in section 7
- [ ] Has a plan for the demo/tech failing (if applicable)
- [ ] <talk-specific items>

## Sources
- [Title](link) — what it was used for
```

## After writing the report

Tell the user where the file is, then give a short summary in chat: the three questions they are most likely to face, and the single most important weak spot to fix before presenting. Keep it brief; the detail is in the file.

Offer, in one line, to run a mock Q&A where you ask the questions one at a time and give feedback on their answers. Live practice is where most of the confidence comes from.

If the project is a git repository and `.presentation-helper/` is not ignored, mention that they may want to add it to `.gitignore`. Don't edit `.gitignore` without asking.

## Follow-up runs

When the user runs the skill again (after revising the deck, or for a different audience), create the next numbered report instead of editing the old one. Read the previous report first: carry forward questions that still apply, note which weak spots have been fixed, and focus new effort on what changed. Add a short "Changes since report <N-1>" section at the top.
