# Project instructions

## Code style

Code is self-documenting: names carry intent. If a block needs prose to be
understood, rename or extract until it doesn't — a well-named variable or
method beats any comment.

## Code comments

Default is NO comment. Write one only when code does something for a
non-obvious reason and a competent reader would otherwise "clean it up" and
break it — then state that reason in one or two lines. Never narrate what
code does (the reader reads code), never describe history, prior approaches,
removed code, or spec section/amendment references. A comment must make
sense to a reader who has never seen any earlier version of the file.

Bad:  # Minimum fraction of an episode's span during which its gate was
      # above s_gate_off ... (spec 20 §1, A2a). With the close window
      # widened to hold_s, a chain of two-second pass-bys ... [8 lines]
Good: # Chained pass-by sweeps must not merge into a fake dwell now that
      # gap tolerance is as wide as hold_s.

Docstrings exist to document API surface — what a consumer of a public
module, class, or function needs to call it correctly. One line; parameters
or return described only when the signature doesn't already say it. Private
helpers and internals get no docstring (if lint demands one, adjust the lint
config, not the code). No essays, no design rationale, no algorithm
walkthroughs, no spec references. Moving banned comment content into a
docstring is a violation, not a workaround.

## Docs

- docs/spec/ is the authoritative design; each numbered doc owns its piece.
  Changes to behavior require the spec updated in the same change.
- Specs are declarative: they state what the software is, never its history
  or rollout state. No changelogs, no amendment markers, no
  "previously/was removed/replaced" phrasing, no build-phase narration, no
  "implemented/shipped/disabled until" status. Acceptance sections define
  what correct means; enablement decisions live in validation reports.
  Timeless rationale ("X because Y", where Y is still true) is welcome;
  anything dated belongs in git history.
- docs/spec/validation/ holds evidence reports; specs gate features on them.
  Reports are records and may reference what they measured.

## Layering

- custom_components/smart_ld2410/algo/ is pure Python: no homeassistant
  imports, no wall-clock reads; all time comes from Frame timestamps.
  Replay (custom_components/smart_ld2410/replay.py) must reproduce live
  behavior exactly.
- Storage is SQLite via store.py, all access off the event loop.

## Testing

Run the full suite with `uv run --group test pytest`; lint with
`uv run ruff check custom_components tests`. Both must be clean before
reporting done. Test function parameters are fully type-annotated with
concrete types.
