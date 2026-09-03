# AMDLucebox

AMDLucebox is a reproducible build, validation, and release wrapper for the
latest [Lucebox](https://github.com/Luce-Org/lucebox), specialized for AMD
Radeon AI PRO R9700 (`gfx1201`) on Ubuntu 24.04. It deliberately does not
vendor or maintain a fork of the Lucebox source tree.

Each release pins one exact upstream commit and builds it twice:

| Track | ROCm | Purpose |
|---|---:|---|
| Reference | 7.2.4 | comparison point for the published R9700 results |
| Candidate | 10.0.0 | production candidate evaluated against Reference |

Both tracks compile only `gfx1201`; `gfx1200` code objects are incompatible
with the R9700. Container tags and current immutable registry digests live in
[`config/build-matrix.json`](config/build-matrix.json).

## Requirements

- Linux x86_64, primarily Ubuntu 24.04
- Docker with Buildx for reproducible builds
- enough disk and memory for both ROCm builds
- an R9700 host with `/dev/kfd`, `/dev/dri`, and ROCm for runtime validation
- `python3`, Git, GNU tar, and zstd for wrapper tests and packaging

Match an artifact's ROCm major series to the host ROCm userspace unless that
specific combination has been validated. A successful build is not proof that
a different host driver/userspace combination can load the model safely.

## Build

Resolve the latest upstream commit without checking out moving `main`:

```bash
scripts/resolve-upstream.sh --ref main
```

Build either track, or pass a tag/full SHA with `--upstream-ref`:

```bash
scripts/build.sh --track reference --upstream-ref main
scripts/build.sh --track candidate --upstream-ref 298031aa4222ec61c971ed834ec8f8829ce37a5c
```

The build fetches that exact commit, initializes recursive submodules, builds
`dflash_server`, `test_dflash`, and `test_server_unit`, verifies the code object
and dependencies inside the pinned ROCm image, then writes a versioned
`.tar.zst` and checksum under `dist/<track>/`.

Every package includes `BUILD_INFO.json`, `SUBMODULES.txt`, toolchain output,
the CMake cache, offload inspection, runtime dependencies, and applicable
Lucebox/llama.cpp licenses. Verify an archive independently with:

```bash
scripts/verify-package.sh dist/reference/*.tar.zst
```

## Install and run

Extract the package without relocating its upstream-like layout:

```bash
tar --zstd -xf lucebox-r9700-rocm7.2.4-gfx1201-<sha>.tar.zst
cd lucebox-r9700
ldd server/build/dflash_server
```

Model weights are never stored in this repository or its releases. With the
Hugging Face CLI installed, prepare the public Qwen3.8 target and DFlash2 draft
against the same pinned Lucebox checkout used for the build:

```bash
scripts/prepare-qwen38.sh \
  --lucebox-source /path/to/pinned/lucebox \
  --model-dir /data1tb/LLM/AMDLucebox/qwen38
```

The helper currently uses upstream's `convert_dflash_to_gguf.py` followed by
`quantize_dflash_draft.py --scheme q8_0`. It downloads model data only to the
chosen external directory.

Launch the measured profile directly:

```bash
./server/build/dflash_server \
  /data1tb/LLM/AMDLucebox/qwen38/Qwen3.8-27B-UD-IQ4_XS.gguf \
  --draft /data1tb/LLM/AMDLucebox/qwen38/qwen38-dflash2-q8_0.gguf \
  --draft-block-size 16 --max-ctx 131072 \
  --cache-type-k q8_0 --cache-type-v q8_0 --port 8216
```

The OpenAI-compatible API can then be checked with:

```bash
curl http://127.0.0.1:8216/v1/models
curl http://127.0.0.1:8216/v1/completions \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Write a Python binary search.","max_tokens":128,"temperature":0}'
```

## R9700 validation and benchmark

Run the no-model hardware preflight first. It guards against a wedged
`rocminfo`, verifies `gfx1201`, and compiles/executes a native HIP vector add:

```bash
HIP_VISIBLE_DEVICES=0 scripts/preflight-r9700.sh r9700-diagnostics
```

For staged weights, the launcher performs readiness, completion, DFlash2, clean
shutdown, and benchmark capture:

```bash
scripts/run-qwen38-r9700.sh \
  --binary ./lucebox-r9700/server/build/dflash_server \
  --model /data1tb/LLM/AMDLucebox/qwen38/Qwen3.8-27B-UD-IQ4_XS.gguf \
  --draft /data1tb/LLM/AMDLucebox/qwen38/qwen38-dflash2-q8_0.gguf \
  --output benchmark-r9700.json
```

The initial end-to-end guardrails are PASS at 180 tok/s or above, WARN from
170 to 180 tok/s, and FAIL below 170 tok/s. Candidate results can be compared
with `--reference-results`; more than 10% regression fails. These client-side
numbers should be compared only with the same hardware, models, prompts, block
size, cache, context, power, and thermal conditions.

## Automation and security

- `ci.yml` tests wrapper code on hosted runners.
- `release.yml` checks upstream daily, suppresses an already-published commit,
  builds both pinned ROCm tracks, and publishes verified checksums/assets.
- `validate-r9700.yml` is manual-only and requires explicit trusted runner
  labels: `self-hosted`, `linux`, `x64`, `r9700`, `gfx1201`.

Fresh upstream code runs only in jobs with `contents: read`. Release publication
is a separate job with `contents: write` and does not execute upstream output.
Unvalidated builds are prereleases; a normal release must follow real R9700
validation. See [release operations](docs/RELEASE.md) and [runner setup](docs/SELF_HOSTED_RUNNER.md).
The evidence and remaining environment-bound checks for the current wrapper
revision are recorded in [validation status](docs/VALIDATION_STATUS.md).

## Troubleshooting

- `rocminfo` hangs: inspect the saved KFD holder/process/dmesg diagnostics and
  repair or reboot the host before retrying; do not let it consume the job timeout.
- wrong GPU: set `HIP_VISIBLE_DEVICES`; preflight rejects anything other than
  `gfx1201` after filtering.
- `not found` from `ldd`: use the matching ROCm series and keep the packaged
  library layout intact.
- CMake rejects an option: compare the pinned upstream README,
  `Dockerfile.rocm`, and `server/CMakeLists.txt`; update this wrapper to the
  current contract rather than dropping the feature.
- model load fails: confirm target/draft pairing, conversion from the same
  current upstream scripts, available VRAM, and host/runtime compatibility.

## Provenance and licensing

`BUILD_INFO.json` identifies the exact upstream and AMDLucebox commits, ROCm
image digest, target, flags, architecture, and build time. `SUBMODULES.txt`
pins recursive submodules. `SHA256SUMS` authenticates release downloads.

AMDLucebox redistributes no models. Artifact license texts are derived from the
components actually bundled: Lucebox and its bundled llama.cpp libraries.
External ROCm/runtime and model licenses remain with their respective sources.
See [design](docs/DESIGN.md) for the complete trust and artifact boundary.
