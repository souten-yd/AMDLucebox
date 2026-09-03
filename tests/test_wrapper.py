from __future__ import annotations

import hashlib
import http.server
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
    def test_benchmark_writes_machine_readable_result(self) -> None:
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers["Content-Length"])
                self.rfile.read(length)
                body = json.dumps({"choices": [{"text": "ok"}], "usage": {"completion_tokens": 10}}).encode()
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
                    "--pass-tps", "0", "--fail-tps", "0",
                )
                result = json.loads(output.read_text())
                self.assertEqual(result["status"], "pass")
                self.assertEqual(result["runs"][0]["completion_tokens"], 10)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


class WorkflowTests(unittest.TestCase):
    def test_self_hosted_validation_is_manual_only(self) -> None:
        workflow = (ROOT / ".github/workflows/validate-r9700.yml").read_text()
        trigger = workflow.split("permissions:", 1)[0]
        self.assertIn("workflow_dispatch:", trigger)
        self.assertNotIn("pull_request", trigger)
        self.assertIn("runs-on: [self-hosted, linux, x64, r9700, gfx1201]", workflow)
        self.assertIn("server/build/test_server_unit", workflow)

    def test_build_jobs_have_read_only_permissions(self) -> None:
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("permissions:\n      contents: read", workflow)
        self.assertIn("permissions:\n      contents: write", workflow)
        self.assertIn("scripts/check-release.sh", workflow)
        self.assertIn("schedule:", workflow)
        self.assertIn("github.event.label.name == 'full-rocm-build'", workflow)
        self.assertIn("github.event_name != 'pull_request'", workflow)

    def test_actions_are_pinned(self) -> None:
        for workflow in (ROOT / ".github/workflows").glob("*.yml"):
            for line in workflow.read_text().splitlines():
                if "uses:" in line:
                    reference = line.split("uses:", 1)[1].strip().split()[0]
                    self.assertRegex(reference, r"^[^@]+@[0-9a-f]{40}$", f"unpinned action in {workflow}: {line}")


if __name__ == "__main__":
    unittest.main()
