"""Artifact tests using only local files and an isolated Python subprocess."""
import contextlib
import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from apps.rag_chat.prepare_release import FILES, build_release

ROOT = Path(__file__).resolve().parents[1]


class RagReleaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.source = self.base / "repo"
        for source in FILES.values():
            path = self.source / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / source).read_bytes())
        self.output = self.base / "release"

    def test_exact_allowlist_hashes_and_sensitive_exclusion(self):
        for name in (".env", ".databrickscfg", "logs/error.log", "evaluation/private.jsonl",
                     "apps/rag_chat/.env", "src/analytics_ai/secrets.py", "src/analytics_ai/__pycache__/x.pyc"):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("sensitive-test-sentinel")
        manifest = build_release(self.source, self.output)
        actual = {p.relative_to(self.output).as_posix() for p in self.output.rglob("*") if p.is_file()}
        self.assertEqual(actual, set(FILES) | {"release.json"})
        for item in manifest["files"]:
            data = (self.output / item["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])
            self.assertEqual(len(data), item["size_bytes"])
            self.assertNotIn(b"sensitive-test-sentinel", data)
        self.assertEqual(json.loads((self.output / "release.json").read_text()), manifest)

    def test_missing_file_fails_before_writing(self):
        (self.source / "src/analytics_ai/rag_service.py").unlink()
        with self.assertRaises(ValueError):
            build_release(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_symlink_fails_before_writing(self):
        path = self.source / "src/analytics_ai/rag_service.py"
        real_is_symlink = Path.is_symlink
        patches = contextlib.nullcontext()
        try:
            outside = self.base / "outside.py"
            outside.write_bytes(path.read_bytes())
            path.unlink()
            path.symlink_to(outside)
        except OSError:
            # Windows sem modo desenvolvedor/admin não cria symlink: simula o
            # symlink no arquivo permitido, exercitando o mesmo ramo do packager.
            path.write_bytes(outside.read_bytes())
            patches = mock.patch.object(
                Path, "is_symlink", autospec=True,
                side_effect=lambda p: p == path or real_is_symlink(p))
        with patches, self.assertRaisesRegex(ValueError, "Symlink not allowed"):
            build_release(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_no_overwrite_and_reproducible_payload(self):
        first = build_release(self.source, self.output)
        with self.assertRaises(ValueError):
            build_release(self.source, self.output)
        second = build_release(self.source, self.base / "second")
        self.assertEqual(first["payload_sha256"], second["payload_sha256"])
        path = self.source / "apps/rag_chat/app.py"
        path.write_bytes(path.read_bytes() + b"\n# changed\n")
        third = build_release(self.source, self.base / "third")
        self.assertNotEqual(first["payload_sha256"], third["payload_sha256"])

    def test_imports_without_repository_or_installed_site_packages(self):
        build_release(self.source, self.output)
        script = '''
import importlib, pathlib, sys
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root))
for path in (root / "src/analytics_ai").glob("*.py"):
    module = importlib.import_module("src.analytics_ai." + path.stem)
    assert pathlib.Path(module.__file__).is_relative_to(root)
compile((root / "apps/rag_chat/app.py").read_text(encoding="utf-8"), "app.py", "exec")
'''
        subprocess.run([sys.executable, "-I", "-S", "-B", "-c", script, str(self.output)],
                       cwd=self.base, check=True, capture_output=True, text=True)

    def test_descriptor_references_packaged_entrypoint_and_resources(self):
        build_release(self.source, self.output)
        # PyYAML is intentionally not needed by the packager or its core tests.
        content = (self.output / "app.yaml").read_text(encoding="utf-8")
        self.assertIn("apps/rag_chat/app.py", content)
        self.assertIn("valueFrom: documentary-index", content)
        self.assertIn("valueFrom: generation-endpoint", content)
        self.assertNotIn("DATABRICKS_TOKEN", content)

    @unittest.skipUnless(importlib.util.find_spec("streamlit"), "Streamlit environment required")
    def test_packaged_streamlit_starts_in_isolation(self):
        build_release(self.source, self.output)
        script = """
from streamlit.testing.v1 import AppTest
import sys
app = AppTest.from_file(sys.argv[1]).run(timeout=20)
assert not app.exception, str(app.exception)
assert len(app.chat_input) == 1
assert app.session_state['interactions'] == []
"""
        subprocess.run([sys.executable, "-I", "-B", "-c", script,
                        str(self.output / "apps/rag_chat/app.py")],
                       cwd=self.base, check=True, capture_output=True, text=True, timeout=40)
