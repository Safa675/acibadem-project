# Lessons Learned

## 2026-03-01

- When the user says cards still blend into the wallpaper, treat it as a layering bug first, not a naming/class consistency issue.
- Backdrop blur + medium-alpha fills can still show strong image detail; increase base opacity and reduce blur sampling before changing component structure.
- Validate against the user-provided screenshot baseline and tune global design tokens (`frost-canvas`, `frost-panel`, `frost-tooltip`) instead of patching per-component classes.
- If the user deprioritizes mobile, keep planning and delivery desktop-first and avoid spending cycles on responsive redesign in the current phase.
- When the user asks for information labels, default to implementation-ready metric glossary + placement mapping before visual refinements.

## 2026-03-07

- For RAM regressions, quantify each stage first, then enforce memory-first defaults (`env` flags + startup orchestration) while keeping API response shapes stable with explicit empty outputs.
