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
no-model Phase 2 gate has passed. Qwen3.8 target and DFlash2 draft staging has
passed outside Git. Model loading, OpenAI-compatible generation, speculative
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

## 2026-09-03 Production Acceptance Phase 3 — PASS

Repository and pinned upstream were rechecked at Phase 3 entry. AMDLucebox
`main` was `1a2396254f2329889c9c117097587cb9aa63eee6`; the detached,
recursive Lucebox checkout remained
`298031aa4222ec61c971ed834ec8f8829ce37a5c` with pinned
Block-Sparse-Attention and CUTLASS submodules.

The production model pair is staged under
`/data1tb/LLM/AMDLucebox/qwen38`, outside both the repository and Actions
workspace:

- target `Qwen3.8-27B-UD-IQ4_XS.gguf`: 14,252,845,984 bytes, SHA-256
  `40fac4050e940397dbf13087afd50f4734a11805bf9d65ef8ddd7483470e6199`
- Q8_0 draft `qwen38-dflash2-q8_0.gguf`: 2,045,471,776 bytes, SHA-256
  `bb727abc583498aa4deea8b3cd0c34c2d96553954cbff25b5f7bdd469f0f1306`

The target is pinned to `unsloth/Qwen3.8-27B-GGUF` revision
`4ca720788d1e01f1bff70c033e0d0028fd02e502`. The draft source is pinned
to `incoai/Qwen3.8-27B-DFlash2` revision
`dedf8df68adfb1afeaf7b7480c0a0243108177b4`; its original
`model.safetensors` SHA-256 is
`67fc76d68dc5a9415511a4f394ef744d67510cd20e93b37cc2cc7d28e4bab65c`.
Both repository metadata files declare Apache-2.0.

Pinned upstream conversion produced an 81-tensor draft (49 Q8_0 tensors and
32 preserved F32 tensors). The local, machine-readable
`validation/model-manifest.json` records source revisions, file sizes/hashes,
submodules, exact converter/quantizer script hashes, commands, Python 3.12.3,
and package versions. Its SHA-256 is
`f14653657df9e5ffc32254bc260da304a6d71a56d7399d618f2dcde8ed247d3e`.
A full manifest-driven reread independently verified both production files.
No GGUF or safetensors file is tracked by Git or uploaded to GitHub.

## 2026-09-04 Production Acceptance Phase 4 — REOPENED

Repository and pinned upstream were rechecked at Phase 4 entry. AMDLucebox
`main` is `91f94489b79bcc985c83aeee90fce8f1d1e72798`; the detached upstream
checkout and recursive submodules remain exactly
`298031aa4222ec61c971ed834ec8f8829ce37a5c`,
`49d6c39e4dc0303442cda3bb758b3925d4399c49`, and
`a75b4ac483166189a45290783cb0a18af5ff0ea5`.

The initial model-backed Reference run exposed a benchmark-fidelity issue: the
three generic wrapper prompts did not match the published Lucebox workload.
[PR #11](https://github.com/souten-yd/AMDLucebox/pull/11) fixed the gate to use
the exact ten-prompt HTTP HumanEval corpus from the pinned upstream
`server/scripts/bench_he_http.py`, with the corpus SHA-256 recorded and enforced
across Reference and Candidate. CI run
[`33771166543`](https://github.com/souten-yd/AMDLucebox/actions/runs/33771166543)
passed 21 tests and the change merged as `91f94489b79bcc985c83aeee90fce8f1d1e72798`.

Trusted-main manual run
[`33771223236`](https://github.com/souten-yd/AMDLucebox/actions/runs/33771223236)
then passed every functional gate on the ROCm 7.2.4 Reference package:

- ten of ten API requests generated successfully and reported speculative
  decoding active
- average server decode: `174.93 tok/s` (WARN; Phase 4 PASS is `>= 180`)
- average client E2E: `143.435 tok/s`
- average draft acceptance: `0.702321`
- prompt corpus SHA-256:
  `e317321b7e26a48335860288b5bb9dc8666403d2c877f6043b10727f18dceb0c`
- model verification, release checksum, package verification, runtime `ldd`,
  HIP smoke, and all 447 packaged server tests: PASS
- evidence artifact ID `9899701873`, 59,175 bytes; benchmark JSON SHA-256
  `818fa8d0e5d5fa814abc37d08d366ee050fc99e8b8328899be3cb38ac9514c79`

The WARN result was investigated before proceeding. During the measured load,
the R9700 reached 98% GPU activity, 2,732 MHz GFX, and exactly the configured
210 W socket-power cap; hotspot temperature was only 71 C against the 110 C
slowdown limit. The device reports a 210 W minimum and 300 W maximum cap. This
host is therefore power-limited at the minimum board setting, rather than
thermally limited, while the published result was taken on the stock R9700
profile. The current non-root Codex/runner accounts cannot change that
root-owned setting.

A same-head reproducibility run was performed before concluding that privileged
intervention was required. Trusted-main run
[`33772011305`](https://github.com/souten-yd/AMDLucebox/actions/runs/33772011305)
again completed every functional gate and all ten speculative requests, but
measured `171.39 tok/s` server decode and `140.746 tok/s` client E2E. Its mean
acceptance was byte-for-byte identical at `0.702321`; three loaded samples were
again at 210 W, 95–97% GPU activity, and 2,722–2,768 MHz, with a maximum hotspot
temperature of 72 C. Evidence artifact ID `9900030035` is 59,249 bytes. Two
canonical runs therefore reproduce the sub-180 result under the minimum power
cap (`174.93` and `171.39 tok/s`); additional unchanged reruns are not accepted
as remediation.

External prerequisite and exact operator action:

```bash
sudo amd-smi set --gpu 0 --power-cap ppt0 300
amd-smi static --gpu 0 --limit --json
```

After the output confirms `socket_power_limit` is 300 W, resume with:

```bash
gh workflow run validate-r9700.yml --repo souten-yd/AMDLucebox --ref main \
  -f release_tag=lucebox-298031aa-r1 -f track=reference \
  -f model_backed=true -f model_dir=/data1tb/LLM/AMDLucebox/qwen38 \
  -f hip_visible_devices=0 -f benchmark_warmups=3 \
  -f benchmark_max_tokens=256
```

The operator subsequently approved `>= 120 tok/s` as the deployment acceptance
floor. The 300 W intervention is therefore no longer a prerequisite, and the
210 W investigation remains recorded as deployment provenance rather than an
open blocker. Phase 4 remains incomplete until a trusted-main run made after
the threshold change emits a machine-readable PASS. Phase 5 must not use either
older WARN run as its comparison baseline. The release remains a prerelease and
its three existing asset digests are unchanged.

### Phase 4 accepted Reference

[PR #14](https://github.com/souten-yd/AMDLucebox/pull/14) implemented the
operator-approved production floor and merged as
`adf68caea6c0091a5c0f937cb36057b5682c6d01` after CI run
[`33810870212`](https://github.com/souten-yd/AMDLucebox/actions/runs/33810870212)
passed all 21 repository tests. The Candidate regression limit remains 10%, and
the published 208 tok/s result remains a diagnostic reference rather than the
deployment floor.

Trusted-main Reference run
[`33810920024`](https://github.com/souten-yd/AMDLucebox/actions/runs/33810920024)
at that exact head is the accepted Phase 4 baseline:

- result: PASS with no failure reasons
- server decode average: `171.01 tok/s`
- client E2E average: `140.404 tok/s`
- mean acceptance: `0.702321`
- speculative decode: 10/10 requests (`1.0` fraction)
- workload: pinned-upstream ten-prompt HTTP HumanEval corpus, SHA-256
  `e317321b7e26a48335860288b5bb9dc8666403d2c877f6043b10727f18dceb0c`,
  three warmups, 256 maximum output tokens, greedy decoding
- server: block 16, max context 131072, K/V cache q8_0, visible GPU 0
- benchmark JSON SHA-256:
  `261c41f111451aabd550fb1ab2d4be4d2cd9bb9eefdb9c9a1010a1884d45d735`
- evidence artifact ID `9914766197`, 59,384 bytes, retained for 90 days

The tested package is the immutable ROCm 7.2.4 Reference asset with SHA-256
`297322f3885615665157ecad0939ed4e1c2c0cfabd2af8cd29feeb4d8b22feda`.
The host userspace is ROCm 7.2.1/HIP `7.2.53211`, the same required major/minor
family; kernel `7.0.0-30-generic` and the complete redacted R9700 environment,
process list, clocks, power and temperatures are preserved in the artifact.
Model hashes match the Phase 3 manifest. No crash, GPU fault, or KFD hang
occurred. Phase 4 is PASS; run `33810920024` is the only Reference run permitted
as the Phase 5 comparison input.

## 2026-09-04 Production Acceptance Phase 5 — PASS

Repository and pinned upstream were rechecked before the Candidate transition.
AMDLucebox used exact trusted-main commit
`489f0eb297b1e52ca04085763935a7652f538fb5`; upstream remained
`298031aa4222ec61c971ed834ec8f8829ce37a5c` with its recursive pinned
submodules unchanged.

ROCm 10.0.0 is not mixed into the system ROCm 7.2.1 installation. The exact
official userspace image used to build the Candidate was pulled and unpacked
rootlessly under `/data1tb/LLM/AMDLucebox/rocm10-runtime` from
`rocm/dev-ubuntu-24.04:10.0.0-full`, manifest digest
`sha256:a90cf047f615abe70fbef83c64def0a2d549ef37a39c8ea545430aba4981b374`.
Its stable image label, ROCm `.info/version` (`10.0.0`), and critical runtime
file hashes are retained in an external provenance manifest; no runtime or
model payload is tracked by Git.

[PR #16](https://github.com/souten-yd/AMDLucebox/pull/16), merged as
`a8c102105f86f8192c86bb89a58e879846121843` after CI run
[`33813448306`](https://github.com/souten-yd/AMDLucebox/actions/runs/33813448306),
added fail-closed runtime selection, image/hash verification, and linkage
checking. A first Candidate attempt, run
[`33813495220`](https://github.com/souten-yd/AMDLucebox/actions/runs/33813495220),
proved ROCm 10 selection, `gfx1201` HIP execution, Candidate linkage, all 447
packaged tests, and model verification before stopping prior to generation on a
Reference context-schema mismatch. No Candidate performance result was accepted
from that run. [PR #17](https://github.com/souten-yd/AMDLucebox/pull/17) fixed
the check to read the authoritative Reference environment evidence and merged
as `489f0eb297b1e52ca04085763935a7652f538fb5` after CI run
[`33813630963`](https://github.com/souten-yd/AMDLucebox/actions/runs/33813630963).

Trusted-main Candidate run
[`33813673307`](https://github.com/souten-yd/AMDLucebox/actions/runs/33813673307)
then passed the complete Phase 5 gate:

- Candidate server decode average: `171.94 tok/s` — PASS
- Candidate client E2E average: `141.212 tok/s`
- Candidate mean acceptance: `0.702321`
- speculative decode: 10/10 requests (`1.0` fraction)
- accepted Reference: run `33810920024`, `171.01 tok/s`
- regression: `-0.5438%` (Candidate is 0.5438% faster); allowed maximum 10%
- identical model identities/hashes, prompt corpus/hash, three warmups,
  256-token limit, greedy decoding, block 16, max context 131072, q8_0 K/V,
  and visible physical GPU: machine-readable comparison PASS with no errors
- ROCm 10 userspace, source image digest, critical file hashes, `gfx1201`
  preflight, runtime linkage with no ROCm 7.2 fallback, 447 packaged tests,
  release checksum, model verification, and environment captures: PASS
- maximum observed R9700 load: 99% GPU activity, 2,766 MHz GFX, 210 W,
  70 C hotspot, and 23,222 MB VRAM; no crash, GPU fault, or KFD hang

The tested Candidate package SHA-256 is
`52472001d7307c793396b995990b8a342492d511ab6969361e2553f50e182257`.
The Candidate benchmark JSON SHA-256 is
`5006168c854aa2b8443510267474b8e1a066edc5c72bad26dcafe71a54f75ff0`;
the Reference/Candidate comparison JSON SHA-256 is
`c861dd7d33fd113c53b91940a697069494e1405182351a9fc74c130a764e6399`.
Evidence artifact ID `9915738019` is 83,932 bytes, has archive digest
`sha256:2e09d1e7f2036179c53073933a9a7bfe3135f97a7ca3fd94d62e2690df3292b0`,
and is retained through 2026-12-02. Phase 5 is PASS.
