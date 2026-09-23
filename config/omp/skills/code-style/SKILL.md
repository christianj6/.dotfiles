---
name: code-style
description: Christian's code style charter — abstraction-forward, minimal, clean code with solid design principles. Read before writing, refactoring, or reviewing non-trivial code.
---

# Code style charter

Design for the session after this one. Complexity must buy leverage.

## Principles
- **Abstract deliberately, early.** Clean abstractions with stable seams are how future sessions work at higher levels while relying on what earlier agents built. When a concept earns a name, give it an interface — even before the second use.
- **Anchor abstraction in one concrete case.** Implement the general shape against a real use; generality with no anchor drifts into fiction.
- **Overengineering is abstraction without leverage.** Knobs nobody turns, layers that pass data through unchanged, config surface before need — these are the failure mode, not abstraction itself.
- **Smallest correct change at each level; cleanest seam between levels.** No speculative generality in behavior, no "while we're here" scope.
- **Delete weightless code.** Unused params, defensive checks for impossible states, wrappers that add a name but not meaning — remove them.
- **Boring over clever within a layer; bold at the boundaries.** The obvious construct inside a module; the considered interface at its edge.
- **Single responsibility.** A function does one thing at one level of abstraction. Long is fine; mixed levels is not.
- **Explicit over implicit.** Data flow visible at the callsite beats magic via globals, reflection, or side-effecting constructors.
- **Errors are surfaced, not swallowed.** Fix causes; never suppress an exception/warning or special-case inputs to hide a failure path.
- **Match the file.** Existing conventions win over personal taste; never put a second convention beside an existing one.
- **Clean cutover.** No shims, aliases, deprecated paths, stubs, or `TODO: implement` — migrate every caller and delete the old path.
- **Names carry the design.** A name that needs a comment to be understood is the wrong name.

## Tests
- Tests defend observable behavior: boundaries, invariants, transitions, real error paths — not plumbing or incidental defaults.
- Deterministic and isolated; a test that depends on ordering or wall-clock time is a bug.

## Comments
- Explain why (constraint, tradeoff, non-obvious invariant), never what the code obviously does.
