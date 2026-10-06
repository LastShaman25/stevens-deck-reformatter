---
name: stevens-cpe-presentations
description: Create new presentations or redesign existing PowerPoint/PDF decks using the bundled Stevens or CPE templates, or a user-uploaded presentation template. Use when these brands or this template-based presentation workflow are requested. Do not use for developing the Slide Studio application or for unrelated document formatting.
---

# Stevens & CPE Presentations

Deliver an editable PowerPoint that follows the selected template, with content faithful to the user's sources. Work from the files in this skill and the files supplied in the conversation. This skill does not require the Stevens Slide Studio repository, its server, its accounts, or an external AI API key.

All paths below are relative to this SKILL.md. Resolve them from the installed skill location, never from an assumed working directory. Keep bundled assets and uploaded originals unchanged; write outputs to a separate working directory.

## Establish the task

- **Redesign:** The user supplies an existing PPTX or PDF and wants its design changed. Preserve its wording, data, qualifications, citations, and order by default. Rewrite, summarize, or reorder only when requested. A PDF supplied as reference material for a new deck belongs to the generation path instead.
- **Generate:** The user supplies a topic, outline, brief, or source documents. Create the narrative and slides for the requested audience and purpose.
- **Template:** Honor an explicitly chosen uploaded template first; otherwise use the requested bundled brand. If neither is selected, ask once: “Use Stevens, CPE, or a template you upload?” If multiple files have ambiguous roles, clarify which is the template and which is the content source. Do not silently choose a brand or mix both brands.

Ask only for missing details that materially change the deliverable. Honor a specified length; slide counts include opening and closing slides. Never add an obligatory closing to a one-slide request. When length is unspecified, select a reasonable length from the content and state the assumption. Missing presenter names or dates can be omitted rather than invented.

## Check execution capabilities

Use the host's available presentation creation and editing tools, following its presentation guidance when supplied. Confirm that you can access the actual template file and export a PPTX before promising a completed deck. Use rendering tools to inspect outputs when available.

The optional [template helper](scripts/template_tools.py) requires only Python 3.9+ and the standard library. It inventories layouts and makes a working PPTX copy of a PPTX/POTX template; it does not author or render slides. Use equivalent native tools if Python is unavailable. Do not install system software or ask users for API keys merely to invoke this skill.

If the environment cannot create or edit presentations, explain the missing capability and offer a slide outline or a handoff to an enabled environment. Do not represent text, HTML, renamed files, or a ZIP as a finished PowerPoint. If rendering alone is unavailable, deliver an otherwise valid deck with visual verification explicitly marked incomplete.

## Inspect and use the template

For either bundled template, read [template guidance](references/templates.md). For an uploaded template, derive its rules from that file; the bundled brand-specific rules do not apply.

1. Inspect the template's page size, masters, layouts, placeholders, themes, fonts, logos, and sample slides. Include layouts belonging to every master. Layout names alone are not enough: inspect the rendered opening, content, section, and closing artwork where possible.
2. Work from a copy of the template. Retain its actual masters, media, theme relationships, and artwork when the available tool supports that. Prefer the appropriate existing layout and placeholders over reconstructing branded slides on a blank canvas.
3. Remove sample instructions and sample content from output slides while retaining actual branding. A sample date or label can also carry a filled shape that masks artwork; preserve its visual function when replacing its text.
4. Keep text inside the selected layout's safe areas and clear of logos and footer artwork. Match the template's hierarchy and font sizes. Split dense content or use a better layout before shrinking text. Preserve original logo proportions and avoid stretching source images.
5. If the host cannot preserve the template structure and can only approximate it visually, disclose that limitation before substantial generation. Ask whether that approximation is acceptable when exact template use was requested.

## Redesign an existing deck

Inventory each source slide/page before rebuilding: visible text, numbers and units, equations, citations, notes, links, tables, charts, and meaningful images. Keep a source-to-output mapping so split slides can be checked for complete coverage.

Use native editable text, tables, and charts wherever supported. Preserve emphasis that changes meaning, chart data and legends, source notes, and working links. Adding a new template can duplicate old decorative branding: remove only clearly identified old template decoration; retain meaningful source artwork and citations. Do not remove questionable material solely because it repeats.

For PDFs, compare the original page image with extracted text. Equations, diagrams, and pages without a usable text layer may need image regions to retain fidelity. Do not reconstruct uncertain symbols from guesswork. Disclose which regions are images and therefore not individually editable. If full editability is required and cannot be provided faithfully, explain the tradeoff before proceeding.

Split content only where meaning stays intact. Repeat table headers when splitting tables and avoid splitting through a merged cell. Carry notes and internal-link destinations forward deliberately. Check hidden slides and speaker notes rather than silently losing them during import.

Do not imply preservation of animations, media, embedded objects, SmartArt, or other features the chosen tools cannot retain. Identify material losses and obtain the user's choice when these prevent meeting the request.

## Generate a new deck

Plan a concise sequence suited to the audience. Give each slide a purpose, proposed layout, factual basis, and a suitable visual type. Use tables for detailed comparisons, charts for supplied numerical evidence, and diagrams for relationships or processes. Avoid invented data for decorative charts.

If the user requests outline approval, present the outline and wait. Otherwise proceed from a clear brief, stating material assumptions without introducing an extra approval round.

Write concrete titles and concise supporting text. Preserve qualifications and source disagreements that affect the conclusion. Ground factual claims in supplied materials or sources retrieved for the task; do not invent quotations, statistics, institutional endorsements, citations, or references. If external research is needed but unavailable, identify the gap and limit the claims. Include relevant source references in speaker notes and keep essential citations/disclosures visible where needed.

Use an opening or closing only when it serves the requested deck and fits its length. Use the selected template's correct artwork for those roles.

## Verify and deliver

Reopen the exported PPTX and inspect its actual contents. Check slide count, order, source coverage, template choice, data, equations, citations, notes, links, and editability. A successful export alone does not establish correctness.

Render every output slide when supported and inspect it in presentation order, including split slides and added slides. Check for clipped or overlapping text, unreadable type, misplaced symbols, image distortion, low contrast, sample placeholders, and collisions with branded artwork. Compare redesigned slides against their source pages. Then review the deck as a whole for omissions, repetition, and sequence.

Fix actionable defects, export again, and recheck changed slides plus the overall sequence. Stop when checks pass or further repair is blocked or no longer improves the result; report unresolved issues instead of cycling indefinitely. Keep “not checked,” “checked with findings,” and “passed” distinct. Never claim an independent review agent or the Slide Studio application's QA ran unless it actually did.

Return a downloadable PPTX. Include a PDF if requested and a working exporter is available. Briefly disclose unresolved content/fidelity issues, rasterized regions, font substitutions, or incomplete rendering checks that affect use. A completed file may be delivered with findings; never relabel those findings as passed. Keep intermediate files out of the final handoff unless requested.
