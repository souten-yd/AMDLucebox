# Qwen3.8-27B Quant Comparison Plan — UD-IQ4_XS vs UD-Q4_K_M

## Goal

Measure the practical trade-off on the same Radeon AI PRO R9700 between:

1. `Qwen3.8-27B-UD-IQ4_XS.gguf` — current AMDLucebox production baseline / speed-oriented profile.
2. `Qwen3.8-27B-UD-Q4_K_M.gguf` — larger quality-oriented profile.

This is an experiment after Production Acceptance. It must not change the identity, assets, promotion state, or acceptance evidence of Stable release `lucebox-298031aa-r1`.

Use the existing ROCm 10.0.0 Stable Candidate binary and the existing Q8_0 DFlash2 draft unless a test explicitly states otherwise. Do not rebuild Lucebox merely to compare target quantizations.

## Fixed model identities

Baseline already staged:

- repository: `unsloth/Qwen3.8-27B-GGUF`
- repository revision currently used by AMDLucebox acceptance: `4ca720788d1e01f1bff70c033e0d0028fd02e502`
- file: `Qwen3.8-27B-UD-IQ4_XS.gguf`
- SHA-256: `40fac4050e940397dbf13087afd50f4734a11805bf9d65ef8ddd7483470e6199`
- size: 14,252,845,984 bytes

Comparison target:

- repository: `unsloth/Qwen3.8-27B-GGUF`
- prefer the same pinned repository revision if the file exists there; otherwise resolve and record one immutable revision containing the exact file and do not use floating `main`
- file: `Qwen3.8-27B-UD-Q4_K_M.gguf`
- expected current SHA-256: `322e194ff79741c7baa497c240f677f54b201b0efab44ca8e50f122b39123482`
- public file size is approximately 16.5 GB; record the exact downloaded byte size

Draft for both targets:

- file: `qwen38-dflash2-q8_0.gguf`
- SHA-256: `bb727abc583498aa4deea8b3cd0c34c2d96553954cbff25b5f7bdd469f0f1306`
- the same exact draft file must be used for both target quants

Never commit or upload model weights.

## Isolation from Production Acceptance

Do not modify `validation/model-manifest.json` used by Stable Production Acceptance; it intentionally describes exactly one target plus one draft.

Create a separate local-only comparison manifest, for example:

`/data1tb/LLM/AMDLucebox/qwen38/validation/quant-comparison-manifest.json`

It must identify both target quants, the common draft, immutable source revisions, SHA-256, exact sizes, and the Stable Lucebox release/package digest used for the benchmark.

Repository changes should add a separate manual-only quant-comparison workflow rather than weakening `validate-r9700.yml` acceptance semantics.

## Required implementation

Create a small PR that adds reusable comparison support without changing the Stable release contract.

Preferred structure:

- `.github/workflows/compare-quants-r9700.yml` — `workflow_dispatch` only, trusted self-hosted R9700 labels only.
- `scripts/prepare-qwen38-quant-comparison.sh` — stage/verify Q4_K_M outside Git, using an immutable Hugging Face revision. Reuse the existing DFlash2 draft; do not reconvert it unnecessarily.
- `scripts/compare-qwen38-quants.py` or equivalent — combine repeated benchmark JSON and environment/metrics into one machine-readable comparison report.
- tests for filename/path validation, hash verification, result aggregation, equal-settings checks, and failure cases.

The comparison workflow must never run on `pull_request` or `pull_request_target` and must never expose repository write credentials to the self-hosted runner.

## Runtime under test

Use the exact Stable ROCm 10 package from `lucebox-298031aa-r1`:

- `lucebox-r9700-rocm10.0.0-gfx1201-298031aa.tar.zst`
- SHA-256: `52472001d7307c793396b995990b8a342492d511ab6969361e2553f50e182257`

Use the same verified ROCm 10.0.0 userspace already accepted in Production Acceptance, including the same isolated runtime provenance/digest checks. Do not compare one quant on ROCm 7.2 and the other on ROCm 10.

## Fixed DFlash2 server settings

For both quants:

- DFlash2 Q8_0 draft: identical file
- `--draft-block-size 16`
- `--max-ctx 131072`
- `--cache-type-k q8_0`
- `--cache-type-v q8_0`
- temperature `0`
- one visible physical R9700 via the same `HIP_VISIBLE_DEVICES`
- no concurrent LLM workload

Record all arguments in the result JSON.

## Power profiles

The first comparison must use the current deployment profile of 210 W because that is the presently configured R9700 power limit.

Then perform a second comparison at 300 W to measure maximum-speed behavior if the operator makes the Full Power profile available.

Do not grant the GitHub runner broad root/sudo access merely to automate the power change. Detect and record the actual socket power limit before every measured run. If 300 W requires operator action, report `BLOCKED_EXTERNAL_POWER_PROFILE` with the exact required action and resume command; preserve the complete accepted 210 W result.

For a valid power-profile pair:

- every 210 W run must verify the limit is 210 W before measurement
- every 300 W run must verify the limit is 300 W before measurement
- do not label a run 300 W merely because it was requested

## Throughput benchmark

Reuse the pinned AMDLucebox ten-prompt HTTP HumanEval corpus and existing `benchmark-r9700.py` server-side timing fields.

For each quant and each power profile:

- 3 warm-up requests before each recorded benchmark
- 256 max output tokens
- greedy decoding
- run at least 3 independent recorded repetitions
- alternate model order between repetitions when practical (for example A/B/B/A/A/B or equivalent) so thermal/time drift does not always favor one model

Primary metrics:

- server decode tok/s
- client E2E tok/s
- DFlash2 acceptance rate
- speculative decode request fraction
- prefill time / derived prefill throughput when available
- maximum VRAM usage
- GPU activity
- GFX clock
- socket power
- hotspot temperature

Report median, arithmetic mean, minimum, maximum, and coefficient of variation for throughput. Flag the result as noisy if the coefficient of variation exceeds 3%.

A failed speculative decode request invalidates that repetition for a DFlash2 comparison and must be investigated rather than silently averaged.

## Practical long-context benchmark

The ten short HumanEval prompts are deliberately speculation-friendly and do not represent all agent workloads. Add one deterministic practical coding-context workload using a fixed prompt corpus with its SHA-256 recorded.

Target approximately 32K input tokens and 512 output tokens. Prefer a deterministic corpus assembled from pinned open-source code/text already available to the experiment; record how the prompt is constructed and its final file SHA-256.

Measure the same throughput, acceptance, VRAM, clock, power, and temperature metrics for both quants. The exact prompt must be identical between targets and power profiles.

Do not use the short HumanEval result alone to choose the daily-driver quant.

## Quality comparison

DFlash2 verification means accepted draft tokens are checked by the target, so the relevant quality difference is the target quantization itself. Measure quality independently of throughput.

Preferred deterministic quality metric:

1. Build/use `llama-perplexity` from the exact pinned llama.cpp revision contained by the accepted Lucebox upstream source.
2. Use a fixed public evaluation corpus with revision/hash recorded (WikiText-2 test is acceptable).
3. Use identical context/KV/settings for both quant files.
4. Report perplexity for IQ4_XS and Q4_K_M; lower is better.

Do not use a different model family, modified fine-tune, or floating evaluation corpus.

Optional functional coding quality may be added with HumanEval pass@1, but generated code must not be executed unsandboxed on the persistent R9700 runner. If functional execution is used, evaluate generated samples in an isolated ephemeral environment with no secrets/network and strict CPU/memory/time limits, or evaluate on a separate ephemeral hosted runner. Preserve generation settings and test harness revision.

## Result schema

Produce a final `quant-comparison.json` plus a human-readable `QUANT_COMPARISON_RESULT.md` containing at least:

- exact AMDLucebox commit
- exact Lucebox/upstream commit
- release asset name and SHA-256
- ROCm userspace version/provenance
- kernel
- GPU identity
- power limit actually observed
- both target model identities/hashes/sizes
- common DFlash draft identity/hash
- benchmark corpus hashes
- all repeated run measurements
- aggregate speed statistics
- acceptance statistics
- peak VRAM
- long-context results
- perplexity/quality result
- recommendation

Upload only logs/results/manifests that contain no model weights or secrets.

## Decision rules

Do not decide only from nominal quant size.

Recommended practical decision logic:

- Choose Q4_K_M as default if its quality metric is materially better and its median real workload throughput is within 10% of IQ4_XS while still retaining adequate VRAM headroom at 131K context.
- Prefer IQ4_XS if Q4_K_M is more than 10% slower in the practical workload and the measured quality gain is small for the intended coding/agent tasks.
- If Q4_K_M raises DFlash2 acceptance enough to recover most or all of its heavier target cost, explicitly report that; the DFlash2 result may differ from plain decode intuition.
- Record separate recommendations for `210 W efficiency/daily` and `300 W maximum performance` if the winner or trade-off changes by power profile.

Do not change the existing Stable release or its Production Acceptance status based on this experiment. A future default-model documentation change should be a separate PR after evidence review.

## Expected interpretation before measurement

The existing accepted IQ4_XS result at 210 W / ROCm 10 is approximately 171.94 tok/s server decode, 141.212 tok/s client E2E, and 0.702321 average DFlash2 acceptance on the accepted ten-prompt workload. Treat it as historical context, not a substitute for the new repeated A/B run.

Q4_K_M is roughly 2.2 GB larger than IQ4_XS, so it is expected to use more VRAM. The current IQ4_XS accepted run peaked near 23.2 GB VRAM at the 131K server setting, leaving enough nominal capacity on a 32 GB R9700 to test Q4_K_M without changing the context/KV settings. Actual measured allocation is authoritative.

Public community measurements suggest Q4_K_M can preserve quantization quality better than IQ4_XS, while DFlash2 has been shown to work with Q4 targets and a Q8_0 draft. These are hypotheses for this experiment, not acceptance evidence; the R9700 A/B measurements decide the result.

## Codex execution contract

Codex should:

1. Re-read this plan, current repository state, Stable Production Acceptance evidence, and pinned upstream Lucebox before editing.
2. Implement comparison support in a small PR without weakening Production Acceptance workflows.
3. Run unit/lint/actionlint/shellcheck gates and merge only when green.
4. Stage and hash Q4_K_M outside Git at the immutable revision.
5. Run the complete ROCm 10 A/B comparison at verified 210 W automatically.
6. If 300 W is already active/available through an existing approved mechanism, run the 300 W A/B comparison; otherwise stop only that sub-phase as `BLOCKED_EXTERNAL_POWER_PROFILE` and state the exact operator action needed. Do not grant broad sudo to the runner.
7. Run deterministic quality/perplexity comparison and practical 32K workload.
8. Analyze repeated results statistically and check for thermal/power/noise bias.
9. Write `docs/QUANT_COMPARISON_RESULT.md` with a clear daily-driver and maximum-performance recommendation, and preserve machine-readable non-secret evidence.
10. Do not modify Stable release assets or promotion status.
