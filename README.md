# Timbre

Payment approval that verifies who is speaking from the acoustics of a voice,
not from whether a machine can understand the words.

Built for HackGT 13 (Georgia Tech, September 25 to 27, 2026).

## Status

In progress. Storefront, voice enrollment and verification, passkeys, and
Stripe test-mode payments work end to end; evaluation, voice shopping, and
adaptation are next (see the Handoff section of `AGENTS.md`).

## For coding agents

Read `AGENTS.md` first (start with its Handoff section). `CLAUDE.md` only imports it. Companion docs in `docs/`.

## For humans

- `AGENTS.md` for scope, constraints, architecture, commands, and the current handoff
- `docs/ALGORITHM.md` for the verification algorithm, data rules, payments, AI usage
- `docs/CONTEXT.md` for prior art, known issues, the demo script, and the glossary
- `docs/CHANGELOG.md` for every change made to this repository

## Credits and data

TORGO dysarthric speech corpus: Rudzicz et al., 2012. Audio is not redistributed
in this repository.

Product photos in `web/public/products/`: Open Food Facts contributors,
licensed CC BY-SA 3.0 (https://world.openfoodfacts.org). Prices in the demo
catalog are approximate and set by hand.
