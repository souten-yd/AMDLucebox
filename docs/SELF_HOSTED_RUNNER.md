# R9700 self-hosted runner

## Required host

- Ubuntu 24.04 x86_64
- AMD Radeon AI PRO R9700 visible as `gfx1201`
- working `/dev/kfd` and `/dev/dri`
- `/opt/rocm/bin/rocminfo` and `/opt/rocm/bin/hipcc`
- curl, GitHub CLI, Python 3, GNU tar/zstd, `ldd`, and SHA-256 tools
- enough storage for extracted packages, logs, and operator-staged models

Assign all labels exactly: `self-hosted`, `linux`, `x64`, `r9700`, `gfx1201`.
Use a dedicated non-root service account in the `render` and `video` groups.
Do not give the runner general repository administration credentials.

## Security boundary

Repository policy and labels are defense in depth; the workflow definition is
the primary boundary. `validate-r9700.yml` must remain manual-only. Never add a
`pull_request`/`pull_request_target` trigger or make it callable from an
untrusted build workflow. Review changes to the validation script before using
the host.

The runner downloads already-published packages with read permission. It does
not compile arbitrary PR source. Model weights are staged separately by the
operator under a path such as `/var/lib/amdlucebox/models/qwen38` and must never
be placed in the Actions workspace or uploaded as evidence.

## Initial acceptance

Run locally as the runner service account:

```bash
HIP_VISIBLE_DEVICES=0 ./scripts/preflight-r9700.sh /tmp/r9700-diagnostics
```

Acceptance requires `rocminfo` to return promptly, report `gfx1201`, and the
compiled vector-add to execute on that device. A source listing or `/dev/kfd`
presence alone is insufficient.

For model-backed validation, stage:

```text
/var/lib/amdlucebox/models/qwen38/
├── Qwen3.8-27B-UD-IQ4_XS.gguf
└── qwen38-dflash2-q8_0.gguf
```

Confirm ownership permits read access only as intended. Use the manual workflow
first with `model_backed=false`, then once with `model_backed=true`. Preserve
the uploaded diagnostic, runtime-link, server-log, and benchmark JSON evidence.

## KFD recovery

The preflight backgrounds `rocminfo` because a process in uninterruptible sleep
cannot be killed by ordinary `timeout`. On a 15-second hang it captures process
state, `/dev/kfd` holders, and recent amdgpu/KFD messages before failing. Repair
or reboot the host; do not retry repeatedly against the same wedged kernel.
