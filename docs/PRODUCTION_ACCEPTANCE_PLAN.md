# AMDLucebox Production Acceptance Plan

## Purpose

This plan is the execution contract for taking the current AMDLucebox prerelease from reproducible `gfx1201` builds to a model-backed, measured, production-accepted R9700 release.

The current release pipeline is already accepted for hosted build/package/release behavior. This plan starts from that state and focuses on the remaining R9700 runtime and performance acceptance work.

Initial release under test:

- AMDLucebox release: `lucebox-298031aa-r1`
- Upstream Lucebox: `298031aa4222ec61c971ed834ec8f8829ce37a5c`
- Reference artifact: ROCm 7.2.4 / `gfx1201`
- Candidate artifact: ROCm 10.0.0 / `gfx1201`
- Target GPU: Radeon AI PRO R9700
- Promotion baseline model: `Qwen3.8-27B-UD-IQ4_XS.gguf`
- Draft model: Qwen3.8-27B DFlash2 converted to Q8_0

`Qwen3.8-27B-UD-Q4_K_M.gguf` may be benchmarked later as an additional practical profile, but it must not replace UD-IQ4_XS for the initial production gate because the published Lucebox R9700 reference numbers use UD-IQ4_XS.

## Autonomy rules for Codex

Codex should execute these phases in order and evaluate each phase before continuing.

- Read this file, `IMPLEMENTATION_PLAN.md`, `VALIDATION_STATUS.md`, `RELEASE.md`, and `SELF_HOSTED_RUNNER.md` before making changes.
- Re-check the current repository and upstream Lucebox implementation before editing code; do not assume API fields or CLI flags from prose if the pinned upstream source differs.
- Use small PRs for code/workflow changes. Run deterministic tests and the applicable full ROCm build before merge.
- Keep the R9700 self-hosted workflow manual-only. Never make an untrusted PR capable of executing on the R9700 runner.
- Never commit, upload, or attach GGUF/safetensors model weights to GitHub.
- Do not silently change the target from `gfx1201`.
- Record exact upstream SHA, AMDLucebox SHA, model filenames/hashes, ROCm version, driver/kernel information, GPU identity, power/clock state, and benchmark settings with every model-backed measurement.
- Continue automatically while the required environment is available. If an external prerequisite is genuinely unavailable (for example, no registered R9700 runner, no sudo access for a required ROCm switch, or missing model access), record `BLOCKED_EXTERNAL` in `VALIDATION_STATUS.md` with the exact missing prerequisite and the exact next command/action. Do not mark the phase complete.
- After the prerequisite is supplied, resume from the first incomplete phase; do not repeat already accepted destructive/environment setup work unnecessarily.

## Phase 1 — Correct benchmark semantics and GPU selection

Create one small PR before model-backed validation.

### Benchmark changes

Update `scripts/benchmark-r9700.py` so every request records both server-side decode throughput and client end-to-end throughput.

Use the pinned Lucebox API response as the source of truth. Prefer the server-provided fields when present:

- `usage.timings.decode_tokens_per_sec`
- `usage.timings.decode_ms`
- `usage.timings.prefill_ms`
- `usage.spec_decode_ran`
- `usage.accept_rate`

Retain wall-clock client timing as a separate metric.

Required per-request output:

- completion tokens
- client elapsed seconds
- `client_e2e_tokens_per_second`
- `server_decode_tokens_per_second`
- prefill milliseconds
- decode milliseconds
- speculative decode ran flag
- acceptance rate

Required aggregate output:

- average server decode tok/s
- average client E2E tok/s
- average acceptance rate when reported
- count/fraction of requests for which speculative decode actually ran
- pass/warn/fail result
- optional comparison against a Reference JSON

The primary performance gate must use **server decode tok/s**, not wall-clock E2E tok/s. E2E remains a reported secondary metric.

Operator-approved production thresholds (revised 2026-09-04 after two
canonical R9700 measurements under the deployment host's 210 W policy):

- decode PASS: `>= 120 tok/s`
- decode WARN: `110–120 tok/s`
- decode FAIL: `< 110 tok/s`
- Candidate regression gate: no more than 10% slower than the captured Reference server-decode average
- model-backed DFlash2 acceptance requires speculative decode to run; a run that silently falls back to ordinary decoding is not a production PASS

Do not invent a hard minimum acceptance-rate threshold until real R9700 measurements are available. Record it first, then set a threshold from evidence if useful.

Add/adjust unit tests for the new response parsing, missing timing fields, speculative-decode detection, threshold behavior, and Reference comparison.

### GPU selection changes

Update `.github/workflows/validate-r9700.yml` so GPU selection applies to the entire validation job, not only the preflight subprocess.

Add a manual input such as `hip_visible_devices` with default `0`, and set `HIP_VISIBLE_DEVICES` at job scope. After masking the selected R9700, the Lucebox process should see that selected GPU consistently.

Preflight must still verify that the selected visible device reports `gfx1201` and successfully executes the HIP smoke test. Preserve diagnostics sufficient to identify the selected device.

### Phase 1 acceptance

- wrapper/unit tests PASS
- workflow syntax PASS
- full ROCm Reference build PASS
- full ROCm Candidate build PASS
- no model weights in Git
- PR merged

Update `VALIDATION_STATUS.md` with the merged commit and acceptance evidence.

## Phase 2 — Register and validate the R9700 self-hosted runner

Required runner labels:

- `self-hosted`
- `linux`
- `x64`
- `r9700`
- `gfx1201`

Use the security boundary already documented in `SELF_HOSTED_RUNNER.md`: dedicated non-root service account, required `render`/`video` access, no repository-admin credential, and no untrusted PR trigger.

Do not store a runner registration token in the repository or logs.

Run the manual R9700 validation workflow first with `model_backed=false` against the current prerelease. It must pass:

- `/dev/kfd` and `/dev/dri` checks
- `rocminfo` without hang
- selected device is `gfx1201`
- native HIP smoke test
- release checksum verification
- package verification
- host `ldd` with no missing dependency
- packaged `test_server_unit`

Store the validation artifact/run URL in `VALIDATION_STATUS.md`.

## Phase 3 — Stage Qwen3.8 + DFlash2 models outside Git

Use a pinned checkout of upstream Lucebox matching the release under test (`298031aa4222ec61c971ed834ec8f8829ce37a5c`) when running conversion scripts.

Target location on the current acceptance host (operator-selected external
storage; this overrides the earlier example under `/var/lib`):

```text
/data1tb/LLM/AMDLucebox/qwen38/
├── Qwen3.8-27B-UD-IQ4_XS.gguf
└── qwen38-dflash2-q8_0.gguf
```

Use `scripts/prepare-qwen38.sh` or improve it only if current upstream requires a change. Do not put model files in the Actions workspace.

Create a local validation manifest (no model contents) containing:

- model repository
- exact filename
- SHA-256 of each staged model file
- upstream Lucebox commit used for DFlash conversion
- conversion/quantization command versions

The manifest may be uploaded as validation evidence; model weights may not.

## Phase 4 — Capture ROCm 7.2.4 Reference measurement

Run the Reference artifact on a host whose runtime/userspace is appropriate for the ROCm 7.2.4 Reference build. Do not treat a mismatched ROCm-major host as the canonical Reference measurement.

Use:

- `Qwen3.8-27B-UD-IQ4_XS.gguf`
- Q8_0 DFlash2 draft
- draft block size 16
- max context 131072
- K cache q8_0
- V cache q8_0
- same prompts and token limits that will later be used for Candidate
- fixed/recorded GPU selection
- recorded power, clocks, temperatures, and other major load on the machine

Run enough warm-up to avoid a cold-start measurement being used as the gate. Then capture `benchmark-reference.json` and server log.

Reference acceptance:

- API generation succeeds
- DFlash2/speculative decode actually runs
- server decode average is recorded
- E2E average is recorded separately
- acceptance rate is recorded
- no crashes, GPU faults, or KFD hangs

The published ~208 tok/s server-decode result is a target/reference point, not
a requirement for exact equality. Investigate materially lower performance
before moving on. The investigation must remain in the evidence even when the
operator-approved 120 tok/s deployment floor is met.

Record the full evidence and exact environment in `VALIDATION_STATUS.md`.

## Phase 5 — Switch to ROCm 10.0.0 and capture Candidate measurement

Use the **same physical R9700 machine and the same model files/manifest** where practical.

ROCm 7.2.4 Reference and ROCm 10.0.0 Candidate are different runtime tracks. Do not fake this comparison by running both artifacts against one mismatched ROCm userspace. If the machine must be upgraded or booted into another system image, preserve the Reference evidence first and record the environment transition.

Before Candidate measurement:

- verify ROCm 10.0.0 userspace/runtime
- reboot if required by the ROCm/driver transition
- rerun `preflight-r9700.sh`
- confirm `gfx1201`
- confirm the Candidate artifact has no missing runtime dependency

Run the identical benchmark configuration used by Reference and produce `benchmark-candidate.json`.

Candidate production acceptance requires:

- functional API generation PASS
- DFlash2/speculative decode PASS
- no GPU/KFD/runtime fault
- Candidate average server decode throughput `>= Reference × 0.90`
- Reference/Candidate settings and models are demonstrably identical except for the intended ROCm track/runtime differences

Record the comparison in machine-readable JSON and `VALIDATION_STATUS.md`.

## Phase 6 — Attach evidence and promote the exact validated release

Attach or otherwise preserve non-secret validation evidence for the exact release assets that were tested:

- `benchmark-reference.json`
- `benchmark-candidate.json`
- Reference and Candidate server logs (after checking they contain no secrets)
- R9700 preflight diagnostics
- runtime dependency output
- model manifest with filenames and hashes only
- ROCm/driver/kernel/GPU/power/clock environment manifest
- Reference-vs-Candidate comparison result

### Promotion integrity rule

**Do not rebuild or replace the release assets after model-backed validation merely to clear the prerelease flag.** A rebuild changes the artifact identity and invalidates the evidence-to-asset relationship.

The current documented `force_rebuild=true` + `validated_release=true` path must therefore not be used for final promotion of already-tested assets unless the rebuilt assets are revalidated from scratch.

Prefer an in-place promotion mechanism that only changes release metadata (`prerelease=false`) after evidence has passed. If needed, implement a small trusted/manual promotion workflow or script with `contents: write` that:

1. identifies the existing release tag,
2. verifies the expected asset SHA-256 values still match the validated assets,
3. verifies/records the accepted validation evidence,
4. changes only the release prerelease state,
5. does not execute upstream source or replace package assets.

Update `RELEASE.md` so this is the canonical promotion path.

Final acceptance:

- exact validated assets unchanged
- evidence attached/preserved
- `lucebox-298031aa-r1` promoted from prerelease to normal release
- `VALIDATION_STATUS.md` records final PASS with links/run IDs and measured Reference/Candidate values

## Optional Phase 7 — Q4_K_M practical profile

Only after the initial UD-IQ4_XS production gate is complete, optionally stage and benchmark `Qwen3.8-27B-UD-Q4_K_M.gguf` with the same Q8_0 DFlash2 draft.

Record it as an additional practical profile, not as a replacement for the initial published-reference comparison. Compare:

- server decode tok/s
- E2E tok/s
- acceptance rate
- VRAM usage
- functional quality checks if available

## Completion definition

This plan is complete only when all of the following are true:

- Phase 1 benchmark/GPU-selection PR is merged and green
- R9700 self-hosted runner lightweight validation is green
- target and DFlash2 models are staged outside Git with hashes recorded
- ROCm 7.2.4 model-backed Reference evidence exists
- ROCm 10.0.0 model-backed Candidate evidence exists
- Candidate is not more than 10% slower than Reference on the primary server-decode metric
- speculative decoding is confirmed active
- the exact tested release assets remain unchanged
- validation evidence is preserved
- the release is promoted in place to non-prerelease
- `VALIDATION_STATUS.md` contains final measurements and links
