# Stevens & CPE presentation skill

This folder is a standalone plugin source package containing one skill and both original template assets. It has no dependency on the surrounding Slide Studio application. The skill can also be used separately from `skills/stevens-cpe-presentations/` in a host that supports standalone skills.

## Contents

- `plugin.json`: portable Agent Plugins manifest.
- `skills/stevens-cpe-presentations/SKILL.md`: redesign and generation workflow.
- `skills/stevens-cpe-presentations/assets/`: bundled Stevens PPTX and CPE POTX.
- `skills/stevens-cpe-presentations/references/templates.md`: layout roles and brand-specific placement guidance.
- `skills/stevens-cpe-presentations/scripts/template_tools.py`: optional standard-library inventory and template preparation helper.

The host supplies PowerPoint creation/editing and rendering capabilities. This package does not supply a slide-generation engine, install a renderer, make external AI calls, or claim the application’s preservation/QA guarantees. The helper requires Python 3.9+; the workflow may use equivalent host tools instead.

## ChatGPT distribution

The folder is prepared for packaging; it is not installed, published, or approved in ChatGPT. Use the supported plugin creation/import and sharing process available to the target account or workspace. A local folder or ZIP alone does not establish that others can install it on the website. Public directory distribution has its own submission/review requirements.

Official guidance checked when packaging:
- [Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Build plugins in ChatGPT](https://learn.chatgpt.com/docs/build-plugins)
- [Portable plugin manifests and packaging](https://developers.openai.com/plugins/build/plugins)

Before sharing, test the complete workflow in the intended ChatGPT environment. Confirm it can read bundled binary assets, preserve/import the template, export PPTX, and render slides. These capabilities are not proven by validating SKILL.md or the manifest.

## Acceptance scenarios

1. **New Stevens deck:** Request six total slides from a supplied factual outline. Check opening artwork, exact slide count, editable content, and accurate facts; include a closing only if it fits the requested narrative/count.
2. **CPE redesign:** Upload a deck with a table, chart, source notes, and links. Confirm correct CPE branding, no wording/data loss, and explicit disclosure of any unsupported preservation.
3. **Uploaded template:** Choose a third template. Confirm that its artwork and typography take precedence and neither bundled brand leaks into the result.
4. **Scanned PDF:** Redesign a page with equations and no text layer. Confirm faithful image-region handling and honest editability disclosure.
5. **Missing renderer:** Confirm that a valid export is labeled visually unverified rather than passed. If no PPTX creator exists, the skill should explain that limitation instead of claiming to produce a deck.
6. **Ambiguous input:** Supply multiple decks without specifying their roles. Confirm the skill asks which is the template/source; a clear request should proceed without unnecessary approval steps.

These are host acceptance scenarios, not claims of completed live ChatGPT testing.

## Local validation completed

The skill-creator validator passed. Both bundled assets match their originals byte for byte. The helper ran successfully from a temporary copy outside the repository: CPE exposes 13 layouts across four masters; Stevens exposes 23 layouts across one master. PPTX copying preserved the complete file, and POTX preparation changed only `[Content_Types].xml` while retaining every other package member's bytes. Existing-output protection, unchanged originals, malformed-file handling, local reference links, and manifest structure were also checked. Live ChatGPT installation, deck generation, and rendering remain untested.
