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
