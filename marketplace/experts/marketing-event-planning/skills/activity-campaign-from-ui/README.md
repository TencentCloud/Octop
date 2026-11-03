# activity-campaign-from-ui

Current repository version: **0.6.0**

A reusable OpenClaw skill for turning campaign UI references into a **new H5/Web campaign plan and delivery-ready high-fidelity front-end draft**.

## What this skill does
Given campaign screenshots, poster-like activity pages, or design references, this skill can:
- analyze the reference UI
- abstract the gameplay and module patterns
- propose a **new** campaign instead of copying the reference
- design a page/module architecture
- output visual-first draft code for **H5/Web only**

## Fixed platform and stack
This skill is intentionally strict.

- Platform: **H5 / Web**
- Stack: **HTML + CSS + JavaScript**

If the user asks for any other stack, this skill should still stay on the fixed stack above.

## Modes
This skill supports one skill with multiple modes:

- `analysis` — analyze the reference UI only
- `proposal` — generate a new campaign proposal from the reference
- `architecture` — output page modules, states, popups, and data structure
- `delivery` — output H5/Web high-fidelity draft files in HTML/CSS/JS
- `full` — do the full flow from analysis to delivery

If the user does not specify a mode:
- default to `proposal` when they want a new event idea
- default to `delivery` when they ask for code
- default to `full` when they want both planning and code

## Best for
- holiday event pages
- lucky draw / lottery campaigns
- task + reward campaigns
- promotional landing pages
- mobile-first H5 campaign pages
- poster-style marketing pages

## Typical inputs
- screenshots of activity pages
- multiple campaign references
- poster-like event images
- design previews or accessible design links
- user notes about target users, rewards, and campaign goals

## Typical outputs
- reference analysis
- gameplay abstraction
- new campaign proposal
- page architecture
- config/schema suggestions, including activity factory, animation system, and asset output contract
- visual direction summary
- H5/Web high-fidelity draft code (`index.html`, `styles.css`, `main.js`, `mock-data.js`)

## Boundaries
This skill should not:
- produce code in other stacks
- pretend blurry text is exact
- claim hidden states or backend logic that are not visible
- directly copy the reference page

## Visual quality bar
For `delivery` and `full`, the expected result is a **launch-ready-feeling H5 front-end draft**, not a plain wireframe, demo shell, or generic starter.

Strong outputs should:
- summarize the screenshot's visual language before code
- decide whether the screenshot's colors actually fit the new campaign theme before reusing them
- render a believable first screen with nested hero/module markup
- use gradients, decorative wrappers, chips, badges, and stronger CTA styling when the reference implies them
- avoid repetitive white-card scaffolding unless the user explicitly asks for minimal output

If the reference theme conflicts with the requested campaign theme, keep the structural ideas but rebuild the palette and decorative language around the requested theme.
Example: a Spring Festival red-gold reference used for a Dragon Boat Festival brief should usually become a green or blue-green Dragon Boat style page rather than a red reskin.

## Additional delivery defaults
For `delivery` and `full`:
- aim for a launch-ready H5 front-end draft feel rather than a starter shell or wireframe
- use an adult female character-led first screen when the brief or reference clearly depends on poster-style human visual focus
- keep the female hero styling theme-matched, including wardrobe, dominant colors, props, and accessories
- for Spring Festival directions, default the female hero styling toward a red-dominant festive look with gold details rather than a generic modern outfit
- allow glamorous and slightly sexy commercial-fashion styling, while keeping the result suitable for a public-facing campaign page
- prefer tab-first mobile layouts when the page would otherwise become too long
- when the first screen is poster-led, default to generating a hero image asset that the project references as `./image/bg.png`
- push the generated hero toward photorealistic commercial-poster quality with natural skin, hands, hair, lighting, and fabric detail instead of an illustration-like or plastic result
- keep that generated image focused on the woman and theme atmosphere rather than copying prize modules, invitation boards, or lower-page UI from the references
- treat the reference as style input, not as an identity template: generate a new woman rather than recreating the same face or pose
- keep `./image/bg.png` as the top-most first-screen visual, with summary strips, tabs, and lower modules following beneath it
- when image generation is required for the brief, generate the asset for `./image/bg.png` before the front-end files rather than only mentioning it in code
- default to `regenerate_each_run`; reuse an existing hero image only when the user explicitly asks to reuse it
- if the host exposes a concrete tool such as `image_generate`, call it directly
- if image generation is unavailable for an image-required brief, stop and report the run as blocked instead of downgrading to placeholders
- place all final generated files under the current execution environment's `project/` directory and create it automatically if missing
- wrap each delivery in one extra bundle layer such as `project/<delivery-slug>/index.html` rather than writing files directly under `project/`
- create `project/<delivery-slug>/image/` for image assets and include an explicit handoff note telling the user to rename the generated image to `bg.png` and place it there
- when the brief does not pin the activity type, generate a new configurable activity family instead of only repeating the reference mechanic
- for festive or reward-led pages, add one signature interaction animation plus supporting ambient motion so the result feels closer to an online activity page
- this higher quality bar means production-like front-end finish, not a fully backend-connected deployment

## Local artifact generation
- in `proposal`, the result should feel closer to an operations campaign visual deck than a plain strategy memo
- if the user explicitly asks for a local visual deck and the host environment supports local execution, Python should generate `project/<delivery-slug>/campaign-proposal.pptx`
- in `delivery` and `full`, if the user explicitly asks for local front-end files and the host environment supports local execution, Python should write `project/<delivery-slug>/index.html`, `project/<delivery-slug>/styles.css`, `project/<delivery-slug>/main.js`, and `project/<delivery-slug>/mock-data.js`
- treat the current execution environment's `project/` directory as the mandatory top-level output root and create it automatically if it does not exist
- create an additional bundle directory `project/<delivery-slug>/` automatically and place all final artifacts there
- when Python writes local output, it must create `project/<delivery-slug>/image/` first and save the generated hero asset to `project/<delivery-slug>/image/bg.png`
- when local output was requested, the run should actually write the files and report the written paths instead of only showing file structure or code blocks
- even when local artifacts are generated, do not output shell file-write commands in the response; report the created file paths instead

## Repository structure
- `SKILL.md` — main skill rules
- `agents/openai.yaml` — UI metadata for marketplaces and skill pickers
- `.editorconfig` — shared formatting rules for contributors
- `VERSION` — current repository version
- `LICENSE` — repository license
- `CODEOWNERS` — repository ownership template
- `CHANGELOG.md` — repository change history
- `RELEASE.md` — versioning and release policy
- `RELEASE-CHECKLIST.md` — final publishing checklist
- `CONTRIBUTING.md` — contribution and maintenance rules
- `references/scope.md` — scope and non-goals
- `examples/input-example.md` — input examples
- `examples/output-example.md` — output example
- `examples/spring-festival-case.md` — concrete case guidance
- `examples/campaign-schema-example.json` — example campaign delivery schema
- `examples/mode-analysis-example.md` — analysis mode example
- `examples/mode-proposal-example.md` — proposal mode example
- `examples/mode-architecture-example.md` — architecture mode example
- `examples/mode-delivery-example.md` — delivery mode example
- `examples/full-delivery-example.md` — full mode end-to-end example
