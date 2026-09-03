# Lucebox for Radeon AI PRO R9700

This package was built by AMDLucebox from the exact Lucebox commit recorded in
`BUILD_INFO.json`. It contains no model weights.

Use Ubuntu 24.04 with a host ROCm userspace matching the artifact's ROCm major
series unless that combination has been validated separately. Confirm that
`rocminfo` reports `gfx1201`, then follow the model preparation and launch
instructions in the AMDLucebox root README. Runtime library diagnostics from
the build environment are recorded in `DEPENDENCIES.txt`.

The primary executable is `server/build/dflash_server`. Its bundled shared
libraries retain the upstream build layout and relative RPATHs.
