# Design

## Scope and invariants

AMDLucebox turns an immutable Lucebox source commit into two independently
identified R9700 packages. It is a wrapper, not a source fork. The invariants
are:

- the upstream commit is resolved before checkout and both tracks use it;
- recursive submodules are initialized and recorded;
- all HIP compilation is explicitly `gfx1201`, never an inferred/fat target;
- ROCm tags are coupled to registry-verified immutable digests;
- models never enter the Git tree, Docker context output, or release package;
- build and package verification must succeed before publication;
- bare-metal execution occurs only on a trusted manually invoked runner.

## Data flow

`resolve-upstream.sh` resolves a branch, tag, or full SHA via the remote Git
protocol. `build.sh` creates a detached shallow checkout at that SHA, initializes
submodules, loads one track from the central matrix, and asks Buildx to export
the `artifact` stage from `Dockerfile.build`.

The builder configures current upstream CMake with HIP, `gfx1201`, upstream's
ROCm constraints, and the official R9700 MMQ/VMM flags. It builds the server and
supported tests. Still inside the matching ROCm image it captures `file`,
`ldd`, `readelf`, toolchain versions, the CMake cache, and LLVM offload data.
Missing runtime libraries or absent `gfx1201` evidence fail the build.

`package.sh` adds immutable build/submodule provenance and the license texts of
the bundled code. `verify-package.sh` validates both the directory and final
archive before generating its checksum.

## Trust boundary

Upstream source is untrusted build input. A build job has only repository read
permission and receives no publication secret or OIDC write permission. The
publication job downloads fixed-name packages, checks their hashes, and uploads
them; it does not execute their programs or scripts.

Pull requests run hosted wrapper tests only. The R9700 workflow has exclusively
`workflow_dispatch` and exact machine labels, so fork/PR code cannot enqueue on
the trusted GPU host. Model paths refer to files staged by the runner operator,
not downloaded under a repository token.

## Reproducibility limits

Source, submodule commits, container manifest, flags, and tool versions are
captured. The timestamp and AMDLucebox revision intentionally distinguish
rebuilds. Bit-for-bit equality may still be affected by compiler/build-system
nondeterminism; the archive itself normalizes ordering, ownership, and mtime.

ROCm packages are not bundled wholesale. The artifact retains upstream's
relative library layout and records dynamic requirements. Runtime validation is
therefore required on a host with a compatible ROCm series.
