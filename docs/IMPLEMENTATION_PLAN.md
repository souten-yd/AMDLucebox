# AMDLucebox Implementation Plan

## 1. Purpose

AMDLucebox is a reproducible build, validation, and release wrapper for the latest upstream `Luce-Org/lucebox`, specialized for AMD Radeon AI PRO R9700 / RDNA4 / `gfx1201` on Linux.

This repository must not become a fork containing a long-lived copy of Lucebox. Its role is to:

1. resolve and pin the latest upstream Lucebox commit,
2. build R9700-native `gfx1201` binaries,
3. produce separate ROCm 7.2.4 reference and ROCm 10.0.0 production-candidate artifacts,
4. package provenance and runtime dependency information,
5. validate artifacts on a real R9700 self-hosted runner when available,
6. publish reproducible GitHub Releases,
7. automatically detect and build new upstream commits.

Primary upstream:

- Repository: `https://github.com/Luce-Org/lucebox`
- Branch: `main`
- Official R9700 reference: `https://www.lucebox.com/blog/qwen38-r9700`

## 2. Target platform

Primary supported target:

- GPU: AMD Radeon AI PRO R9700
- GPU architecture: RDNA4 / Navi 48
- LLVM/HIP target: `gfx1201`
- Host architecture: Linux x86_64
- Primary OS: Ubuntu 24.04.4 LTS

`gfx1201` is mandatory. Do not silently substitute `gfx1200`. Upstream Lucebox explicitly documents that `gfx1200` and `gfx1201` code objects are not compatible and that R9700 requires `gfx1201`.

Initial releases do not guarantee support for Windows, SteamOS, Arch, Debian, or GPUs other than R9700. Multi-architecture fat binaries are out of scope for the first stable implementation.

## 3. ROCm strategy

Maintain two build tracks for the exact same upstream Lucebox commit.

### 3.1 Reference build

- ROCm: 7.2.4
- Role: reference/baseline
- Target: `gfx1201`
- Purpose: preserve a close comparison point to the ROCm 7.2 environment used in the official Lucebox R9700/Qwen3.8 benchmark.

Preferred build image:

`rocm/dev-ubuntu-24.04:7.2.4-complete`

### 3.2 Production candidate

- ROCm: 10.0.0
- Role: production candidate
- Target: `gfx1201`
- Purpose: validate and eventually promote the current AMD stack for normal R9700 use.

Preferred build image:

`rocm/dev-ubuntu-24.04:10.0.0-full`

### 3.3 Container pinning

Pin build images by immutable image digest in CI, not tag alone. Keep the human-readable tag and resolved digest in `BUILD_INFO.json`.

Before changing a digest, verify it against the current AMD image registry rather than copying an old value from documentation.

## 4. Native-build definition

For this project, “R9700 native build” means the generated HIP code is compiled explicitly for `gfx1201`.

Using Docker as the compiler environment is acceptable and preferred for GitHub-hosted CI. The actual runtime validation and benchmark should run bare-metal on the R9700 self-hosted runner.

Expected flow:

```text
GitHub-hosted runner
    -> pinned ROCm build container
    -> HIP/clang compilation for gfx1201
    -> packaged dflash_server artifact
    -> self-hosted Ubuntu/R9700 runner
    -> native execution without Docker
```

## 5. Upstream source resolution

Do not build an unpinned moving `main` checkout.

Workflow must:

1. query `refs/heads/main` from `Luce-Org/lucebox`,
2. record the full commit SHA,
3. clone/fetch upstream,
4. checkout that exact SHA,
5. initialize all required submodules recursively,
6. build both ROCm tracks from that same SHA.

Suggested resolution command:

```bash
git ls-remote https://github.com/Luce-Org/lucebox.git refs/heads/main
```

Suggested checkout sequence:

```bash
git clone https://github.com/Luce-Org/lucebox.git upstream
cd upstream
git checkout "$UPSTREAM_SHA"
git submodule update --init --recursive
```

Store recursive submodule provenance in `SUBMODULES.txt` using:

```bash
git submodule status --recursive
```

## 6. Follow current upstream, do not hard-code stale assumptions

At each implementation/update, inspect the current upstream:

- `README.md`
- `Dockerfile.rocm`
- `server/CMakeLists.txt`
- `.github/workflows/ci.yml`
- relevant `server/docs/*`

Current known upstream behavior includes:

- explicit `DFLASH27B_GPU_BACKEND=hip`,
- explicit `DFLASH27B_HIP_ARCHITECTURES=gfx1201` support,
- `dflash_server` as a primary server target,
- R9700 self-hosted CI using `gfx1201`,
- HIP vector-add/KFD health checks,
- ROCm-specific dependencies in `Dockerfile.rocm`.

If upstream renames/removes an option, adapt the wrapper to the current upstream contract. Do not silently drop important functionality just to make CI green.

## 7. R9700 build configuration

Baseline CMake configuration should remain aligned with the official Lucebox R9700 guidance:

```bash
cmake -S server -B server/build-hip -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_HIP_COMPILER=/opt/rocm/lib/llvm/bin/clang++ \
  -DDFLASH27B_GPU_BACKEND=hip \
  -DDFLASH27B_HIP_ARCHITECTURES=gfx1201 \
  -DGGML_HIP_MMQ_MFMA=ON \
  -DGGML_HIP_NO_VMM=ON
```

Where compatible with the current upstream ROCm path, also use the upstream ROCm build constraints:

```text
-DCMAKE_BUILD_WITH_INSTALL_RPATH=ON
-DDFLASH27B_FA_ALL_QUANTS=OFF
-DDFLASH27B_ENABLE_BSA=OFF
```

Do not add speculative optimization flags merely because ROCm 10 is newer. First isolate the ROCm version as the only major variable.

Build at least:

```bash
cmake --build server/build-hip --target dflash_server -j"$(nproc)"
```

When supported by current upstream, also build/test:

- `test_dflash`
- `test_server_unit`

## 8. ROCm build dependencies

Use current upstream `Dockerfile.rocm` as the primary dependency reference. At the time this plan was created it includes, among others:

- build-essential
- ca-certificates
- cmake
- curl
- git
- git-lfs
- hipblas-dev
- hipcub-dev
- libcurl4-openssl-dev
- ninja-build
- pkg-config
- python3
- rocblas-dev
- rocprim-dev
- rocwmma-dev

ROCm 10 package naming/content may differ. Resolve dependency changes against the current AMD/upstream environment rather than hard-coding workarounds without explanation.

## 9. Repository architecture

Target repository structure:

```text
AMDLucebox/
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── release.yml
│       └── validate-r9700.yml
├── docker/
│   └── Dockerfile.build
├── scripts/
│   ├── resolve-upstream.sh
│   ├── build.sh
│   ├── package.sh
│   ├── verify-package.sh
│   ├── prepare-qwen38.sh
│   ├── run-qwen38-r9700.sh
│   └── benchmark-r9700.py
├── config/
│   └── build-matrix.json
├── docs/
│   ├── IMPLEMENTATION_PLAN.md
│   ├── DESIGN.md
│   ├── RELEASE.md
│   └── SELF_HOSTED_RUNNER.md
├── tests/
├── .gitignore
└── README.md
```

Exact names may be adjusted if a cleaner implementation is found, but separation of build, package, release, and R9700 validation responsibilities must remain.

## 10. GitHub Actions design

### 10.1 `ci.yml`

Purpose: validate AMDLucebox's own scripts, configuration, Docker/build definitions, formatting, and packaging logic.

Triggers:

- pull requests,
- pushes to `main`,
- manual dispatch.

The self-hosted R9700 runner must never execute untrusted pull-request code.

### 10.2 `release.yml`

Purpose: resolve latest upstream, build both ROCm tracks, verify/package artifacts, and create/update a release.

Triggers:

- `workflow_dispatch`,
- scheduled check (initially once per day is sufficient).

Suggested logical stages:

```text
resolve-upstream
    -> compare with released upstream SHA
    -> stop cleanly if unchanged (unless force rebuild)
    -> ROCm 7.2.4 reference build
    -> ROCm 10.0.0 candidate build
    -> verify artifacts
    -> package
    -> checksums/provenance
    -> GitHub prerelease/release
```

Manual inputs should include at least:

- `upstream_ref` (default `main`)
- `force_rebuild` (default `false`)

Allow a specific upstream commit/ref to be rebuilt for reproducibility and debugging.

### 10.3 `validate-r9700.yml`

Purpose: trusted bare-metal validation on an actual R9700.

Runner labels should be explicit, for example:

```text
self-hosted
linux
x64
r9700
gfx1201
```

Initial trigger should be `workflow_dispatch`; later it may also be invoked by a trusted release workflow after artifacts are built.

Never trigger this workflow directly from arbitrary/fork PRs.

## 11. CI security model

Treat upstream source as code that must not receive repository write credentials during compilation.

Build jobs:

```yaml
permissions:
  contents: read
```

Do not expose release PATs, repository secrets, OIDC write privileges, or other write credentials to jobs that execute freshly fetched upstream code.

Release publication must be a separate trusted job with only the permissions it needs, e.g. `contents: write`.

Pin third-party GitHub Actions to immutable commit SHAs wherever practical.

## 12. Build matrix

Centralize build-track metadata rather than duplicating it throughout workflows.

Conceptually:

```json
[
  {
    "name": "reference",
    "rocm": "7.2.4",
    "image": "rocm/dev-ubuntu-24.04:7.2.4-complete",
    "arch": "gfx1201"
  },
  {
    "name": "candidate",
    "rocm": "10.0.0",
    "image": "rocm/dev-ubuntu-24.04:10.0.0-full",
    "arch": "gfx1201"
  }
]
```

The implementation should record the pinned digest separately or alongside this configuration.

## 13. Packaging

Produce a separate package for each ROCm track:

```text
lucebox-r9700-rocm7.2.4-gfx1201-<upstream-short-sha>.tar.zst
lucebox-r9700-rocm10.0.0-gfx1201-<upstream-short-sha>.tar.zst
```

Preserve an upstream-like build/library layout initially. Avoid aggressive relocation of shared libraries or RPATH rewriting unless necessary and tested.

Suggested package contents:

```text
lucebox-r9700/
├── server/
│   ├── build/
│   │   ├── dflash_server
│   │   ├── deps/...
│   │   └── share/...
│   ├── scripts/...
│   └── share/...
├── LICENSES/
├── README-R9700.md
├── BUILD_INFO.json
├── DEPENDENCIES.txt
└── SUBMODULES.txt
```

Generate archive SHA-256 values and publish a top-level `SHA256SUMS` asset.

## 14. Models are never release assets

Do not commit, upload, or redistribute model weights in AMDLucebox releases.

Specifically exclude:

- Qwen3.8-27B GGUF files,
- DFlash2 model weights,
- Hugging Face model caches,
- converted/quantized draft model files.

Provide scripts/instructions for users or the self-hosted runner to obtain/prepare them separately.

## 15. Build provenance

Every artifact must include `BUILD_INFO.json` containing at least:

```json
{
  "project": "AMDLucebox",
  "upstream_repository": "Luce-Org/lucebox",
  "upstream_commit": "FULL_SHA",
  "upstream_short_commit": "SHORT_SHA",
  "target_gpu": "AMD Radeon AI PRO R9700",
  "gpu_architecture": "RDNA4",
  "llvm_target": "gfx1201",
  "os_target": "Ubuntu 24.04",
  "architecture": "x86_64",
  "rocm_version": "10.0.0",
  "rocm_container": "rocm/dev-ubuntu-24.04:10.0.0-full",
  "rocm_container_digest": "sha256:...",
  "cmake_build_type": "Release",
  "hip_compiler": "/opt/rocm/lib/llvm/bin/clang++",
  "build_flags": [],
  "build_time_utc": "...",
  "amdlucebox_commit": "..."
}
```

Also capture:

- `hipcc --version`
- `clang++ --version`
- `cmake --version`
- recursive submodule SHAs

## 16. Static artifact verification

Before an artifact becomes releasable, run at least:

```bash
file server/build/dflash_server
ldd server/build/dflash_server
readelf -d server/build/dflash_server
```

Save relevant output in `DEPENDENCIES.txt`.

Fail if required shared libraries are unexpectedly reported as `not found` in the validation environment.

Verify the CMake cache contains the expected `gfx1201` configuration.

Where supported by the installed ROCm LLVM tools, inspect offload/code-object information to ensure generated HIP objects/libraries actually contain `gfx1201`. Apply this check to HIP-bearing shared objects such as `libggml-hip.so`, not only the server executable.

## 17. R9700 self-hosted preflight

Before running Lucebox:

1. verify `/dev/kfd` and `/dev/dri`,
2. run `rocminfo` with a hard hang guard,
3. confirm `gfx1201` is present,
4. capture GPU inventory and ROCm version,
5. compile and execute a small HIP vector-add program with `--offload-arch=gfx1201`.

Upstream Lucebox already uses this class of check on its R9700 runner; mirror that robust behavior rather than relying only on model execution.

If `rocminfo` wedges/KFD is unhealthy, fail quickly with diagnostics rather than allowing the job to consume the full timeout.

## 18. Qwen3.8 + DFlash2 validation profile

Reference target model:

- repository: `unsloth/Qwen3.8-27B-GGUF`
- model: `Qwen3.8-27B-UD-IQ4_XS.gguf`

Drafter source:

- repository: `incoai/Qwen3.8-27B-DFlash2`

Provide a helper that follows the current upstream/official conversion process to produce an appropriate DFlash2 GGUF and Q8_0 draft model. Do not assume conversion-script names forever; verify them against current upstream when implementing.

Reference launch profile:

```bash
./server/build/dflash_server \
  models/Qwen3.8-27B-UD-IQ4_XS.gguf \
  --draft models/qwen38-dflash2-q8_0.gguf \
  --draft-block-size 16 \
  --max-ctx 131072 \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --port 8216
```

Add `--target-device hip:N` only when GPU selection is required on a multi-GPU host.

## 19. Functional R9700 validation

The trusted GPU validation should cover, when model weights are staged on the runner:

1. artifact extraction,
2. runtime dependency check,
3. server process start,
4. model load,
5. `/v1/models` or equivalent readiness endpoint,
6. OpenAI-compatible completion/chat request,
7. DFlash2 speculative generation path,
8. clean server shutdown,
9. benchmark capture.

Separate lightweight no-model tests from heavy model-backed validation so normal CI does not require model downloads.

## 20. Performance baseline and regression policy

Official Lucebox R9700 Qwen3.8 reference is approximately:

- plain decode: ~32.3 tok/s
- DFlash2 block 16 HumanEval average: ~208.1 tok/s
- peak request: ~227.8 tok/s

Do not require exact reproduction in CI because clock, power, thermal state, driver, prompt, and upstream commit can vary.

Initial guardrail may be:

```text
>= 180 tok/s: PASS
170-180 tok/s: WARN
< 170 tok/s: FAIL
```

The benchmark implementation should make thresholds configurable so they can be tightened after enough local data is collected.

For ROCm 10 promotion, compare ROCm 10 and ROCm 7.2.4 using the same:

- upstream SHA,
- R9700,
- target model,
- draft model,
- prompt suite,
- DFlash block size,
- cache settings,
- context settings.

ROCm 10 should not be automatically promoted if it regresses by more than roughly 10% versus the reference under comparable conditions.

Record machine-readable benchmark results, preferably `benchmark-r9700.json`.

## 21. Release policy

Suggested tag format:

```text
lucebox-<upstream-short-sha>-r<revision>
```

Example:

```text
lucebox-298031aa-r1
```

Suggested title:

```text
Lucebox R9700 gfx1201 — upstream 298031aa
```

Scheduled workflow should resolve the current upstream SHA and exit successfully without rebuilding when that SHA already has a release, unless `force_rebuild=true`.

A build that has not passed real-R9700 validation should be published as a prerelease. A validated build may be promoted to a normal release.

If no self-hosted R9700 runner is currently configured, implementation of the validation workflow is still required; only the actual GPU execution may remain environment-blocked.

## 22. License handling

Include the upstream Lucebox license in redistributed packages.

Inspect bundled/redistributed third-party components and copy applicable license texts into `LICENSES/` without rewriting them.

Do not guess licensing obligations; derive included licenses from the actual packaged dependencies.

## 23. README requirements

The root README must explain:

- what AMDLucebox is,
- that it is a build/release wrapper rather than a Lucebox fork,
- R9700 / `gfx1201` scope,
- Ubuntu/ROCm requirements,
- ROCm 7.2.4 Reference vs ROCm 10 Candidate,
- artifact installation,
- model preparation,
- DFlash2 preparation,
- standard server launch,
- OpenAI-compatible endpoint use,
- benchmark procedure,
- troubleshooting,
- upstream commit/provenance model,
- licensing.

Explicitly recommend matching the artifact ROCm major series with the host runtime/userspace unless compatibility has been validated.

## 24. Coding and workflow rules

- Do not vendor/fork the full Lucebox source tree into this repository.
- Do not maintain unnecessary source patches against upstream.
- Keep R9700 builds pinned to `gfx1201`.
- Keep both ROCm tracks until an explicit project decision removes the reference track.
- Do not place model weights in Git or GitHub Releases.
- Never run untrusted PR code on the self-hosted R9700 runner.
- Do not expose write tokens/secrets to upstream compilation jobs.
- Pin third-party Actions to commit SHAs where practical.
- Shell scripts should use `set -euo pipefail`.
- Put reusable build/package logic in scripts rather than duplicating large shell bodies in workflow YAML.
- Update docs when behavior changes.
- Add tests for build metadata, package verification, upstream resolution, duplicate-release detection, and other deterministic wrapper logic.
- Treat CI failures as defects to investigate, not as reasons to disable checks.

## 25. Definition of done

The initial implementation is complete only when all applicable items below are satisfied:

- [ ] Root README exists and accurately documents operation.
- [ ] `docs/DESIGN.md`, `docs/RELEASE.md`, and `docs/SELF_HOSTED_RUNNER.md` are present.
- [ ] Latest upstream SHA can be resolved automatically.
- [ ] A specific upstream SHA/ref can be requested manually.
- [ ] Upstream checkout is pinned before build.
- [ ] Required dependencies/submodules are obtained reproducibly.
- [ ] ROCm 7.2.4 Reference build succeeds.
- [ ] ROCm 10.0.0 Candidate build succeeds.
- [ ] Both are explicitly compiled for `gfx1201`.
- [ ] `dflash_server` is produced and statically verified.
- [ ] Runtime dependency information is captured.
- [ ] Build provenance and submodule provenance are captured.
- [ ] SHA-256 checksums are produced.
- [ ] Versioned `.tar.zst` packages are produced.
- [ ] GitHub Actions uploads build artifacts.
- [ ] Scheduled upstream-update detection works.
- [ ] Duplicate release creation is suppressed.
- [ ] Manual force rebuild works.
- [ ] GitHub prerelease/release creation is implemented.
- [ ] Self-hosted R9700 validation workflow exists.
- [ ] Self-hosted runner cannot be invoked by untrusted PRs.
- [ ] Model weights are not committed or released.
- [ ] Required licenses are packaged.
- [ ] Workflow/shell/config tests pass.
- [ ] GitHub Actions is green for all jobs that can run in the currently available environment.

If the physical R9700 runner or staged models are unavailable, document that environmental blocker clearly; do not mark unexecuted GPU/model validation as passed.

## 26. Codex execution directive

When implementing this plan, first inspect this repository and the latest upstream `Luce-Org/lucebox` README, ROCm Dockerfile, CMake configuration, and CI. If current upstream behavior conflicts with a stale implementation detail in this document, preserve the project goals/security/reproducibility requirements while adapting to the current upstream contract.

Implement the project to completion rather than stopping after scaffolding. Add tests as features are added, run them, inspect GitHub Actions failures, fix root causes, and keep documentation synchronized. Do not wait for confirmation on routine implementation choices that can be safely resolved from the plan and current upstream source.
