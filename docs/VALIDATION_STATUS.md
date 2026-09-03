# Validation status

This file records the acceptance evidence for the initial implementation. It
is deliberately separate from release provenance: every package remains
self-describing through `BUILD_INFO.json` and every published release carries
its own checksums.

## 2026-09-03 initial acceptance

The wrapper resolved upstream `Luce-Org/lucebox` `main` to
`298031aa4222ec61c971ed834ec8f8829ce37a5c`. GitHub Actions run
[`33755079860`](https://github.com/souten-yd/AMDLucebox/actions/runs/33755079860)
built that exact source revision in both pinned environments:

- ROCm 7.2.4 Reference: PASS
- ROCm 10.0.0 Candidate: PASS
- `gfx1201` CMake cache and HIP code-object inspection: PASS
- archive checksum and package-structure verification: PASS

Both downloaded workflow artifacts were then checked on an Ubuntu 24.04 host
with a Radeon AI PRO R9700 and a ROCm 7.2 userspace. `ldd` reported no missing
dependencies and each packaged `test_server_unit` passed all 447 cases. The
Reference `dflash_server --help` invocation also completed successfully.

Bare-metal preflight on the same host reported `gfx1201` and compiled and ran
the repository's HIP vector-add smoke test on the R9700. This proves the local
KFD/HIP path and native `gfx1201` execution, but it is not model-backed Lucebox
validation.

## Environment-bound checks

No repository self-hosted Actions runner is currently registered, and the
Qwen3.8 target and DFlash2 draft weights are not staged on this host. Therefore
model loading, OpenAI-compatible generation, speculative decoding, benchmark
capture, and the ROCm 10 versus 7.2 performance comparison have not executed.
Releases must remain prereleases until those checks pass through the trusted
manual R9700 workflow described in `SELF_HOSTED_RUNNER.md`.

## 2026-09-03 Production Acceptance Phase 1 — PASS

Phase 1 was merged by [PR #2](https://github.com/souten-yd/AMDLucebox/pull/2)
as AMDLucebox commit `85fd4b01e0451f6fd3606bf4296288ad4c12e026`.
Pinned upstream `main` was rechecked immediately before and after acceptance and
remained `298031aa4222ec61c971ed834ec8f8829ce37a5c`.

- wrapper/unit and workflow validation: PASS, run
  [`33761452334`](https://github.com/souten-yd/AMDLucebox/actions/runs/33761452334)
  (15 tests plus repository CI gates)
- full ROCm 7.2.4 Reference build: PASS, run
  [`33761493554`](https://github.com/souten-yd/AMDLucebox/actions/runs/33761493554)
- full ROCm 10.0.0 Candidate build: PASS, same run `33761493554`
- publication from the PR: correctly skipped; existing release assets unchanged
- committed model weights: none

The benchmark result schema is now version 2. Its primary gate is
`usage.timings.decode_tokens_per_sec`; client end-to-end throughput is retained
separately. Missing server timings, failure to run speculative decoding on any
measured request, or a Candidate regression above 10% causes a production
failure. `HIP_VISIBLE_DEVICES` is set for the complete trusted validation job.
