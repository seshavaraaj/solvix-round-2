---
name: hackathon-ppt-builder
description: Analyze a hackathon project (repo, README, code, docs, notes, or a description) together with a hackathon's template deck (.pptx/.potx), then fill the template with judge-ready content while keeping the template's own design. Handles slide/page limits — reads the template's rules, asks for the limit if none is given, and either adds slides within the limit or fits content into the existing count. Use this skill whenever the user mentions a hackathon PPT, idea submission deck, pitch deck template, Smart India Hackathon (SIH) / Devpost / college hackathon slides, "fill this template with my project", or wants a hackathon presentation reviewed or rewritten — even if they don't say "template".
---

# Hackathon PPT Builder

Turn a project into a hackathon deck by writing **content** into the
**organizer's template**. The template's design is the brand the judges
expect; this skill changes words, not looks.

This skill builds on the `pptx` skill. Read `/mnt/skills/public/pptx/SKILL.md`
first — its unpack → edit XML → pack workflow, `add_slide.py`, `clean.py`,
`validate.py`, and QA steps are used below. (Paths to its scripts are
relative to `/mnt/skills/public/pptx/`.)

For what judges look for and how to phrase each section, read
`references/judging-playbook.md` before Step 4.

## Inputs

1. **Template deck** — the hackathon's .pptx/.potx. If only a PDF or Google
   Slides link is given, ask for the .pptx export (a PDF cannot be edited
   into a template-faithful deck).
2. **Project** — any of: uploaded repo/zip, README, source files, report,
   pitch notes, screenshots, or a written description.
3. **Optional** — problem statement text, judging rubric, slide/page limit,
   presentation time, team details (names, IDs, institute).

Words "page" and "slide" mean the same thing here.

## Workflow

### Step 1 — Analyze the project → project brief

Read the project material (README first, then docs, then code structure,
package manifests, and existing screenshots/images). Write a short brief in
your working notes with these fields:

- Problem: who is affected, what goes wrong, evidence/numbers (with source)
- Target users and the problem statement it answers (ID/title if given)
- Solution in one sentence; the core user flow in 3 steps
- What's unique vs. existing alternatives
- Tech stack by layer, and why; architecture (components + data flow)
- Status: **Built / In progress / Planned** (derive from code, not claims)
- Hardest technical part and how it is solved
- Risks and mitigations; cost/deployment path
- Impact: beneficiaries, measurable outcomes (only real numbers)
- References: datasets, APIs, papers, docs actually used
- Assets: screenshots, diagrams, logos present in the project
- Gaps: anything the template asks for that the project doesn't answer

Rules: never invent metrics, users, accuracy, market size, or references.
If a gap matters, write the claim qualitatively and report the gap at the
end. Don't ask about gaps up front unless the missing item is required for a
title-slide field and there's no way to proceed (e.g. no team name at all) —
collect questions and ask once.

### Step 2 — Analyze the template

```bash
python scripts/inspect_template.py template.pptx --json template_inventory.json
python /mnt/skills/public/pptx/scripts/thumbnail.py template.pptx template-thumbs
markitdown template.pptx
```

`inspect_template.py` (in this skill's folder) lists each slide's XML file,
role guess, every text box with its font sizes and an estimated character
capacity, existing pictures/tables, and every rule it finds (slide limits,
time limits, "PDF only", "don't change the pointers", "avoid paragraphs").
View the thumbnail images too.

From this, record for each slide:
- **Heading** (keep verbatim — judges score against it)
- **Pointers/prompts** the slide asks you to answer (e.g. "How it addresses
  the problem") — these are instructions to replace with answers
- **Fixed elements** to keep untouched: logos, footer ("@SIH Idea
  submission- Template"), page numbers, decorative shapes
- **Editable slots** and their capacity
- **Role**: title / content / instructions / closing

Instruction-only slides ("IMPORTANT INSTRUCTIONS", "Guidelines") are for the
team, not the judges. Remove them from the output unless the rules say to
keep them, and mention the removal in the final summary. They usually don't
count toward the slide limit.

Determine the **slide limit** in this order: user's message → rules in the
template (slides + notes) → hackathon rules the user shared. A phrase like
"maximum six (6) slides including title" is a hard cap. Also note if the
template explicitly forbids adding slides or changing pointers.

### Step 3 — Plan content-to-slide mapping and slide count

Map every brief field to a template slot, in the template's order. Every
pointer must get an answer; pointers you can't answer get the best honest
answer plus a gap note (never a leftover prompt).

Estimate the fit: draft content for each slot and compare its length with
~70% of the slot's capacity. Then decide:

1. **Fits** → keep the template's slide count. Done.
2. **Overflows** → compress first, in this order: cut adjectives and filler;
   shorten bullets to ≤12 words; merge overlapping bullets; turn a process
   paragraph into a simple flow (A → B → C); move explanation to speaker
   notes. Re-estimate.
3. **Still overflows** → a slide increase is needed. Check the limit:
   - **Limit known and above current count** → add only the slides needed,
     never exceeding the limit. Add a continuation of the overflowing
     section (e.g. "Technical Approach (2/2)") by duplicating that same
     template slide so the design matches, or add a slide for a section the
     rubric values that the template lacks (e.g. Demo/Screenshots).
   - **Limit known and already reached, or template forbids adding** → do
     not add slides. Fit into the existing count with harder compression:
     keep only the strongest 3–4 points per slot, prefer diagrams over
     text. Tell the user what was cut.
   - **No limit found anywhere** → **ask the user before changing the
     count.** Use `ask_user_input_v0` (or a single plain question if that
     tool isn't available) with options like: "Fit into the current N
     slides", "Allow up to N+X slides" (X = what you need), "There's a
     different limit". Wait for the answer, then proceed with the matching
     branch above.

Never shrink fonts to make content fit. If a slot's font would need to go
below the template's size (or below 12pt), cut words instead.

### Step 4 — Write the content

Apply the formulas and writing rules in `references/judging-playbook.md`.
Key points:
- Keep the template's headings and section order exactly.
- Replace prompt/pointer text with answers. Where the template lists
  pointers as sub-headings meant to stay (e.g. bold labels like
  "Proposed Solution:"), keep the label and write the answer after or under
  it. When unsure whether a pointer is a label or a prompt, keep it as a
  short bold label followed by the answer — reviewers can still tick it.
- Lead with the problem and the user, then the solution, then the tech.
- One headline claim per slide, then 3–5 bullets of ≤ ~12 words.
- State Built / In progress / Planned honestly.
- Title slide: fill every field; replace "Your Team Name" footers with the
  real team name.

### Step 5 — Edit the deck (content only, template design)

Follow the pptx skill's "Editing existing decks and templates" workflow:

```bash
python3 -c "import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall('unpacked')" template.pptx
# structural work FIRST: duplicate slides (add_slide.py), delete instruction
# slides / reorder by editing <p:sldIdLst> in ppt/presentation.xml, then:
python /mnt/skills/public/pptx/scripts/clean.py unpacked/
# THEN edit text in ppt/slides/slideN.xml
(cd unpacked && rm -f ../output.pptx && zip -Xr ../output.pptx .)
```

Design rules — "minimal design":
- Edit only the text inside existing `<a:t>` runs. Keep each run's `<a:rPr>`
  and each paragraph's `<a:pPr>` so fonts, sizes, colors, and bullets stay
  the template's. One `<a:p>` per bullet, copying a sibling paragraph's
  properties. Bold (`b="1"`) is allowed for inline labels only.
- Do not add themes, colors, fonts, backgrounds, accent bars, icons, stock
  images, or decorative shapes. Do not move or resize fixed elements.
- Allowed additions, only when they carry content: real project
  screenshots/diagrams (placed in the slot's empty area, aspect ratio kept),
  a simple flow of plain boxes and arrows using the template's existing
  theme colors and fonts when the pointer asks for a flowchart/methodology,
  or a plain table in the template's style. Prefer duplicating an existing
  template element over drawing a new one.
- Remove unused template slots completely (the whole group, not just the
  text) — e.g. a 4th team-member card when there are 3 members.
- Speaker notes: optional, for detail cut from slides.

### Step 6 — QA

1. `markitdown output.pptx` — check every pointer is answered, headings
   unchanged, order kept, team name/footers filled.
2. Leftover-prompt check — no template prompt text remains:
   ```bash
   markitdown output.pptx | grep -iE "your team name|problem statement id –\s*$|describe your|detailed explanation of|e\.g\.|lorem|ipsum|xxx|\[insert|TODO"
   ```
   (Adjust the patterns to this template's own prompt wording from Step 2.)
3. Slide count ≤ limit (instruction slides removed).
4. `python /mnt/skills/public/pptx/scripts/office/validate.py output.pptx --original template.pptx`
5. Render and look at every slide (pptx skill → "Converting to Images").
   Check overflow first, then overlaps, leftover decoration from removed
   slots, and that each slide still looks like the template's thumbnail.
6. Score it with the self-review checklist at the end of
   `references/judging-playbook.md`; fix any "no".
7. If the rules require PDF submission, also export a PDF with
   `python /mnt/skills/public/pptx/scripts/office/soffice.py --headless --convert-to pdf output.pptx`.

### Step 7 — Deliver

Save to `/mnt/user-data/outputs/` (keep the template's extension; add the
PDF if required) and present the files. Then give a short summary:
- Slide count used vs. limit, and any slides added/removed (and why)
- Gaps the team should fill (missing IDs, numbers, screenshots)
- Anything cut for space that they may want to say aloud
