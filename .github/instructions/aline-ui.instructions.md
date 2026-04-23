---
description: "Use when editing ALine PySide6/qfluentwidgets UI, dialogs, pages, project tree, extension panels, or UI tests. Covers Fluent layout metrics, theme helpers, focus commit, tooltip behavior, notification parenting, and narrow UI regression testing."
applyTo: "ui/**/*.py, tests/test_ui.py"
---

# ALine UI Constraints

- Prefer qfluentwidgets widgets plus shared helpers from `ui/theme.py` before adding new styling. Reuse `make_section_label`, `make_hint_label`, `make_card_caption`, `apply_button_metrics`, `WORKBENCH_*`, and `preview_canvas_*_color()` where possible.
- Avoid raw hex colors in UI code unless the value is first promoted into a shared helper in `ui/theme.py`. Secondary/helper text should use `secondary_color()` or `placeholder_color()`, not literal `gray`.
- Main workbench pages should keep the current spacing baseline: 12px outer margins, 10px main spacing, and card inner margins around 14px.
- Compact action `ToolButton`s should be square and use `WORKBENCH_BUTTON_HEIGHT` for both width and height.
- Keep descriptions close to the control they explain. If a gray `CaptionLabel` under a selector is enough, do not add a dedicated section block just for the description.
- For editable inputs, commit on `editingFinished` or install `install_click_away_focus_commit(...)`. Do not wire expensive updates to `textChanged` unless live preview is explicitly required.
- Tree/list hover tips must use Fluent tooltip mechanisms such as `ToolTip` and `ToolTipFilter`; do not try to restyle widget-level `QToolTip` selectors to fake Fluent behavior.
- User-facing `InfoBar` and similar notifications should prefer the top-level window as parent when triggered from embedded panels or child widgets, so feedback appears in the main window context.
- ProjectTree defaults should expand the project root only to first-level business groups on first build; deeper nodes stay collapsed unless an existing expansion state is being restored. Do not re-enable double-click inline rename.
- When rebuilding ProcessPage or AnalysisPage selected lists, block signals and restore both selected items and current item.
- Any UI behavior change should add the narrowest matching regression in `tests/test_ui.py`, and validation should prefer individual pytest nodes because batched qfluentwidgets page tests can fail from theme lifecycle timing rather than real regressions.
