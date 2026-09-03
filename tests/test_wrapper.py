from __future__ import annotations

import hashlib
import http.server
import importlib.util
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_SPEC = importlib.util.spec_from_file_location("benchmark_r9700", ROOT / "scripts/benchmark-r9700.py")
assert BENCHMARK_SPEC and BENCHMARK_SPEC.loader
BENCHMARK = importlib.util.module_from_spec(BENCHMARK_SPEC)
BENCHMARK_SPEC.loader.exec_module(BENCHMARK)
MODEL_VERIFY_SPEC = importlib.util.spec_from_file_location(
    "verify_staged_models", ROOT / "scripts/verify-staged-models.py"
)
assert MODEL_VERIFY_SPEC and MODEL_VERIFY_SPEC.loader
MODEL_VERIFY = importlib.util.module_from_spec(MODEL_VERIFY_SPEC)
MODEL_VERIFY_SPEC.loader.exec_module(MODEL_VERIFY)
ENV_CAPTURE_SPEC = importlib.util.spec_from_file_location(
    "capture_r9700_environment", ROOT / "scripts/capture-r9700-environment.py"
)
assert ENV_CAPTURE_SPEC and ENV_CAPTURE_SPEC.loader
ENV_CAPTURE = importlib.util.module_from_spec(ENV_CAPTURE_SPEC)
ENV_CAPTURE_SPEC.loader.exec_module(ENV_CAPTURE)


def run(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd or ROOT, check=check, text=True, capture_output=True)


class MatrixTests(unittest.TestCase):
    def test_matrix_has_two_immutable_gfx1201_tracks(self) -> None:
        data = json.loads((ROOT / "config/build-matrix.json").read_text())
        self.assertEqual(data["schema_version"], 1)
        tracks = data["tracks"]
        self.assertEqual({track["name"] for track in tracks}, {"reference", "candidate"})
        self.assertEqual({track["rocm_version"] for track in tracks}, {"7.2.4", "10.0.0"})
        for track in tracks:
            self.assertEqual(track["llvm_target"], "gfx1201")
            self.assertRegex(track["image_digest"], r"^sha256:[0-9a-f]{64}$")
            self.assertNotIn("@", track["image_tag"])

    def test_dockerfile_keeps_required_upstream_rocm_contract(self) -> None:
        dockerfile = (ROOT / "docker/Dockerfile.build").read_text()
        for required in (
            "ARG BASE_IMAGE", "DFLASH27B_GPU_BACKEND=hip",
            "DFLASH27B_HIP_ARCHITECTURES=${LLVM_TARGET}",
            "DFLASH27B_FA_ALL_QUANTS=OFF", "DFLASH27B_ENABLE_BSA=OFF",
            "GGML_HIP_MMQ_MFMA=ON", "GGML_HIP_NO_VMM=ON",
            "dflash_server test_dflash test_server_unit", "llvm-objdump --offloading",
        ):
            self.assertIn(required, dockerfile)
        for stale_package in ("hipblas-dev", "hipcub-dev", "rocblas-dev", "rocprim-dev", "rocwmma-dev"):
            self.assertNotIn(stale_package, dockerfile)


class ResolveTests(unittest.TestCase):
    def test_full_sha_resolution_does_not_close_ls_remote_pipe_early(self) -> None:
        script = (ROOT / "scripts/resolve-upstream.sh").read_text()
        full_sha_branch = script.split("else", 1)[0]
        self.assertNotIn("exit }", full_sha_branch)

    def test_resolves_branch_and_full_sha(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, remote = base / "source", base / "remote.git"
            run("git", "init", "--quiet", "--initial-branch=main", str(source))
            run("git", "-C", str(source), "config", "user.email", "test@example.invalid")
            run("git", "-C", str(source), "config", "user.name", "Test")
            (source / "README").write_text("fixture\n")
            run("git", "-C", str(source), "add", "README")
            run("git", "-C", str(source), "commit", "--quiet", "-m", "fixture")
            sha = run("git", "-C", str(source), "rev-parse", "HEAD").stdout.strip()
            run("git", "clone", "--quiet", "--bare", str(source), str(remote))
            for ref in ("main", sha):
                result = run(str(ROOT / "scripts/resolve-upstream.sh"), "--repository", str(remote), "--ref", ref)
                self.assertEqual(result.stdout.strip(), sha)

    def test_unknown_ref_fails(self) -> None:
        result = run(str(ROOT / "scripts/resolve-upstream.sh"), "--repository", str(ROOT), "--ref", "missing", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unable to resolve", result.stderr)


class ReleaseStateTests(unittest.TestCase):
    def test_duplicate_is_skipped_unless_forced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake_bin = Path(directory)
            gh = fake_bin / "gh"
            gh.write_text("#!/bin/sh\nexit \"${FAKE_GH_EXIT:-0}\"\n")
            gh.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
            for force, expected in (("false", "should_build=false"), ("true", "should_build=true")):
                result = subprocess.run(
                    [str(ROOT / "scripts/check-release.sh"), "--repository", "owner/repo", "--tag", "tag", "--force", force],
                    cwd=ROOT, env=environment, check=True, text=True, capture_output=True,
                )
                self.assertIn(expected, result.stdout)

    def test_missing_release_builds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake_bin = Path(directory)
            gh = fake_bin / "gh"
            gh.write_text("#!/bin/sh\nexit 1\n")
            gh.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
            result = subprocess.run(
                [str(ROOT / "scripts/check-release.sh"), "--repository", "owner/repo", "--tag", "tag", "--force", "false"],
                cwd=ROOT, env=environment, check=True, text=True, capture_output=True,
            )
            self.assertIn("release_exists=false", result.stdout)
            self.assertIn("should_build=true", result.stdout)


class PackageTests(unittest.TestCase):
    def test_package_and_verify_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            build = base / "build"
            binary = build / "server/build/dflash_server"
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/bin/sh\nexit 0\n")
            binary.chmod(0o755)
            (build / "server/scripts").mkdir()
            (build / "server/share").mkdir()
            (build / "LICENSES").mkdir()
            (build / "LICENSES/LUCEBOX-LICENSE").write_text("license\n")
            (build / "LICENSES/llama.cpp-LICENSE").write_text("license\n")
            verification = build / "verification"
            verification.mkdir()
            (verification / "DEPENDENCIES.txt").write_text("libamdhip64.so => /opt/rocm/lib/libamdhip64.so\n")
            (verification / "TOOLCHAIN.txt").write_text("HIP version\n")
            (verification / "CMAKE_CACHE.txt").write_text("CMAKE_HIP_ARCHITECTURES:STRING=gfx1201\n")
            (verification / "OFFLOAD.txt").write_text("amdgcn-amd-amdhsa--gfx1201\n")
            source = base / "source"
            run("git", "init", "--quiet", str(source))
            output = base / "out"
            sha = "a" * 40
            result = run(
                str(ROOT / "scripts/package.sh"),
                "--build-root", str(build), "--source-root", str(source),
                "--output-dir", str(output), "--track", "reference",
                "--rocm-version", "7.2.4", "--container", "example:tag",
                "--container-digest", "sha256:" + "b" * 64,
                "--upstream-sha", sha, "--amdlucebox-sha", "c" * 40,
                "--build-time", "2026-09-03T00:00:00Z",
            )
            archive = Path(result.stdout.strip())
            self.assertTrue(archive.is_file())
            checksum, name = (Path(str(archive) + ".sha256").read_text().split())
            self.assertEqual(name, archive.name)
            self.assertEqual(checksum, hashlib.sha256(archive.read_bytes()).hexdigest())
            run(str(ROOT / "scripts/verify-package.sh"), str(archive))


class BenchmarkTests(unittest.TestCase):
    def test_response_parsing_uses_server_timings(self) -> None:
        parsed = BENCHMARK.parse_response(
            {
                "usage": {
                    "completion_tokens": 180,
                    "timings": {"decode_tokens_per_sec": 205.5, "decode_ms": 875.9, "prefill_ms": 42.0},
                    "spec_decode_ran": True,
                    "accept_rate": 0.73,
                }
            },
            elapsed=1.0,
            prompt="test",
        )
        self.assertEqual(parsed["server_decode_tokens_per_second"], 205.5)
        self.assertEqual(parsed["client_e2e_tokens_per_second"], 180.0)
        self.assertEqual(parsed["prefill_milliseconds"], 42.0)
        self.assertEqual(parsed["decode_milliseconds"], 875.9)
        self.assertIs(parsed["speculative_decode_ran"], True)
        self.assertEqual(parsed["acceptance_rate"], 0.73)

    def test_missing_server_timings_and_spec_decode_fail(self) -> None:
        parsed = BENCHMARK.parse_response(
            {"usage": {"completion_tokens": 10}}, elapsed=2.0, prompt="test"
        )
        aggregate, status, reasons = BENCHMARK.summarize_runs([parsed], 180.0, 170.0)
        self.assertEqual(status, "fail")
        self.assertIsNone(aggregate["average_server_decode_tokens_per_second"])
        self.assertEqual(aggregate["speculative_decode_request_fraction"], 0.0)
        self.assertEqual(len(reasons), 2)

    def test_thresholds_and_reference_comparison_use_server_decode(self) -> None:
        def measured(server_tps: float) -> dict[str, object]:
            return {
                "server_decode_tokens_per_second": server_tps,
                "client_e2e_tokens_per_second": 999.0,
                "acceptance_rate": 0.5,
                "speculative_decode_ran": True,
            }

        aggregate, status, _ = BENCHMARK.summarize_runs([measured(175.0)], 180.0, 170.0)
        self.assertEqual(status, "warn")
        self.assertEqual(aggregate["average_server_decode_tokens_per_second"], 175.0)
        _, status, reasons = BENCHMARK.summarize_runs(
            [measured(179.9)], 180.0, 170.0, reference_tps=200.0, max_regression_percent=10.0
        )
        self.assertEqual(status, "fail")
        self.assertIn("candidate exceeded the maximum Reference regression", reasons)
        aggregate, status, _ = BENCHMARK.summarize_runs(
            [measured(180.0)], 180.0, 170.0, reference_tps=200.0, max_regression_percent=10.0
        )
        self.assertEqual(status, "pass")
        self.assertTrue(aggregate["reference_comparison"]["passed"])

    def test_benchmark_writes_machine_readable_result(self) -> None:
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers["Content-Length"])
                self.rfile.read(length)
                body = json.dumps({
                    "choices": [{"text": "ok"}],
                    "usage": {
                        "completion_tokens": 10,
                        "timings": {"decode_tokens_per_sec": 200.0, "decode_ms": 50.0, "prefill_ms": 5.0},
                        "spec_decode_ran": True,
                        "accept_rate": 0.5,
                    },
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "result.json"
                prompts = Path(directory) / "prompts.json"
                prompts.write_text('["test"]')
                run(
                    "python3", str(ROOT / "scripts/benchmark-r9700.py"),
                    "--base-url", f"http://127.0.0.1:{server.server_port}",
                    "--prompts-json", str(prompts), "--output", str(output),
                    "--pass-tps", "180", "--fail-tps", "170",
                )
                result = json.loads(output.read_text())
                self.assertEqual(result["status"], "pass")
                self.assertEqual(result["schema_version"], 2)
                self.assertEqual(result["primary_measurement"], "server_decode_tokens_per_second")
                self.assertEqual(result["aggregate"]["average_server_decode_tokens_per_second"], 200.0)
                self.assertEqual(result["runs"][0]["completion_tokens"], 10)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


class ModelEvidenceTests(unittest.TestCase):
    def test_model_launcher_records_warmups_tokens_and_live_metrics(self) -> None:
        launcher = (ROOT / "scripts/run-qwen38-r9700.sh").read_text()
        self.assertIn('--warmups "$warmups"', launcher)
        self.assertIn('--max-tokens "$max_tokens"', launcher)
        self.assertIn("scripts/sample-r9700-metrics.py", launcher)

    def test_environment_evidence_redacts_hardware_identifiers(self) -> None:
        redacted = ENV_CAPTURE.redact_hardware_identifiers(
            {"uuid": "secret", "asic": {"asic_serial": "secret", "market_name": "R9700"}}
        )
        self.assertEqual(redacted["uuid"], "REDACTED")
        self.assertEqual(redacted["asic"]["asic_serial"], "REDACTED")
        self.assertEqual(redacted["asic"]["market_name"], "R9700")

    def test_environment_capture_records_other_gpu_processes(self) -> None:
        script = (ROOT / "scripts/capture-r9700-environment.py").read_text()
        self.assertIn('"amd_smi_process"', script)
        self.assertIn('["amd-smi", "process", "--json"]', script)

    def test_staged_model_manifest_verifies_content_and_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            models = base / "models"
            models.mkdir()
            entries = []
            for role, filename, content in (
                ("target", "target.gguf", b"target model"),
                ("draft", "draft.gguf", b"draft model"),
            ):
                path = models / filename
                path.write_bytes(content)
                entries.append(
                    {
                        "role": role,
                        "filename": filename,
                        "size_bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "repository": f"example/{role}",
                        "repository_revision": role[0] * 40,
                    }
                )
            upstream = "a" * 40
            manifest = base / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "production_models": entries,
                        "conversion": {"upstream_commit": upstream},
                    }
                )
            )
            build_info = base / "BUILD_INFO.json"
            build_info.write_text(
                json.dumps(
                    {
                        "upstream_commit": upstream,
                        "llvm_target": "gfx1201",
                        "rocm_version": "7.2.4",
                    }
                )
            )
            result = MODEL_VERIFY.verify(manifest, models, build_info, "7.2.4")
            self.assertEqual(result["status"], "pass")
            self.assertEqual({item["role"] for item in result["models"]}, {"target", "draft"})
            (models / "draft.gguf").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "size mismatch"):
                MODEL_VERIFY.verify(manifest, models, build_info, "7.2.4")

    def test_model_manifest_rejects_release_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            manifest = base / "manifest.json"
            build_info = base / "BUILD_INFO.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "production_models": [],
                        "conversion": {"upstream_commit": "a" * 40},
                    }
                )
            )
            build_info.write_text(
                json.dumps(
                    {
                        "upstream_commit": "b" * 40,
                        "llvm_target": "gfx1201",
                        "rocm_version": "7.2.4",
                    }
                )
            )
            with self.assertRaisesRegex(ValueError, "upstream commits differ"):
                MODEL_VERIFY.verify(manifest, base, build_info, "7.2.4")


class WorkflowTests(unittest.TestCase):
    def test_self_hosted_validation_is_manual_only(self) -> None:
        workflow = (ROOT / ".github/workflows/validate-r9700.yml").read_text()
        trigger = workflow.split("permissions:", 1)[0]
        self.assertIn("workflow_dispatch:", trigger)
        self.assertNotIn("pull_request", trigger)
        self.assertIn("runs-on: [self-hosted, linux, x64, r9700, gfx1201]", workflow)
        self.assertIn("server/build/test_server_unit", workflow)
        self.assertIn("HIP_VISIBLE_DEVICES: ${{ inputs.hip_visible_devices }}", workflow)
        self.assertIn('default: "0"', workflow)
        self.assertIn("actions: read", workflow)
        self.assertIn("scripts/verify-staged-models.py", workflow)
        self.assertIn("scripts/capture-r9700-environment.py", workflow)
        self.assertIn("--metrics-output", workflow)
        self.assertIn("reference_run_id", workflow)
        self.assertIn("benchmark-reference-input.json", workflow)
        self.assertIn("reference-candidate-input-check.json", workflow)
        self.assertIn("retention-days: 90", workflow)

    def test_build_jobs_have_read_only_permissions(self) -> None:
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("permissions:\n      contents: read", workflow)
        self.assertIn("permissions:\n      contents: write", workflow)
        self.assertIn("scripts/check-release.sh", workflow)
        self.assertIn("schedule:", workflow)
        self.assertIn("github.event.label.name == 'full-rocm-build'", workflow)
        self.assertIn("github.event_name != 'pull_request'", workflow)
        self.assertIn("github.event_name == 'pull_request' ||", workflow)
        self.assertIn("fail-fast: true", workflow)

    def test_actions_are_pinned(self) -> None:
        for workflow in (ROOT / ".github/workflows").glob("*.yml"):
            for line in workflow.read_text().splitlines():
                if "uses:" in line:
                    reference = line.split("uses:", 1)[1].strip().split()[0]
                    self.assertRegex(reference, r"^[^@]+@[0-9a-f]{40}$", f"unpinned action in {workflow}: {line}")


if __name__ == "__main__":
    unittest.main()
