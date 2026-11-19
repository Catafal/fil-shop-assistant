# Fil evaluation v2

This diagnostic pilot checks a fictional shop. The eleven original scenarios were inspected during tuning and serve as development regressions. The repository also includes development and audio cases.

Research and source links are in [evaluation-research.md](evaluation-research.md).

## Evidence layers

- Local invariant and harness tests exercise deterministic failure modes without a provider.
- Native text trials exercise the actual agent and authenticated isolated inventory. Provider judge scores, objective checks and independent semantic review remain separate.
- PCM trials exercise the real speech transport and captured audio. Returned PCM and transcription do not establish physical speaker playback, microphone behavior, browser/WebRTC integration or naturalness.

A completed script is not a successful conversation. Missing required paths are `not_exercised`; insufficient semantic or persistent evidence is `uncertain`; forbidden writes fail even if rejected or later expired. Do not discard invalid attempts from the attempted-completion denominator.

## Reproduce local checks

```sh
make check
uv run python scripts/calibrate_graders.py --output /tmp/fil-calibration-new.json
```

The calibration corpus contains minimal positive and negative controls derived from observed failure modes. Its labels are model-authored and independently model-reviewed, not human gold. Agreement on these controls does not estimate semantic judge accuracy.

`case.grading.expected_criteria` constrains every successful search; `final_criteria` constrains only the final search after a deliberate preference change. Required typed result predicates distinguish missing values, `null`, zero and booleans. Positive informed consent remains subject to independent semantic review.

## Run tools against isolated inventory

Run `uv run python scripts/run_evaluation_backend.py --root <fresh-directory>` with a separate `FIL_EVALUATION_WEBHOOK_SECRET`. The evaluation backend exposes shop tools and stores each provider conversation in its own seeded database. Use explicit `--resume` to preserve an existing run's holds. This backend has no browser or voice-token routes. Point evaluation agents at the isolated backend to keep the demo's shared stock out of test runs.

For a model comparison, pass the same frozen `--fixture` to `provider_tests.py`. It records the source hash, materialized cases, calendar metadata, and materialized hash. Compare the same registered test IDs. Record whether the candidate can fall back to another model so you can attribute results to the model you intended to test.

## Native trial records

Create one immutable batch per attempt. `scripts/provider_tests.py` accepts `--repeat-count` (1–20), `--freeze`, and a frozen `--fixture`. A new batch can use `--from-manifest` and repeated `--case-id` selections to reuse already registered identical cases. Case metadata is removed before provider submission; shopper scenarios must not contain grading answers. A pending write blocks retry until reconciled.

The freeze identifies candidate, exact fixture, model, prompt, tools, voice, harness, simulator and grader. The coordinator verifies the current source/provider snapshots before submission; supplying a freeze file alone is not proof that a remote agent still matches it. Do not silently fall back to a different model.

Status snapshots preserve all returned rows and actual provider test-run IDs and credit usage. Expected case × repetition counts must match; duplicate, missing, extra or unfinished rows invalidate the matrix. Trial indices are a stable rank of provider run IDs within a case, not chronological execution order.

`grade_evaluation.py` consumes the frozen manifest, a result snapshot and the marked evaluation root. It joins returned quote IDs to the actual persisted conversation when native tests omit conversation IDs. No quote anchor means persistence remains unverified; a missing database is never created to manufacture a zero-reservation result. All historical reservations count, including expired holds.

## Audio trial records

The audio runner requires an explicit versioned case, evaluation agent, marked isolated root, and provision manifest containing verified provider snapshot hashes. Set `ELEVENLABS_AGENT_ID` to the live agent so the runner can reject that target. Each trial has a unique output directory and an unresolved-submission guard. Six case definitions cover language correction, overlap, closing, refusal, positive consent, and inventory failure.

Audio events distinguish receipt, virtual queueing, discard and response association. They never assert physical playback. Final spoken-content grading needs hash-bound transcription of the captured WAV; transcript text alone is insufficient. Review any interruption or incomplete closing rather than marking it successful because the socket closed. Backchannel, sentence-pause and background-speech behavior remain unexercised; the current runner rejects those case kinds rather than claiming that labeling an event tests the behavior. Audio-content presence and persistent business outcomes are graded separately; consent semantics still require review.

## Budget and reporting

The planned ceiling is 33 regression text trials (11 × 3), 30 heldout text trials (6 × 5), and 12 audio trials (6 × 2). This is a pilot design, not a power calculation or a promise that the included credits fund all 75. Read account usage before each small batch and stop before exceeding authorization. Preserve old failures and report every unrun matrix cell.

Report per-case counts, provider completion, objective outcomes, semantic uncertainty, critical policy violations, invalid harness attempts and remaining coverage. Any observed unauthorized reservation, fabricated tool outcome or silently relaxed critical constraint blocks demo acceptance. Remote CI and human/browser audio remain unverified until directly exercised.
