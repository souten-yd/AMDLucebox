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

## 2026-09-03 Production Acceptance Phase 2 — BLOCKED_EXTERNAL

Repository and pinned upstream were rechecked at Phase 2 entry. AMDLucebox
`main` was `9bfba9d7927f5b323037cf5f187e161fde0e68c0`, upstream remained
`298031aa4222ec61c971ed834ec8f8829ce37a5c`, and the repository had zero
registered Actions runners. The R9700 host is Ubuntu 24.04.4 with kernel
`7.0.0-30-generic`; the current account has `render` and `video` access and
ROCm 7.2, but there is no dedicated non-root runner account. Codex has no
non-interactive sudo authority, so it must not weaken the boundary by running
the public-repository runner under the operator's general-purpose account.

Required external setup (runner registration tokens must stay out of Git and
logs):

```bash
sudo useradd --system --create-home \
  --home-dir /data1tb/AMDLucebox-runner --shell /bin/bash amdlucebox-runner
sudo usermod -aG render,video amdlucebox-runner
sudo install -d -o amdlucebox-runner -g amdlucebox-runner \
  /data1tb/AMDLucebox-runner/actions-runner
```

From GitHub `Settings > Actions > Runners > New self-hosted runner`, follow the
Linux x64 commands as `amdlucebox-runner`. Use Actions runner v2.337.0 archive
SHA-256 `70920811a4f8ad4328818682bca5c6469c1c942fab52448868071d0063816613`,
runner name `souten-r9700`, and custom labels `r9700,gfx1201`; retain the
default `self-hosted,Linux,X64` labels. Install and start it as a service owned
by `amdlucebox-runner`. Do not paste the short-lived registration token into
this file, an issue, or chat.

After the runner reports online, resume Phase 2 with:

```bash
gh workflow run validate-r9700.yml \
  --repo souten-yd/AMDLucebox --ref main \
  -f release_tag=lucebox-298031aa-r1 \
  -f track=reference -f model_backed=false \
  -f model_dir=/data1tb/LLM/AMDLucebox/qwen38 \
  -f hip_visible_devices=0
```

Phase 2 is not accepted until that manual workflow and its evidence artifact
are green. Model downloads requested by the operator may continue in parallel,
but model conversion and acceptance do not bypass this gate.
