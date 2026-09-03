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

A dedicated repository self-hosted Actions runner is now registered and the
no-model Phase 2 gate has passed. Qwen3.8 target and DFlash2 draft staging is in
progress outside Git. Model loading, OpenAI-compatible generation, speculative
decoding, benchmark capture, and the ROCm 10 versus 7.2 performance comparison
have not executed yet. Releases must remain prereleases until those checks pass
through the trusted manual R9700 workflow described in
`SELF_HOSTED_RUNNER.md`.

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

## 2026-09-03 Production Acceptance Phase 2 — PASS

Repository and pinned upstream were rechecked at Phase 2 entry and acceptance.
AMDLucebox `main` was
`de657a3057bdf18dac63f2b807ed3e7d71ea1421`; upstream remained
`298031aa4222ec61c971ed834ec8f8829ce37a5c`.

The repository runner `souten-Linux` uses Actions runner v2.337.0 as a systemd
service under dedicated non-root UID 997 (`amdlucebox-runner`). It has
`render`/`video` group membership and the exact required labels
`self-hosted,Linux,X64,r9700,gfx1201`. The workflow remains manual-only and was
dispatched from trusted `main`; no pull-request event can select this runner.

Manual validation run
[`33764884969`](https://github.com/souten-yd/AMDLucebox/actions/runs/33764884969)
at exact head `de657a3057bdf18dac63f2b807ed3e7d71ea1421` passed in 1 minute
14 seconds with `track=reference`, `model_backed=false`, and
`HIP_VISIBLE_DEVICES=0`:

- `/dev/kfd`, render-node access, and non-hanging `rocminfo`: PASS
- selected native device: AMD Radeon AI PRO R9700 (`gfx1201`)
- compiled HIP vector-add smoke: PASS
- ROCm/HIP reported by the host compiler: `7.2.53211-e1a6bc5663`
- existing Release checksum and package verification: PASS
- host `ldd`: PASS, no missing dependency
- packaged upstream server tests: PASS, 447 passed / 0 failed / 0 skipped

Evidence artifact
`r9700-validation-lucebox-298031aa-r1-reference` has Actions artifact ID
`9897085515`, archive size 10,052 bytes, and uploaded ZIP SHA-256
`b495abc4c0403fd9af2522b8ed6caa507ff01f63b47ef43ccb96aa603dbdddba`.
It contains `rocminfo.txt`, `hipcc-version.txt`, the HIP smoke output/binary,
and `runtime-ldd.txt`; no model weights are present.
