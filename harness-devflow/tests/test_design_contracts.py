"""Execute synthetic design-case contracts; this is not a generated-prose/model eval."""
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest


CASES = Path(__file__).resolve().parents[1] / "skills/server-tech-design/evals/cases.json"


class DesignContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = json.loads(CASES.read_text())["cases"]
        cls.cases = {row["id"]: row for row in rows}
        if len(cls.cases) != len(rows):
            raise AssertionError("Duplicate evaluation case IDs")

    def receive(self):
        with tempfile.TemporaryDirectory(prefix="design-wire-") as directory:
            source = Path(directory) / "transport.py"
            source.write_text(self.cases["push-wire-contract"]["files"]["transport.py"])
            return runpy.run_path(str(source))

    def test_wire_encoder_is_application_json_despite_proto_model(self):
        codec = self.receive()
        delta = {"revision": 2, "upserts": [{"id": "a"}], "deleted_ids": ["b"]}
        meta = codec["encode_meta"](delta)
        self.assertIsInstance(meta, bytes)
        self.assertEqual(json.loads(meta.decode("utf-8")), delta)
        # A protobuf field header is not a valid substitute for the implemented JSON.
        with self.assertRaises((ValueError, UnicodeError)):
            codec["receive"](b"\x08\x02", 1, {})

    def test_delta_preserves_unmentioned_rules_instead_of_replacing_everything(self):
        codec = self.receive()
        original = {"keep": {"id": "keep"}, "delete": {"id": "delete"}}
        meta = codec["encode_meta"]({"revision": 2, "upserts": [{"id": "add"}], "deleted_ids": ["delete"]})
        status, revision, rules = codec["receive"](meta, 1, original)
        self.assertEqual((status, revision, set(rules)), ("applied", 2, {"keep", "add"}))
        self.assertEqual(set(original), {"keep", "delete"})
        self.assertNotEqual(set(rules), {"add"})  # Reject the full-replacement explanation.

    def test_nonconsecutive_revision_requests_pull_without_advancing_or_clearing(self):
        codec = self.receive()
        original = {"keep": {"id": "keep"}}
        for revision in (1, 3):
            with self.subTest(revision=revision):
                meta = codec["encode_meta"]({"revision": revision, "upserts": [], "deleted_ids": ["keep"]})
                self.assertEqual(codec["receive"](meta, 1, original), ("pull", 1, original))

    def test_worker_instances_do_not_create_additional_consumer_groups(self):
        config = json.loads(self.cases["mq-topology-contract"]["files"]["consumers.json"])
        groups = {entry["group"] for entry in config["consumers"]}
        instances = sum(entry["instances"] for entry in config["consumers"])
        self.assertEqual((config["topic"], groups, instances, config["lane_suffix"]),
                         ("jobs.events", {"cg_job_worker"}, 2, False))
        self.assertNotEqual(len(groups), instances)

    def test_login_precedes_disabled_feature_and_acl_is_not_effective(self):
        files = self.cases["complete-integration-contract"]["files"]
        namespace = {}
        exec(compile(files["handler.py"], "handler.py", "exec"), namespace)
        from types import SimpleNamespace
        handler = namespace["client_handler"]
        disabled = SimpleNamespace(enabled=False)
        self.assertEqual(handler(SimpleNamespace(user_id=None), disabled), "login invalid")
        self.assertEqual(handler(SimpleNamespace(user_id=7), disabled), [])
        routes = json.loads(files["routes.json"])
        self.assertEqual([r["login_required"] for r in routes["routes"]], [True, False])
        self.assertEqual(routes["rpc"]["acl_status"], "submitted")

    @unittest.skipUnless(shutil.which("go"), "Go fixture serialization not checked: local Go unavailable")
    def test_storage_struct_serializes_nesting_optional_zero_and_ttl(self):
        source = self.cases["nested-storage-contract"]["files"]["store.go"]
        source = source.replace("package sample", "package main", 1).replace(
            'import "time"', 'import ("time"; "encoding/json"; "fmt")', 1)
        source += '''
func main() {
 zero := int64(0)
 record := Record{Revision:7, Jobs:map[string]Job{
  "absent": {Labels:[]string{"a"}}, "zero": {Labels:[]string{}, DeadlineMS:&zero},
 }}
 data, err := json.Marshal(map[string]any{"key":Key("tenant", "job"), "ttl_ms":RecordTTL.Milliseconds(), "value":record})
 if err != nil { panic(err) }; fmt.Println(string(data))
}
'''
        with tempfile.TemporaryDirectory(prefix="design-storage-") as directory:
            path = Path(directory) / "main.go"
            path.write_text(source)
            env = {**os.environ, "GOTOOLCHAIN": "local", "GOWORK": "off", "GOPROXY": "off", "GO111MODULE": "off"}
            result = subprocess.run([shutil.which("go"), "run", str(path)], cwd=directory,
                                    env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"key": "job:tenant:job", "ttl_ms":86400000,
            "value":{"revision":7,"jobs":{"absent":{"labels":["a"]},"zero":{"labels":[],"deadline_ms":0}}}})


if __name__ == "__main__":
    unittest.main()
