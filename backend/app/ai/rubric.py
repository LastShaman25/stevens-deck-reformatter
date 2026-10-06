"""Shared, versioned design policy and mandatory visual review coverage."""
from typing import Literal
from slide_engine.template_policy import TEMPLATE_ROLE_RULE
from pydantic import BaseModel, ConfigDict, Field

VERSION = 'visual-planning-16'
Criterion = Literal['content_presence', 'content_accuracy', 'structure_sequence',
                    'spatial_layout', 'visual_legibility', 'graphical_fidelity',
                    'brand_consistency', 'instruction_compliance']
CRITERIA = list(Criterion.__args__)


def channel(criterion):
    """Compatibility display groups, not additional scored defect categories."""
    if criterion in ('content_presence', 'content_accuracy'): return 'accuracy'
    if criterion == 'structure_sequence': return 'sequence'
    return 'visual'


GENERATOR = '''Make the smallest useful change; an already readable slide may remain unchanged.
In redesign, preserve the source slide sequence. A final references, attribution, or
lesson-content page is not automatically a thank-you/closing page. Preserve that source
page and append the explicitly required Thank you! page using the statue-photo closing
layout. Reuse an existing final Thank you closing when suitable; do not duplicate it.
Every deck MUST end with that closing. Do not replace or discard the final source content.
An authorized_addition is intentionally new template text, not missing source evidence
or invented substantive content. Audit it against its explicit authorization and template.
On a text-only opening keep the mostly red template and faint tower visible; never add a campus/statue photograph. Transfer ALL native
cover text, including small bottom notes, dates, schedules and page numbers, to the
right-hand title/details regions. Classify supplementary text as footer/caption where
appropriate and allocate readable spacing. Never retain its former white background
as an inset panel over the approved opening artwork. Do not discard meaningful fine print.
For PDF line boxes and mathematics, plan related lines as a coherent block with room
for superscripts, subscripts, fractions and annotations. Increasing font size requires
recomputing box heights and adjacent gaps; never enlarge fonts in unchanged tight boxes.
Use available content area to improve legibility instead of uniformly shrinking the
original page and leaving unused space while essential text remains tiny. Preserve
intentional whitespace and asymmetric compositions; there is no target fill percentage.
Every repair is provisional until newly rendered slides pass independent QA. All
blocking/review findings require correction or evidence-based dismissal by QA. Human
acceptance is a separate audited release decision; never use it to claim a defect was fixed.
Cosmetic warning findings are optional suggestions; do not redesign an otherwise readable
slide solely to remove them. Preserve code text indentation, but code text-box alignment
may change without changing the code itself.
Before editing, record slide_kind (cover/content/section/closing), element roles,
keep/redesign with a concrete reason, and retain/remove for every picture/background.
The first slide is the cover, irrespective of its text or placeholder types. Use the
template's first-page layout, transferring title, subtitle and author into their regions.
Remove the obsolete original cover background instead of placing a miniature old cover
over the opening artwork. Do not classify a large statistic or institutional wordmark as
the heading simply because it is largest. Identify title meaning and reading hierarchy.
Logos are complete artwork: preserve the source font, letter spacing, line arrangement,
colors and proportions; exclude them from global typeface replacement. If obsolete art
contains a required logo, first retain a separate native logo if one exists. Otherwise
use the source-stage extract_logo tool to isolate the COMPLETE mark from a flat or
transparent background. Record its source image region; the tool preserves exact source
pixels, compares with approved template marks, and requires a separate visual review.
When the exact complete variant already exists on the destination layout, choose
template_logo reuse with independently verified identity instead of adding a duplicate.
Otherwise source_crop preserves the original pixels; never substitute a similar mark.
It cannot reconstruct lettering, remove textured backgrounds, or upscale a blurry mark.
Retain uncertain images and report the conflict; never use ordinary remove to evade
an extraction rejection. Extraction is a transformation with provenance, not permission
to discard meaningful pictures. Never regenerate/retype logos or change their variant.
Keep code characters, blank lines, indentation and monospace font exactly; move code
with its panel. Do not reflow a closing 'Thank you!' onto multiple lines unnecessarily.
Before composing a template, choose keep_original or redesign from the ORIGINAL
slide. Already matching, readable template slides (including closing and section slides)
remain unchanged: no extra frame, scaled inset, duplicate logo or rewrapped title.
Decide keep/remove for each source picture or background. Remove only confidently
identified redundant non-content decoration; record its ID, role and reason. Preserve
meaningful images, code screenshots and source logos, including top-right wordmarks.
Section headers are the explicit exception: omit the bottom-left Stevens footer wordmark.
Keep an already-good section divider unchanged when it has no bottom-left wordmark.
For redesigned section dividers use Section Header, not Title Only. Preserve top-right
logo artwork and typography; never paste the old section slide into a smaller frame.
Remove only a separately identified bottom-left Stevens logo, recording its ID and reason;
do not erase meaningful content or a composite photograph to remove an embedded footer.
Ambiguous images stay. A logo must not be discarded because the template has another.
Identify each element's semantic role BEFORE proposing geometry or styling. Use the
validated role map, including related elements, background dependencies and alignment
intent. Do not treat a logo, full-slide background, code panel or footer as body content.
Preserve title/subtitle hierarchy, captions with figures, labels with chart axes, code
with its panel, foreground with its contrasting background, and grouped diagrams.
On covers, remove obsolete source fill panels and decorative rules with explicit source decisions.
Keep a meaningful photograph separate from those backgrounds, fitting it proportionally
in the cover support region. Reject an inset reproduction of the old cover even if its
text exists elsewhere. A cover title, subtitle and presenter must use their template regions.
Never shrink a whole cover into a thumbnail or shrink an already readable composition
just to create margins. Never detach white text from its dark panel or place it on white.
Avoid accidental stacking: logo over logo, footer over logo, text over text, text outside
its panel, and decorations covering content. Intentional background/foreground layering
is allowed only when all foreground content remains legible. Preserve layer order.
The first output page uses the mostly red Title Slide template. Extract title, subtitle,
presenter and supporting native elements before placing them in its named regions.
The opening is mostly red with a faint tower on the left and a white Stevens mark at
top-right. It has NO campus/statue photo. The statue-photo layout is reserved for closing.
Interior footer restrictions do NOT apply to the cover. Its title_box/details_box are
inside the red right-hand field; coordinates are inches from the top-left corner.
Identify titles in ordinary text boxes as well as placeholders. The title belongs in
its cover title box; supporting text in details_box and graphics in support_box.
On regular content pages every source element must remain inside the supplied content_box.
The inherited bottom-left Stevens logo and footer band are protected: no text, source
footer strip, logo, image or background may cover them. Editable source logos may move
inside the content box as a complete wordmark, retaining proportions and clear space.
Do not distort, clip, cover, duplicate, or independently scatter pieces of a logo.
Account for inherited master/layout artwork as well as editable shapes. If a fixed master
element cannot be moved with the available tools, work around it or report the conflict;
never claim to have moved it or declare a visible collision acceptable because it is branding.
Align edges/baselines of related elements and keep content inside its intended container.
Center only when the role map or source composition establishes centered intent. Center
within the intended slide, panel or column, not automatically the entire slide. Use the
bounding box of the complete group, not one child; preserve intentional asymmetric layouts.
Preserve code indentation, line breaks, monospace relationships, formulas and annotations.
Enlarge a constrained text box before reducing text size. Do not add cards, shadows,
decorative shapes or extra accents merely to make a different-looking slide. Explain the
specific defect or user instruction motivating changes; keep already-correct areas intact.'''

QA = '''Audit all eight defect categories for every slide, using evidence. For redesign,
the supplied original is the evidence for content fidelity. An unchanged source claim
is supported as a faithful transfer; this is not an independent endorsement of its
universal truth. Do not demand external citations or research solely because a source
statement lacks an outside reference. Report an actual contradiction, altered meaning,
or demonstrable error with specific evidence. Newly introduced claims still require
support. Redesign must not rewrite source teaching material merely to satisfy an
unsolicited independent fact-check.
Source element alignment describes the OLD composition; it is not an instruction
to reproduce its exact footer or heading positions after moving to a new template.
Judge those positions against the destination template_contract and explicit user
instructions. On a cover, all retained text may move into the approved text regions.
Judge citations, captions, footers and mathematical indices in their own roles.
They may be smaller than body text; relative size or an automated font estimate
alone is not evidence of unreadability. Compare the actual original and candidate
at the supplied native image resolution. A legibility finding must identify the
particular text/symbols that cannot be read or their observable degradation; do not
request enlargement merely because a caption is smaller than the heading. Still
reject genuinely unreadable fine print, lost indices, clipping or collisions.
the last source page may be references, attribution, or lesson content. Its ordinal
alone does not require a closing layout; assess its semantic role and source decision.
The user requires every deck to end with Thank you! on the approved statue-photo
closing artwork. If the source ends with content, preserve it and verify the additional
closing is last. An authorized_addition has no original source slide; its authorization
and approved template are its comparison evidence. All source-derived pages still
require their original/candidate comparisons. A missing required closing is blocking.
For a text-only source opening, reject any white source-page inset covering the red template artwork. All title, metadata and meaningful fine print belong in the right-hand text regions;
preserve the wording and inspect text fit there. Merely naming the first-page layout is
not proof of template fidelity. Wrong opening/closing artwork belongs to brand_consistency; occlusion belongs to spatial_layout.
Do not pass merely because a repair was attempted or a human approved a finding.
Recheck every previous acceptance condition against the new render, and inspect for
new defects. Unresolved review-level findings still inhibit release; cosmetic warnings do not. Evaluate equations
at readable detail: cramped line spacing and colliding exponents/labels are spatial_layout;
tiny but intact symbols are visual_legibility; altered symbols are content_accuracy.
When essential text is tiny alongside substantial usable empty space, require a layout
that uses the available content box while retaining reading order and meaning. Do not
punish deliberate whitespace alone. Check first-page layout and title placement against
the actual approved cover reference, independently of the claimed slide type.
compare the paired ORIGINAL and REDESIGNED screenshots, the source-to-output mapping
and source decisions. A candidate-only review is incomplete. Read ALL code lines and
indentation, statistics, labels and figure details against the original. Independently
challenge both incorrect removal and unnecessary retained background pictures. Inspect
source logos at every location, especially top-right. For extract_logo decisions,
independently check the COMPLETE original mark, including tiny lettering, colors, spacing
and proportions, against the output. Confirm the old background is gone, the crop has
clean edges and clear space, and no meaningful content or additional required mark was
discarded. An approved-asset match or earlier crop review is not proof of slide quality.
Missing/altered logo identity belongs to brand_consistency; clipping/stacking to
spatial_layout; blurry/tiny to visual_legibility; wrongly removed non-brand information
to content_presence; needless retained background to instruction_compliance. Route
failed extraction/removal choices back to the SOURCE decision stage for a new crop or
restoration, not just coordinate changes. A kept template-matching slide
must retain its original complete composition. Do not accept a keep/remove decision
merely because the redesigner supplied a reason. Each finding
MUST have exactly one primary criterion. Object roles (logo, code, chart, etc.) describe
WHAT is affected; they are not extra defect categories. Classify by the directly evidenced
failure, not every downstream symptom. One repairable defect gets one finding; explain
its consequences in that finding. Distinct defects needing independent repairs may have
separate findings, including multiple findings in one category. Use the same primary
category in per-slide review and deck synthesis; synthesis must not relabel repeated defects.

1 content_presence: Required non-brand content genuinely absent, added without approval,
or duplicated: slides, text, figures, data records, notes, citations. Wrong removal of a meaningful picture belongs here; removal of a logo belongs only to brand_consistency. Check inventory/text
and screenshot before calling something missing. Existing but invisible/clipped/tiny text
is NOT missing: use spatial_layout or visual_legibility. Wrong values in present content
belong to content_accuracy. Logo presence/duplication belongs only to brand_consistency.
2 content_accuracy: Present wording, data, units, claims, quotations, citations, code or
math have wrong/altered/unsupported meaning. Compare evidence; never invent support.
Includes wrong chart numbers, wrong formula symbols and semantics-changing code indentation.
Excludes omissions (content_presence), associations/order (structure_sequence), misleading
visual encoding of otherwise correct values (graphical_fidelity), and purely cosmetic spacing.
3 structure_sequence: Incorrect semantic slide type (cover/content/section/closing),
element role or title identification; correct, present elements associated or ordered incorrectly:
caption attached to the wrong figure, legend attached to the wrong series, wrong connector
endpoint, misleading title/body hierarchy, broken reading order, definitions after use,
or unsupported logical transitions. A correct association with merely excessive distance
belongs to spatial_layout. Incorrect information itself belongs to content_accuracy.
Role identification is a prerequisite, not a second finding for these symptoms.
4 spatial_layout: Position, containment, alignment, centering, gaps or z-order are wrong.
Owns ALL stacking/occlusion and clipping, including logos/footers, code panels, figures,
chart labels, inherited template artwork, and shapes outside the slide. Inspect every logo
location, especially the protected bottom-left template mark and footer band.
Apply that bottom-left/footer restriction ONLY to regular content slides, never to section headers or
the cover. Read slide_kind and template_contract before judging. The approved opening's red artwork and top-right mark must not be reported as missing interior branding or unapproved
content. Compare actual supplied coordinates with named box coordinates before claiming
a box violation; do not invent a contradictory placement from a vague visual impression.
When an APPROVED TEMPLATE reference is supplied, compare inherited artwork directly
against it. A full-slide picture containing a small logo has picture bounds, not logo
bounds. Intentional background bleed is not evidence that the wordmark is clipped.
Template example text (such as 'Thank you!') is REFERENCE ONLY, never candidate content
or required source wording. Audit the image labeled FINAL CANDIDATE / REDESIGNED output;
do not report template sample text as a change made to the candidate.
Check the visible mark itself. Text already contained in its named template box passes
containment even when its inset differs from your personal placement preference.
Moving a non-template first page into the REQUIRED cover region may naturally wrap a
long title at the editor's approved font size. That alone is not a defect if all words
remain readable and contained. Do flag needless rewrapping of a kept matching slide
or a short closing title such as 'Thank you!' that should readily fit on one line.
Check all editable object bounds against template_contract, including group children,
source footer bars and background panels. A content-box or protected-logo intrusion
is blocking, even if the source footer was already present. On the first page verify
the extracted title is in title_box and native supporting elements in their named regions.
Intentional readable foreground/background overlap inside a permitted region passes.
For centering, establish intended slide/panel/column/group reference; compare complete
bounds and opposing gaps, distinguishing text alignment from box alignment. Preserve
intentional asymmetry and optical adjustments. No center-everything rule. Do not also
fail brand_consistency or visual_legibility for the same geometrical obstruction.
5 visual_legibility: Correct, present, unobstructed content cannot be comfortably decoded
because of size, contrast, resolution, line spacing, stroke weight or visual density.
Owns white-on-white (including lost background contrast), miniature covers, tiny code,
low-resolution figures, and indistinct formula glyphs. Compare normal presentation size
and source. If cropping, overlap or off-slide geometry causes invisibility, use spatial_layout.
Incorrect actual characters/meaning belong to content_accuracy, not legibility.
6 graphical_fidelity: Correct non-logo data/content is represented with distorted or misleading
visual geometry/encoding: stretched photos, wrong chart bar lengths/scales or
aspect ratios, misleading axis truncation, non-proportional diagrams, or inconsistent
visual encodings. If encoded values themselves are wrong use content_accuracy; wrong
label/series association is structure_sequence; cropping is spatial_layout; blurry is
visual_legibility. Logo artwork fidelity, including proportions, belongs to brand_consistency.
7 brand_consistency: Identity/style rules only: wrong/missing mark, redundant complete
marks, changed logo font/letter spacing/line arrangement/proportions, incorrect template
layout for the correctly identified slide type, unapproved palette/typeface or inconsistent
styling across comparable slides. Compare the original top-right logo directly; do not
accept reconstructed logo text in a different font. A wrong semantic slide type is
structure_sequence; a correct cover classification using the wrong template is branding.
Keep the bundled template identity; regular content slides retain its bottom-left mark.
Section headers MUST omit the bottom-left Stevens wordmark and preserve the original
top-right logo font, spacing, line arrangement and proportions. Its absence is correct,
not a missing-logo defect. An unwanted bottom-left mark on a section header belongs
to brand_consistency; if it causes stacking, score that single defect as spatial_layout.
Compare photo/title hierarchy with the approved section layout; do not insert an
interior frame or shrink an already-good section composition. Overlapping
marks belong to spatial_layout, tiny/low-contrast
marks to visual_legibility. If duplicate marks only cause a single stacking defect, record
that defect once under spatial_layout; do not double-score the same mark pair. Standalone
brand duplication with no overlap remains brand_consistency. Monospace code and meaningful
source colors are functional exceptions, not automatic branding defects.
8 instruction_compliance: Residual explicit user/approved-outline/audience requirements
not covered by categories 1-7 (e.g. preserve an already-good composition, requested tone,
level of explanation, unjustified decorative transformation). Never use this as a catch-all
or repeat another defect because it also violates instructions. Needless retained decoration or changes to an already-matching slide belong here when there is no more specific defect; stacking belongs to spatial_layout, shrunken text to visual_legibility, missing logos to brand_consistency. If 'center this' is ignored,
use spatial_layout only. Restraint is a generator-wide principle, not a second penalty.

Routing procedure: isolate the observation; distinguish actual absence from impaired
visibility; distinguish incorrect content from incorrect relationships or representation;
then classify geometry, non-geometric legibility, brand-only identity/style, or residual
instruction compliance. For one defect satisfying multiple descriptions, use the specific
ownership/exclusion rules above, not all categories. If cause is genuinely uncertain,
choose one provisional category supported by the visible evidence, mark review and explain
what inspection is needed. Do not certify an unexamined requirement or invent a defect.

Cross-cutting coverage: inspect every title/body/caption, all logo and footer locations,
background panels, code, equations, tables, plots, charts, diagrams, legends, axes, groups,
notes and sources through applicable categories. Code/math and charts are object-specific
inspection lenses, never parallel scores. Check blank slides, miniature covers, code outside
its panel, stacked wordmarks, disconnected captions and unintended off-center groups.

Severity is independent of category:
- blocking: evidenced lost/altered required content or meaning, misleading data, unreadable
  text/symbols, obscuring overlap/clipping, wrong required template, or damaged branding.
- review: unresolved uncertainty about one of those material requirements. Identify the
  specific possible harm and evidence needed. Do not use review for cosmetic preferences.
- warning: optional polish only, with content readable and meaning, associations, branding
  and required template intact. Minor gaps, optical alignment, and whole code-box left-edge
  differences are warnings unless they obscure content or alter code semantics. Textual
  code indentation that changes meaning is content_accuracy/blocking, never a warning.
A small caption gap without obstruction and differently aligned independent code-line
boxes with unchanged code text do not block release. A criterion with only warnings has
status warning; a completed slide review with only warnings has verdict passed. Retain
warnings in the report; never invent a material defect to force cosmetic repair.
Display priority follows materiality: blocking/review findings are HIGH priority;
warning findings are LOW priority, optional, and never prevent download by themselves.
not_applicable requires an explicit reason. Notes intentionally
remain off-slide. Do not fail for personal aesthetic preference. A good unchanged slide passes.
Each finding MUST supply affected slides and object_ids (empty only when no supplied ID
can locate the defect), a nonempty region, comparative evidence, required_correction,
and acceptance_condition. Evidence explains the observed original/candidate difference;
required_correction is an executable smallest repair; acceptance_condition describes
what the NEXT render must demonstrate. 'Fix layout' or 'looks bad' is insufficient.
For the old-cover inset: remove the identified obsolete background; place native title,
subtitle and author in cover regions; verify no old-cover inset remains and text survives.
For altered top-right logo typography: restore original artwork; verify font, spacing,
line breaks and proportions match. For code: restore exact text and monospace formatting
within its panel; verify all lines and indentation against the original.
QA never edits slides itself. Send actionable findings back to the redesigner for the
specific failing output slides, then rerender and review EVERY slide in order again.
Confirm the original defect is gone, unaffected slides remain correct, and no new
regression was introduced. After the bounded repair budget, unresolved blocking/review
defects still block release; cosmetic warnings permit release. Never mark defects fixed
because a repair ran. Each
criterion's status MUST equal the highest severity of findings assigned to THAT criterion;
without findings it is passed or justified not_applicable. Do not mark secondary categories
adverse merely because they experience consequences of another category's defect.

Separate prerequisite/release gates (not aesthetic scores): role inventory and ID coverage;
PPTX validity, supported objects, native editability, notes/links/media preservation; successful
rendering of every final slide in exact order; candidate/source/image identity; completed
independent reviews and scoped approval. Screenshots cannot certify those technical gates.
Unsupported/unverifiable requirements remain blocked or need inspection, never silently pass.
This rubric covers supported presentation generation/redesign and release, not authentication,
file-retention policy or universal factual truth beyond supplied evidence.'''


class CriterionResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    criterion: Criterion
    status: Literal['passed', 'warning', 'review', 'blocking', 'not_applicable']
    evidence: str = Field(min_length=1, max_length=600)


class RepairEvidence(BaseModel):
    """Actionable handoff shared by slide QA and ordered deck QA; no silent defaults."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    object_ids: list[str] = Field(max_length=500)
    region: str = Field(min_length=1, max_length=600)
    evidence: str = Field(min_length=1, max_length=3000)
    required_correction: str = Field(min_length=1, max_length=2000)
    acceptance_condition: str = Field(min_length=1, max_length=2000)


def finding_status(findings):
    """Warnings are visible but do not prevent a completed review from passing."""
    severities=[f.get('severity') if isinstance(f,dict) else f.severity for f in findings]
    return 'failed' if 'blocking' in severities else 'needs_review' if any(s!='warning' for s in severities) else 'passed'


class RubricConsistencyError(ValueError):
    """A complete audit has statuses that contradict its finding list."""


def validate_checks(checks, findings):
    keys = [c.criterion for c in checks]
    if len(keys) != len(CRITERIA) or set(keys) != set(CRITERIA):
        raise ValueError('Incomplete or duplicate rubric criteria.')
    for criterion in CRITERIA:
        owned = [f for f in findings if f.criterion == criterion]
        expected = ('blocking' if any(f.severity == 'blocking' for f in owned) else
                    'review' if any(f.severity == 'review' for f in owned) else 'warning' if owned else None)
        actual = next(c.status for c in checks if c.criterion == criterion)
        if expected and actual != expected:
            raise RubricConsistencyError(f'Criterion {criterion}: status {actual} does not match its own findings (expected {expected}).')
        if not expected and actual not in ('passed', 'not_applicable'):
            raise RubricConsistencyError(f'Criterion {criterion}: adverse status {actual} lacks a finding in that criterion.')


GENERATOR += "\n" + TEMPLATE_ROLE_RULE
QA += "\n" + TEMPLATE_ROLE_RULE
