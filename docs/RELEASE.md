# Release operations

## Automatic and manual builds

The release workflow runs daily and may also be dispatched manually. Scheduled
runs resolve upstream `main`. Manual runs accept a branch, tag, or full commit,
an integer package revision, and `force_rebuild`.

The tag is `lucebox-<8-char-upstream-sha>-r<revision>`. If it already exists,
the workflow exits successfully before either expensive ROCm build unless force
rebuild was explicitly requested. Force rebuild replaces assets for that exact
tag; increment the revision when the wrapper or packaging contract changed.

For pre-merge acceptance, a maintainer may add the `full-rocm-build` label to a
pull request. That explicit label runs the same hosted, read-only build jobs but
the publication job is disabled for pull-request events. Remove and re-add the
label only when a new full build is genuinely needed.

Build jobs run the Reference and Candidate tracks from the same resolved SHA.
They upload short-lived Actions artifacts only after static verification. The
publication job validates their checksums, creates `SHA256SUMS`, and publishes
the GitHub release.

## Validation and promotion

The default release is a prerelease. Dispatch `Validate release on R9700` for
each applicable track. Lightweight validation always checks KFD, device
identity, native HIP execution, archive integrity, and host dependencies.
Enable model-backed validation only after the operator has staged the exact
Qwen3.8 and converted DFlash2 files.

Compare Candidate with Reference using the same upstream SHA, machine, weights,
prompts, context/cache settings, clocks, and power/thermal state. Do not promote
ROCm 10 if it regresses by more than 10% or fails functional validation.

After successful evidence review, dispatch the dedicated `Promote validated
release in place` workflow from trusted `main`. It verifies the existing
package/checksum asset hashes, accepted Reference and Candidate runs, identical
models/settings, and the Candidate regression gate; it then attaches the
non-secret evidence bundle and changes only the existing release metadata to
`prerelease=false`.

The build workflow always publishes prereleases. It cannot promote a release,
and it refuses to force-rebuild a release that is already stable. Never use a
rebuild to clear the prerelease flag: a rebuild changes artifact identity and
invalidates the model-backed evidence.

## Updating a container digest

1. Resolve the current tag at Docker Hub with an OCI/Docker manifest accept
   header and record the returned `Docker-Content-Digest`.
2. Confirm the tag and digest are for the intended Ubuntu/ROCm track.
3. Update only `config/build-matrix.json`.
4. Run wrapper tests and a real build before merging.
5. Record the new digest through normal Git history; do not copy a stale digest
   from prose documentation.

## Failure handling

Investigate Actions failures as product defects. Cancel superseded or clearly
unnecessary runs immediately, but do not disable a failing gate. Prefer all
deterministic local checks before pushing. A wedged self-hosted KFD should fail
quickly with diagnostics and be repaired before a single controlled rerun.
