# Fil evaluation methodology: research and proposed protocol

Research artifact, 6 November 2026. No new provider tests, product changes or execution budget are authorized by this document. This is a synthesis of published evaluation practice adapted to Fil, not a claim to know any lab's private process. Proposed sample sizes below are pragmatic starting budgets, not statistical certification.

## What the current evidence supports

The repository has eleven authored scenario templates, isolated real inventory, actual tool/state checks, native evaluator verdicts and independent model-agent transcript review. The repaired DeepSeek candidate completed all eleven templates successfully in one retained native run. Those templates were inspected repeatedly while changing prompts/configuration: they are development/regression cases, not an untouched test set. A subagent's review is useful independent scrutiny, but it is not human annotation or evidence of human/judge agreement.

Both the simulator and evaluator in `agent/test-cases.json` use Gemini3.5Flash. Keeping them fixed controls one source of variation between candidates, but no calibration establishes that their scenario behavior or grading is unbiased across candidate models. Exact scripted acknowledgments and fixed product names narrow coverage. They can test a particular consent boundary well while missing natural alternatives.

The two real PCM probes establish a useful component integration: synthetic speech enters ASR, the agent calls live tools, and Ona produces recoverable spoken output. The clean replay demonstrates English/Catalan/Spanish/English and correct final shopping state with zero holds after refusal. The first run has a harness race and an observed language mismatch under overlapping input. Both received audio artifacts truncate the closing acknowledgment. A nonzero waveform or `script_completed=true` is not complete conversational success. These files are received chunks, not a faithful microphone/speaker or wall-clock playback recording. Browser WebRTC, visible product synchronization, acoustic echo, naturalness, positive-hold audio and audio outage recovery were not tested.

## Published foundations

- Anthropic distinguishes tasks, repeated trials, graders, traces and final environment outcomes; recommends combining code, model and human grading; and distinguishes capability evaluations from regression checks. It also emphasizes examining traces and calibration rather than treating an aggregate score as sufficient evidence. [Demystifying evals for AI agents](https://www.anthropic.com/research/demystifying-evals-for-ai-agents)
- The original tau-bench grades final database state against annotated goal state and introduces pass^k for consistency over repeated trials. Its emphasis is particularly relevant to Fil's stock holds and policy compliance. [Original tau-bench paper](https://arxiv.org/abs/2406.12045)
- Tau2-bench uses compositional tasks, a simulator constrained by observable environment state, and ablations separating reasoning from communication/coordination. Fil can borrow these experimental ideas without implementing the benchmark's full dual-control environment. [Original tau2-bench paper](https://arxiv.org/abs/2506.07982)
- MT-Bench's judge study documents position, verbosity and self-enhancement biases and compares model judgments with human preferences. A different judge model is not automatically a trustworthy judge; it needs calibration. [Judging LLM-as-a-Judge](https://arxiv.org/abs/2306.05685)
- Full-Duplex-Bench separates pause handling, backchanneling, turn-taking and interruption management. It supports evaluating speech interaction behavior separately from text correctness. Its results do not directly establish thresholds for our cascaded ElevenLabs system. [Full-Duplex-Bench](https://arxiv.org/abs/2503.04721)

- Tau-Voice combines verifiable grounded task completion, full-duplex voice interaction and controllable audio conditions, enabling matched voice/text comparisons. It is a closer conceptual fit than a generic chatbot-quality benchmark. We borrow its separation of task success and voice interaction quality, without transferring its published model rankings to Fil. [Tau-Voice](https://arxiv.org/abs/2603.13686)
- Full-Duplex-Bench v1.5 probes interruption, listener backchannel, side conversation and background speech separately, including stop/response latency. This supports measuring whether Fil interrupts selectively, rather than rewarding it for stopping on every sound. [Full-Duplex-Bench v1.5](https://arxiv.org/abs/2507.23159)

## Five decisions that matter most

### 1. Define the claim and the failure costs before choosing more models

Target claim: a shopper can revise garment preferences in EN/CA/ES, receive grounded recommendations and a delivery estimate, and authorize or decline a synthetic hold without losing intent or creating an unauthorized action.

Use an explicit scorecard rather than one blended number:

| Dimension | Evidence | Proposed decision rule |
| --- | --- | --- |
| Business outcome | Final context, quotes and holds in SQLite | Exact allowed outcome; no unintended hold |
| Policy and grounding | Ordered trace plus tool results | No unauthorized write, fabricated stock/price/delivery, or silently relaxed constraints |
| Interaction quality | Questions, corrections and spoken responses | Useful clarification, no repetitive loops, appropriate language and complete acknowledgment |
| Audio interaction | Time-aligned caller input and actual output | Correct turn-taking, interruption recovery, no unintended truncation |
| Operational behavior | Tool errors, reconnects, durations and cost | Fail clearly; preserve consistent state; report availability separately |

One unauthorized hold should block a demo release even if many other cases pass. This is a product-risk gate, not a claim of zero production risk. Naturalness or speed must not compensate for a consent violation.

### 2. Freeze development and held-out cases, then sample the intended use

Keep the existing eleven templates as regression cases. Build new task families from combinations of intent and conditions, not merely cosmetic paraphrases: language direction; size/colour corrections; withheld budget/date; contradictory date; known zero versus unavailable inventory; explicit consent, summary acknowledgment and refusal; interruption timing; tool delay/error.

Each case should specify initial database/clock, shopper goal, information available to the shopper, allowed actions, required observed path, forbidden outcomes and a rubric. A deterministic script is appropriate for exact boundary probes. A constrained simulated user is useful for flexible conversations. Neither should see hidden expected assistant answers or grading rationales that a real shopper would not know.

Create separate development and held-out files before tuning. Split whole scenario families, speaker identities or audio recordings where relevant; near-duplicate paraphrases in both sets are leakage. Once a held-out failure is inspected and used to improve the agent, move it into regression/development and replenish the holdout. Never keep claiming it is unseen.

Proposed first increment: retain eleven regression/development cases; have a separate case author prepare twelve fresh held-out tasks, covering each existing behavior plus one compound case. Freeze those tasks before tuning and keep their exact wording and expected outputs out of the prompt-builder context. This small holdout demonstrates procedure rather than reliable population coverage. Expand based on the failure taxonomy and intended deployment distribution.

### 3. Grade outcomes and trajectories, and test the graders

Code should decide objectively checkable facts: final criteria, allowed SKUs, cents, dates, number of writes, quote ownership and persisted holds. Trace grading is still essential: a correct final database can conceal a temporary unauthorized action, misleading spoken claim or a check performed before clarification.

Use narrow model rubrics for semantic questions such as whether an utterance grants consent, whether a response preserves intent, or whether an explanation is grounded. Require cited turn/tool evidence and permit `uncertain`/`not exercised`. Keep code and semantic verdicts separate. Do not require an exact tool sequence when multiple valid sequences satisfy the policy; do require ordering when it encodes a real consent or clarification boundary.

Calibrate on a small deliberately mixed label set: valid behavior, known violations, and hard negatives such as “yes, that summary is right” without reservation permission. Include the already observed false positives and ISO-date false negative. Ideally two human reviewers label cases blind and reconcile disagreements; until that happens, describe judge calibration as provisional. Compare false-accept and false-reject rates per criterion, especially consent. For pairwise quality comparisons, hide candidate names and swap response order. Changing to a new judge family alone does not demonstrate correctness.

### 4. Validate the harness and separate text reasoning from audio/system failures

Before the next expensive run, feed controlled event traces into the harness: old response after new input; split ASR utterance; delayed audio; interrupted buffered chunks; a final goodbye; timeout; tool error. Verify its own pass/fail decisions. Our observed race makes this an immediate requirement, not a theoretical precaution.

Run controlled pairs: same semantic task as text and speech; same PCM input across candidates; same task without overlap versus timed overlap. This helps localize failure to ASR, dialogue, tool execution, TTS or timing. Preserve all attempted runs and classify `agent failure`, `provider failure`, `harness-invalid`, `scenario not exercised` and `passed`; report both task success among valid trials and overall completion/availability. Excluding invalid trials must not hide infrastructure instability.

For audio, preserve a synchronized two-channel timeline or explicit playback reconstruction, including discarded buffers. Measure latency from end of caller speech to first meaningful audible response, and interruption-stop latency from caller speech onset to cessation of actual agent playback. Do not substitute time-to-text, received byte duration or a provider interruption event for those measures. Separate non-interrupting backchannels, pauses within a sentence, deliberate corrections and final goodbyes. Use more than one synthetic caller voice; later add consented real recordings and device/browser checks. Independent STT is supporting evidence for spoken content, not a naturalness score.

### 5. Run repeated, paired trials and decide before inspecting the winners

Freeze candidate model/prompt/tool/harness versions, voice and audio settings, grader/simulator versions, dates, inventory and cost limits. Reuse identical starting states and inputs across candidates; randomize or interleave candidate order to reduce provider/time effects. Change one factor at a time when diagnosing a failure. If a repair changes the prompt or tool contract, label it a system comparison rather than attributing all improvement to the base model.

Proposed candidate assessment: eleven existing cases plus twelve fresh holdout cases, three trials each, produces69 text trials per frozen configuration. This is a diagnostic pilot budget, not a statistically powered benchmark. Run fast regression smoke checks during development; reserve the held-out trials until the candidate is frozen. A later audio matrix could use four critical scripts across clean speech, true interruption and background speech, repeated twice:24 audio calls per configuration. That is substantial for a portfolio and should not be the immediate next batch. First validate the harness/graders offline, run four clean audio probes, then spend on the smallest paired stress subset that can resolve a concrete hypothesis. Only expand to the full matrix if the pilot is valid and affordable. Estimate credits from measured call lengths and actual account usage before execution, separate TTS generation, conversation, transcription and judge costs, and stop at a predeclared spending limit. Do not execute these counts under an expired or exhausted build allowance.

Report per-task and per-slice successes, number of trials, critical violations, provider/harness failures, cost and duration. Repeated success on the same task is more useful here than “at least one of several retries worked.” Tau-bench's pass^k captures this distinction. Confidence intervals need the sampling unit and independence assumptions stated; multiple turns or near-identical paraphrases are not independent users. As an illustration only, zero failures in100 independent identically distributed trials still has a one-sided95% upper failure bound of approximately3%; eleven heterogeneous development cases justify no comparable reliability claim.

## Immediate recommendation for Fil

First isolate the closing-acknowledgment and rapid-overlap failures with deterministic event/audio fixtures. Then establish the holdout and calibrate the graders, run a small repeated paired evaluation, and publish a compact results card containing both strengths and unresolved limits. Do not choose another model merely because the current suite once reached11/11. For an FDE presentation, the credible story is that a discovered failure became a reproducible case, a targeted change improved a defined metric, and unseen tests plus system-level evidence checked that the change generalized.
