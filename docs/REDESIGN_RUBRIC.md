# Stevens redesign and output QA rubric

Version: `cover-photo-clear-10` · September 25, 2026

## Governing principle

Preserve a composition that works. Make the smallest change that addresses an observable defect or the user's instruction. An unchanged slide can pass. Creativity is allowed where it improves communication; novelty, additional decoration, and rigid symmetry are not objectives.

The first page uses **1_Title Slide**. Extract native title and supporting elements and place them in its cover regions. Regular content pages use **Title Only**: all source elements belong inside the content box. The inherited **bottom-left Stevens logo and footer band are protected**. Source logos, footer strips, text, images and backgrounds must not cover that area.

## Approved section-header reference

The user-approved formatting reference is `SWE_-_Module_8__Stevens_Formatted_keyless-v3_fixed.pptx`, especially section dividers 5, 10, 14 and 19. Its lesson text is example content, not generator instructions. Keep the private reference outside version control.

- Classify section headers before selecting a layout. A section divider introduces a new lesson/topic; an ordinary slide with a heading is still a content slide.
- Omit the **bottom-left Stevens wordmark** on section headers. Use the bundled **Section Header** layout when redesign is needed; do not wrap the divider in the interior template.
- Preserve the complete **top-right logo**, including its font, spacing, line arrangement, colors and proportions. Preserve an already-good photo/title composition unchanged.
- Only a separately identified bottom-left Stevens footer logo may be removed. Record its source ID, role and reason. Composite imagery, linked artwork and dependent content remain protected; unresolved removal requires review, not destructive cropping.
- QA checks the original/candidate pair: a missing bottom-left mark is correct for a section divider. A surviving or newly added bottom-left mark is `brand_consistency`; stacking is `spatial_layout` only. Altered top-right logo typography remains a branding defect.
- Regular content slides still require the protected bottom-left template mark. The section exception does not change their content-box or footer rules.

## What the six supplied examples teach us

These observations concern the visible screenshots, not a forensic inspection of the source PPTX.

| Example | Visible problem | Required outcome |
| --- | --- | --- |
| 1: GenAI cover | Candidate contains a tiny inset of the cover; its main title is no longer visibly readable. Large background geometry remains disconnected from the meaningful content. | Identify the cover, background, title/subtitle, author and logo separately. Preserve their composition and contrast; reject thumbnail-sized covers and invisible titles. |
| 2: course introduction | Candidate looks almost blank except for the footer. The original's white text may still exist but is not visible against the output. | Check rendered visibility in addition to extracted text. Existing text with lost background contrast is a visual-legibility defect, not an additional completeness failure. |
| 3: learning objectives | The readable row structure is reduced in size; the source footer crowds the destination branding at bottom-left. | Preserve each number/row association, avoid unnecessary shrinkage, and separate footer/branding into clear areas. |
| 4: Python code | Code is displaced from its panel and its layout/indentation appears degraded. | Treat code and its panel as related elements; keep all lines inside the panel and preserve whitespace and reading order. |
| 5: section/photo slide | The top-right wordmark appears superimposed, with additional bottom-left branding beside the footer. | Review every mark, including inherited artwork. A corrupted or stacked wordmark is blocking; section dividers omit the bottom-left wordmark and preserve the top-right logo. |
| 6: 2M context slide | Content is reduced, with bottom-left branding/footer crowding. The statistic and explanatory panel must retain their intended relationship. | Keep the statistic centered in its own red panel, align related panels, preserve readable content, and clear branding collisions. |

## Generator procedure

1. **Identify roles before layout planning.** Inspect source and candidate screenshots and the complete editable-object inventory plus inherited template artwork. Assign each supplied ID exactly once: title, subtitle, body, code, equation, logo, footer, background, panel, decoration, image, chart, table, diagram, caption, axis label, legend, connector, group, or unknown.
2. **Record relationships and intent.** Record dependencies (text/background, code/panel, label/chart, caption/figure, multipart logo), alignment, its reference frame, confidence and reasoning. Do not guess that everything should be centered. Unknown is preferable to a false confident role.
3. **Validate the inventory.** Missing, duplicated or invented IDs and invalid relationship references stop planning. Role classification is a required model call, not an optional sentence in a prompt. Record it with the generation and repeat it for targeted repair passes.
4. **Plan minimal edits.** Use the validated inventory. Move related elements coherently. Keep background/foreground contrast and layer order. Preserve correct regions; explain the defect or instruction driving each proposed layout. An invalid layout contract gets at most one correction request with validation feedback, before any edit is applied; a second failure blocks redesign.
5. **Apply and independently verify.** Keep original wording, data, relationships and meaningful emphasis. Reopen the native PPTX, run structural/content checks, render, and apply the visual rubric. Every accepted candidate remains provisional until mandatory QA passes.
6. **Review the complete output in order.** A separate reviewer audits all final screenshots and then the full ordered deck. Incomplete review or missing rubric coverage blocks verified release.
7. **Return final QA findings to the redesigner.** Send rubric category, evidence, smallest repair and affected output-slide indices. Replan only affected slides, then rerender and review every slide in order. Accept a repair only when final QA improves without technical regression. Continue improving repair cycles until every per-slide and ordered-deck QA check explicitly passes, subject to the upload request/token budget and session deadline. The legacy repair-pass setting cannot disable this final gate. An unchanged or worse result retains the earlier candidate and its unresolved findings. Running a repair never counts as passing QA.

## Enforced template placement

Coordinates below are inches in the bundled 13.333 × 7.5 template.

| Region | x | y | width | height |
| --- | ---: | ---: | ---: | ---: |
| Interior content box | 0.70 | 0.40 | 11.70 | 6.05 |
| Cover title | 6.917 | 2.739 | 5.693 | 2.255 |
| Cover supporting text | 7.75 | 5.021 | 4.86 | 1.664 |
| Cover supporting graphics | 0.45 | 1.15 | 5.95 | 5.30 |
| Section title (below top-right logo) | 7.236 | 2.50 | 5.374 | 3.22 |
| Section supporting text | 7.50 | 5.90 | 5.11 | 1.02 |

The interior box ends at y=6.45, above the footer band starting at y=6.65. This applies to group children, original footer bars and backgrounds as well as ordinary text. Cover title/supporting text is white against the template's red field. The cover has approved campus imagery on the left and a white Stevens mark at top-right. **The interior bottom-left/footer restriction does not apply to covers or section headers.** Its inherited photo and rule are permitted template artwork, not unapproved additions or factual claims. QA must cross-check supplied coordinates before alleging an out-of-box placement.

Initial native extraction recognizes ordinary text boxes as possible titles using native title identity, font hierarchy and reading order. It records this hypothesis before placement; the mandatory AI role pass rechecks it before AI editing. Unknown graphics remain native objects, not silently deleted decorations. Explicit RGB source backgrounds are preserved as fixed panels to retain white-text contrast; their color, bounds, count and layer order are independently checked against the source.

The planner receives these regions, invalid proposals are rejected before editing, and the exported PPTX is checked again. Region intrusions, stacking and incorrect centering belong only to `spatial_layout`; contrast loss belongs only to `visual_legibility`. Final-QA repair history records the incoming findings, targets, hashes, checks, model calls and acceptance.

Role identification is descriptive, not permission to delete an object. A logo classification must not silently exempt a source object from preservation checks. Likewise a role map is a hypothesis for QA to verify, not evidence that the slide is correct.

## MECE review: scope and unit of assessment

The previous rubric was **not MECE**: it mixed object types (code/math, charts), failure mechanisms (stacking, contrast), outcomes (readability), and process/principles (roles, restraint). A single stacked wordmark could fail four categories. Factual support, instruction compliance, and technical release obligations also had unclear ownership.

This version partitions **individual, independently repairable defects**, not entire slides or object types. A slide may have multiple different defects; each finding has exactly **one primary category**. Consequences are described within that finding instead of scored again. Severity is independent of category. A complete slide audit visits all eight categories, but only categories owning findings can be adverse.

Collective exhaustiveness is bounded to **supported presentation generation/redesign and release**. Three layers cover that scope:

1. **Prerequisites:** approved requirements, source/object inventory, element roles, relationships and supported editing capabilities. Incomplete role identification stops layout planning.
2. **Presentation quality:** the eight categories below, applied to every supported element and the complete ordered deck.
3. **Technical release gates:** actual artifact preservation, notes/links/media checks, editability where required, render coverage/order, exact file/image identity, completed reviews and scoped approval. Screenshot QA cannot certify these gates. Unsupported objects remain blocked; they are not silently excluded.

Authentication, retention, deployment, and universal factual truth outside supplied evidence are outside this design rubric. Missing evidence is explicitly unverified/review, never assumed correct. A new unsupported requirement must expand the coverage map or remain unresolved; it must not be forced into an unrelated category to obtain a pass.

## Eight primary QA categories

| ID / category | Owns | Explicit exclusions |
| --- | --- | --- |
| `content_presence` — Completeness | Genuinely missing, extra/unapproved or duplicated non-brand slides, text, figures, data records, notes and citations. | Existing but invisible content goes to layout or legibility. Wrong present values go to accuracy. Logo presence/duplication goes to branding. |
| `content_accuracy` — Correctness and support | Wrong/altered/unsupported wording, facts, numbers, units, citations, code or mathematical meaning; contradictions between claims. | Absence goes to completeness; wrong association/order to structure; misleading visual encoding of correct values to fidelity. |
| `structure_sequence` — Relationships and order | Wrong semantic slide type or element role, title/body hierarchy, caption/figure or legend/series association, connector endpoint, reading order, prerequisites, transitions or argument structure. | Correctly associated items placed too far apart go to layout. Wrong content itself goes to accuracy. Missing steps go to completeness. |
| `spatial_layout` — Geometry and layers | All accidental stacking/occlusion, clipping, off-slide content, wrong position, containment, alignment, centering and gaps. Applies equally to logos, code, captions and charts. | Non-geometric contrast/size issues go to legibility; intrinsic distortion goes to fidelity; wrong logical associations go to structure. |
| `visual_legibility` — Perceptual readability | Correct, present, unobstructed content that is hard to decode because of size, contrast, resolution, line spacing, stroke weight or density. | Geometry-caused obstruction/clipping belongs to layout. Incorrect characters/meaning belong to accuracy. Do not mark this adverse again for the consequences of a layout defect. |
| `graphical_fidelity` — Representation | Stretched/distorted non-logo images; misleading bar lengths, scales, aspect ratios, axis truncation or visual encodings when underlying content/data is correct. | Wrong data goes to accuracy; wrong legend association to structure; cropping to layout; low resolution to legibility. |
| `brand_consistency` — Identity and style | Wrong/missing institutional mark, altered logo typography/spacing/line arrangement/proportions, wrong template for a correctly classified slide, separate redundant marks, unapproved palette/typeface and inconsistent style across comparable slides. | Overlap goes to layout; tiny/low-contrast marks go to legibility. Logo proportions are part of branding; non-logo distortion belongs to fidelity. Functional monospace code and meaningful source colors are not automatic brand defects. |
| `instruction_compliance` — Residual requirements | Explicit user/approved-outline/audience requirements with no owner above: tone, level of explanation, preserving a good composition, or an unjustified decorative transformation. | Never a second penalty for another defect. Ignoring “center this” is layout only. This is not a miscellaneous/catch-all category. |

## Classification procedure and tie-breakers

1. **Describe one observation and the smallest repair.** Do not combine unrelated defects or emit multiple findings for one defect with several consequences.
2. **Check actual presence before declaring loss.** Compare object inventory/extraction with screenshots. White-on-white text is legibility, not missing content. Cropped text is layout. If the screenshot alone cannot distinguish these, use one provisional evidence-backed category, mark review, and state the inspection needed.
3. **Separate content from relationships and encoding.** Wrong number = accuracy; right number linked to the wrong series = structure; right number/series drawn with misleading proportions = fidelity.
4. **Give physical failures a specific owner.** Collision/clipping/position/centering = layout; unobstructed but tiny/low-contrast/blurry = legibility; non-logo aspect distortion = fidelity; altered logo proportions = branding. None becomes an additional brand finding merely because it affects a logo.
5. **Apply branding only to residual identity/style failures.** For duplicate marks that manifest as one stacked wordmark, report layout once. If complete marks are separately positioned but unnecessarily repeated, report branding. Do not count the same mark pair twice.
6. **Apply instruction compliance only after excluding categories 1–7.** Restraint guides generation; it does not add a second “overdesign” penalty to an existing layout or readability finding.
7. **Keep ownership stable across stages.** The final deck review should reconcile repeated findings with the per-slide ledger, not relabel the same problem under another category. Separate independent defects can legitimately require separate repairs and categories.

MECE is an operational classification rule, not a claim that design qualities are causally independent. Validators enforce single-category assignment and checklist consistency; whether two descriptions refer to the same real-world defect still requires reviewer judgment.

## Detailed inspection lenses (not extra scores)

| Inspect every applicable element | Checks and primary owners |
| --- | --- |
| Titles, body, captions, notes and citations | Presence; literal accuracy/support; hierarchy/reading order; clipping/alignment; scale/contrast. Notes intentionally remain off-slide. |
| Logos, footers and master artwork | Check **every** logo location. Identity/redundancy → branding; overlap or insufficient clear space → layout; logo typography/proportion changes → branding; tiny/faint mark → legibility. Regular content pages protect the interior logo and footer; section headers omit the bottom-left wordmark. |
| Backgrounds, panels and grouped elements | Keep dependent foreground readable (legibility); inspect z-order/containment (layout), correct association (structure) and aspect ratios (fidelity). Intentional readable layering passes. |
| Centered content | Establish intended slide/panel/column/group reference first. Compare complete bounds and opposing gaps; inspect text alignment separately from box placement. Unintended offset → layout. Intentional asymmetry and optical adjustment pass. |
| Code and equations | Required tokens/lines → presence; semantics-changing indentation, operators, exponents or syntax → accuracy; panel containment → layout; cosmetic spacing/monospace clarity/symbol readability → legibility. |
| Charts, plots, tables and diagrams | Required values/rows/labels → presence; numbers/units/formulas → accuracy; legend/series and connector associations → structure; overlap → layout; readable labels → legibility; axis/proportion/encoding → fidelity. |
| Complete deck | Slide coverage → presence; factual agreement → accuracy; order/transitions/prerequisites → structure; cross-slide style → branding; residual audience/purpose requirements → compliance. |
| Native PPTX, notes, links, media, editability and rendering | Preserved content is cross-checked above; broken file/function, unsupported object handling, rendering completeness/order and byte identity belong to technical gates. A working link to a substantively wrong source is accuracy; a nonfunctional link is a technical failure. Do not certify either from screenshots alone. |

## Verdict and evidence contract

For each slide, record all eight category results: `passed`, `review`, `blocking`, or justified `not_applicable`. Every finding carries exactly one `criterion`, affected slide/elements/region, observable evidence, severity, `required_correction` and a testable `acceptance_condition`. Both reviewer schemas require nonempty `region`, `evidence`, `required_correction` and `acceptance_condition`, plus `object_ids` (empty only when the supplied IDs cannot locate the defect). Missing or blank handoff fields invalidate the review.

- `blocking`: confirmed lost/changed essential meaning, misleading data, unreadable essentials, or corrupted branding.
- `review`: genuine uncertainty or a minor observable defect. Lack of evidence cannot be converted into a pass.
- `passed`: applicable category inspected with no observed defect.
- `not_applicable`: an explicit explanation of why the category cannot apply; never a shortcut around missing review.

For each category, the checklist must equal the **highest severity of findings assigned to that category**. No owned findings means passed or justified not-applicable. A blocking layout finding cannot justify an adverse branding or readability checkbox. Conversely, a passed checkbox cannot hide its own finding. Missing/duplicate categories and inconsistent results invalidate the review.

Examples:

| Observation | One primary owner |
| --- | --- |
| Two wordmarks visibly overlap | Spatial layout |
| Two clear, separately placed but redundant wordmarks | Brand consistency |
| Wordmark stretched horizontally | Brand consistency |
| Wrong institution's mark | Brand consistency |
| White text still exists but is on white | Visual legibility |
| Title is actually absent from the output | Content presence |
| Correct code block sits outside its panel | Spatial layout |
| Code indentation changes program meaning | Content accuracy |
| Correct chart data is drawn with misleading bar lengths | Graphical fidelity |
| Correct legend label identifies the wrong series | Structure and sequence |
| A correct statistic is off-center in its intended panel | Spatial layout |
| Output ignores requested introductory explanation despite correct content/layout | Instruction compliance |

## Implementation boundaries and verification

The executable shared policy and the eight-category finding schema are `backend/app/ai/rubric.py`. The mandatory role phase is `element_roles.py`, used before each AI layout proposal. Per-slide visual review and final ordered output QA use the same detailed rubric and validate complete checklist coverage. Fresh topic/PDF authoring receives the same design rules and final QA; its title/body/visual roles are already explicit in its composition schema.

The native editor can move editable logos and associated shapes. Inherited master artwork is currently supplied as **non-editable context**: a prompt does not make it movable. The current source-preservation constraint also forbids silently deleting duplicate source marks. If editable repositioning cannot solve a conflict, QA must keep it unresolved rather than falsely approve it. Arbitrary master-art relocation/removal needs a separate, provenance-checked editing capability.

The existing native editor still enforces 40-point titles and preserves fixed/rotated geometry. This rubric does not silently remove those implementation constraints or claim to repair every bad example. Existing candidate approvals are invalidated by the verification-policy version change on the next backend start.

Verification covers: missing/duplicate/invented role IDs, invalid relationships, role calls preceding plans, planner consumption of the role map, inherited artwork context, missing/duplicate QA criteria, adverse checks without findings, and incomplete per-slide audit coverage. A live screenshot challenge checks the supplied bad examples separately from these contract tests. Screenshot QA remains model judgment, not a guarantee of visual quality.

### Historical MECE checkpoint (`mece-defect-2`)

- 95 affected AI/provider/authoring tests passed. The expanded 23-test rubric suite also passed, including single-category schema enforcement, identical category vocabularies across reviewers, and category-specific verdict consistency.
- Finding schemas accept exactly one of the eight primary categories. Legacy overlapping categories and secondary-category fields are rejected. The implementation derives the existing visual/accuracy/sequence UI groups; those are display groups, not additional rubric scores.
- The live recheck of the previously authorized screenshots was **not a completed six-image acceptance pass**. It produced valid reviews for four examples across two runs, encountered an invalid provider response, and rejected a later review for marking a category adverse without an owned finding. The final example was not reached. This demonstrates failure handling, not proof of perfect classification or detection.
- Some live classifications remain debatable when screenshots do not establish whether text is truly absent or simply invisible. Source/PPTX evidence or human inspection is needed to resolve that distinction. The rubric instructs one provisional category with explicit uncertainty instead of multiple speculative failures.
- Live evidence: `.local/verification/mece-screenshots-live-1/` and `.local/verification/mece-screenshots-live-remaining/`. Earlier six-image and end-to-end acceptance results below apply only to the previous rubric.
- No application restart, existing-deck regeneration, or approval override was performed during the MECE review.

### Historical checkpoint — previous rubric (`role-aware-minimal-1`)

- 137 offline backend tests passed, plus all 3 real PowerPoint renderer tests. After the validation-retry change, all 60 affected AI/provider/rubric tests passed. A separate targeted regression verifies that the single invalid-plan retry happens before editing.
- With explicit permission to transmit the six examples, live GPT-6 Luna QA found blocking defects in **all six**. It identified lost/shrunken cover content, the near-empty introduction, footer/wordmark collisions, and displaced/unreadable code. This measures rejection of these bad examples, not complete detection of every individual defect or proof of repair.
- Live synthetic end-to-end redesign completed role identification, planning, native editing, rendering, per-slide rubric review and ordered QA. All ten release checks passed; state `ready`, without manual approval overrides.
- Evidence is ignored development output: `.local/verification/rubric-screenshots-live-3/` and `.local/verification/role-phase-live-20260925-b/`. Uploaded screenshots are not copied into the repository.
- Run local checks with `tools/verify.ps1`. Repeat synthetic model verification with `tools/run_ai_smoke.py --live --output <new-directory>`. The new `tools/verify_design_rubric.py --live --images <comparison-images> --output <new-directory>` command explicitly sends the specified images to the configured QA provider and records criterion-level results.

The active application server was not restarted during this change, to avoid discarding an in-progress deck. New Python behavior takes effect on its next restart; an existing candidate is not evidence that the new rubric has run.


## Source-first decisions and paired QA (September 25 update)

Before template composition, the agent sees the ORIGINAL slide, its complete source-object inventory and rendered examples from the bundled template. It records roles, whether each element carries information or includes a logo, a slide-level keep/redesign decision, and explicit removal IDs with reasons.

- **Keep original:** an already-matching, readable template slide remains native and unchanged. This includes section and Thank You slides. Preserve the original layout, master, theme, positions, pictures and typography; do not paste it inside a second template. A nonvisual slide-name marker and globally unique imported layout IDs do not change its rendered appearance. Reopened verification compares the complete source/output dependency graph, excluding only those nonvisual import identifiers.
- **Keep or remove artwork:** remove only high-confidence redundant non-content decoration or backgrounds. Do not remove meaningful figures, code screenshots, labels, tables, charts, linked/connected objects or anything retained objects depend on. Uncertain images stay. Each removal is audited against the original source ID and recorded role decision; an allegedly removed picture still present is a blocking contract failure. A source background panel is omitted on the cover when no retained source element needs it.
- **Protect source logos:** keep all original marks, including small top-right marks. Do not delete them because the destination contains another logo. Protect logo typography/colors, proportions and multipart grouping. Matching slides preserve the original placement; redesigned slides preserve the mark and use clear space.
- **Paired QA:** both per-slide review and final ordered QA compare ORIGINAL and REDESIGNED images. Every output ordinal is explicitly mapped to its source ordinal; split slides repeat the corresponding source image. Missing original images block completion. Compare code lines and indentation, numbers/units, images and labels against the original; candidate-only text inventory is insufficient.
- **Challenge the decision:** a generator decision is not evidence of correctness. Wrongly removed meaningful imagery belongs to content_presence; a missing source logo belongs to brand_consistency. Unwanted retained decoration or gratuitous changes to an already-matching slide belong to instruction_compliance unless a more specific defect applies. Stacking is spatial_layout; unnecessary miniaturization is visual_legibility. Keep the eight-category MECE partition.
- **Repair the decision:** QA findings about missing content, branding or instruction compliance can trigger a new source decision for affected slides. The native composer can restore removed pictures or change the keep/remove decision; only affected output slides are replaced. Reopen, render and review again. Mapping changes or failed verification remain blocked. Coordinate editing alone is not treated as recovery of a missing picture.

Tests include rejecting removal of a logo/content-bearing picture, preserving logo bytes, detecting a retained rejected picture, restoring an incorrectly removed picture after QA, source/output pairs in split-slide order, and pixel-identical rendering of a kept template slide. Prior live evidence for earlier rubric versions remains historical.


## Actionable decisions and repair acceptance (current)

The generator records `slide_kind` (cover, content, section, closing) before composition. Source ordinal 1 is always the cover. An unchanged cover must already use the first-page layout; otherwise the generator transfers native title/subtitle/author into **1_Title Slide**. Validated semantic roles now drive cover extraction; a large logo or statistic cannot win a largest-font heuristic in the AI path. A cover with no identified native title stops for correction rather than pretending extraction succeeded.

Every source element records retain/remove/extract_logo and a reason. Removal IDs must agree with those element decisions, and remain subject to the existing non-content/non-logo safety checks. Remove obsolete cover-background pictures rather than overlaying the old cover on the template. Required branding embedded in a raster background may use the bounded extraction procedure below. Unsupported or uncertain extraction keeps the original image and remains unresolved; it cannot become an unverified plain removal.

### Embedded-logo extraction

1. **Native first.** Keep separate source pictures, vectors, text wordmarks and groups intact. Do not rasterize or retype an available native logo.
2. **Inspect the original image.** The source agent receives labeled raw raster images with dimensions, in addition to the slide screenshot. Known bundled artwork is matched first to suggest a logo region; otherwise the vision agent proposes one complete region in normalized image coordinates. It identifies the background as obsolete, and confirms that it contains no meaningful non-brand information. Textured backgrounds, existing picture crops/rotations/effects and ambiguous regions are unsupported.
3. **Check source pixels.** The extraction tool requires flat or transparent boundary padding, a bounded region, sufficient foreground detail and clear space. It trims to the complete foreground plus original padding and writes exact source pixels to PNG. No inpainting, reconstructed lettering, recoloring or upscaling. A small amount of the original flat background remains behind the mark.
4. **Compare approved marks.** Compare the crop's proportions and RGB appearance with logo regions in the bundled template. This is a conservative identity hint, not a semantic completeness certificate or authorization to substitute another logo variant. When the exact complete variant already exists on the destination layout, `placement=template_logo` reuses that mark instead of adding a duplicate. It requires both a strict asset match and the independent reviewer's explicit identity agreement. The exported inherited artwork must still match the approved template's bytes, geometry and XML. Otherwise `source_crop` preserves the original crop.
5. **Review before removal.** A separate vision call sees the original slide, full raw image and proposed crop, plus the destination mark when reuse is proposed. All four extraction checks must pass: complete required mark(s), only obsolete background removed, clean edges/clear space, and faithful source appearance. Template reuse additionally requires identity agreement. Failure allows one corrected source decision; otherwise the transformation stops. A side-by-side comparison uses the same display scale for source/template marks. The receipt is tied to source-image and crop hashes and cannot be supplied by the source agent. Rejected checks and their reasons go back to the source agent; disputed template identity can fall back to exact source-crop preservation, never unverified removal.
6. **Compose and reopen.** Replace the background picture with its verified crop, mark it as a protected logo, and keep its proportions at at least 96 source pixels per inch. The artifact checker reopens the source, recomputes the crop and compares actual output pixels; altered, missing, duplicated, cropped, distorted or hidden replacements fail even if placement metadata claims success.
7. **Review the rendered slide again.** Paired and ordered QA must independently check completeness, tiny lettering, color, clear space, readability, background removal and collisions with template branding. The earlier extraction review never waives final QA. Extraction-related failures can return to source decisions for a new crop or restoration, not only coordinate repair.

Keep MECE ownership: missing/altered logo identity → branding; clipping/stacking → spatial layout; insufficient resolution/contrast → legibility; lost non-brand content → content presence; needless retained decoration → instruction compliance. A single defect has one owner.

This is bounded crop extraction, not general segmentation of arbitrary photographic backgrounds. Difficult or low-resolution marks remain protected and require review instead of being guessed or redrawn.

Logo typography is protected artwork, including the correct original top-right logo. Source typefaces are resolved before transferring shapes to a different theme. Code uses its original font, exact text, blank lines and indentation; it is not converted to Arial or automatically rewrapped. The editor restricts marked logo/code objects to geometry changes. Independent artifact checks compare exact text and effective typefaces against the reopened source; whitespace normalization cannot hide damaged code. Screenshot QA still checks panel containment, legibility, logo spacing and line arrangement.

Required screenshot acceptance scenarios:

| Scenario | Expected decision and check | Primary owner |
| --- | --- | --- |
| Code displaced outside its panel | Preserve exact code and font; position it inside the associated panel; compare every rendered line to original. | Spatial layout for displacement; separate actual code corruption belongs to accuracy. |
| First page contains a miniature old cover | Identify cover, use the first-page template, remove obsolete non-content background, preserve native title/subtitle/author. The next render must contain no old-cover inset. | Wrong semantic type: structure; wrong template after correct type: branding; needless retained background: instruction compliance. Independent defects only. |
| Readable 2M composition unnecessarily shrunk | Keep an already compliant slide unchanged; otherwise adjust individual elements, retaining readable scale. The title is the heading, not the statistic. | Legibility for tiny text; structure for incorrect title role. |
| Original top-right logo changes font | Preserve original complete mark, including font, spacing, line arrangement and proportions. Compare original and output directly. | Brand consistency. |
| Thank-you slide wraps and artwork protrudes | Identify closing; preserve the compliant original. Keep the intended single-line title, photo crop and red-panel arrangement. | Layout for protrusion; legibility for degraded wrapping; no duplicate overdesign penalty. |

Each QA failure carries its affected slide/objects/region, original-versus-candidate evidence, smallest required correction, and acceptance condition. Those fields survive conversion to application findings and reach the targeted redesigner. Per-slide re-review and final ordered QA receive the acceptance checks again, alongside original and newly rendered output images. Structure errors can reopen source decisions, and decision repairs receive the bundled template screenshots even during final-QA repair. All slides are reviewed again; unchanged or worsened proposals are not promoted. An attempted repair is never evidence of success.

The release policy is `actionable-slide-decisions-qa-9`; prior approvals cannot certify a candidate against this version. Automated contract and synthetic artifact tests validate enforcement and repair routing; they do not prove that a live model will diagnose every real-world screenshot correctly.


Review context now includes the matching approved template screenshot as well as source/output pairs. Template image hashes are checked before final review. The bounding box of a full-slide picture containing a logo is not treated as the logo's own bounds; intentional background bleed is distinguished from visible mark clipping. Paired notes evidence explicitly supplies original, expected-on-this-output and actual output notes, including intentional omission of repeated notes on split continuations.

Source decisions and candidate role maps each receive at most one validation correction before editing. A malformed second response still blocks the pipeline, and retries count against the same call budget. Re-review does not bypass invalid IDs, roles, relationships, missing acceptance conditions or contradictory criterion verdicts.


The per-slide image order is ORIGINAL, matching APPROVED TEMPLATE reference, then FINAL CANDIDATE. The candidate is always last and explicitly labeled; reference example text is never treated as candidate content. Ordered deck QA labels every original/output pair and places template references before those pairs. A non-template cover may naturally wrap a long title when transferred into the required cover region at the approved size; this is distinct from unnecessarily rewrapping a kept matching slide or a short closing title.


## PDF redesign and cover photo placement

Text-based PDF uploads use the same redesign and paired QA workflow. Editable text is imported in page order; vector plots, images and other graphics are preserved as raster regions, not recreated with invented data. The original PDF page render remains QA's visual authority. Scanned pages require OCR first. Unsupported forms, annotations, attachments and link types must be explicitly resolved before import.

On covers, the title/subtitle/author go into first-page template regions. A single meaningful source photograph replaces the inherited campus photo, retaining aspect ratio and source bytes within the support area. A white matte can frame that photo; the old full-slide background is not pasted into the template. Cover master footer furniture is hidden when the source photo replaces campus art. QA distinguishes a photo from an old-cover screenshot and rejects unwanted decorative panels, source-photo/campus-photo stacking and an old-cover inset.

Timeout recovery permits one transport retry within the existing upload budget. Successful validated source decisions can be reused for an identical source, revision, provider configuration and policy; QA repair feedback bypasses that cache. If redesign does not complete, output QA is not run and verified release stays blocked. A timeout is an incomplete check, not a failed visual judgment.


Mandatory pass and spacing enforcement (policy 14 / rubric 9):

- `needs_review` is not a QA pass. Human approval cannot resolve any mandatory AI QA finding. Remaining deterministic warnings may be acknowledged only after all mandatory AI QA checks pass; deterministic blocking defects cannot be waived.
- Repair feedback includes per-slide AI findings, ordered-deck findings and deterministic structural blockers. Re-render the repaired candidate and review all slides again, paired with their originals and in order. Promote only an improved candidate without technical regression. Stalled repairs, provider failures or exhausted processing budget leave downloads inhibited.
- The first output slide must use the native `1_Title Slide` layout and contain extracted title text in its title region. Check this independently before any preserved-slide exemption. A failed or incomplete preview is not an approved redesign.
- Preserve small source text proportions during initial composition; do not apply a body-font floor to tightly positioned PDF lines. The planner must allocate box height and adjacent gaps together with font size. Reject newly introduced text-box collisions and worsening text-fit estimates before rendering. Existing collisions, contained text and math still require screenshot QA.
- Math QA checks symbols against the original, clear superscript/subscript and fraction spacing, annotation association, and readability. Unused space is a defect only when a better use of it is needed for legibility; intentional whitespace is allowed.


Cover correction (policy 15): keep all ordinary cover text, including bottom notes and metadata, in the right-hand text regions. The details region starts at x=7.75 to clear the sloping photo edge. Flow metadata using estimated wrapped-line heights and consistent spacing. A text-only source must not produce a blank source-page picture or contrast panel over the campus photo. All wording remains protected. PDF canvas dimensions use exact template EMUs; a maximum two-EMU rounding difference is allowed for unchanged native slides, while actual dimension mismatches return to the source decision stage before composition. This prevents the one-EMU PDF mismatch from aborting the pipeline before QA.
