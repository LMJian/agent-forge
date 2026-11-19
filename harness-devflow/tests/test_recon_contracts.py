"""Executable recon-case facts/counterexamples, not model investigation quality tests."""
import copy
import json
from pathlib import Path
import unittest


CASES = Path(__file__).resolve().parents[1] / "skills/brownfield-recon/evals/cases.json"


class ReconContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = json.loads(CASES.read_text())["cases"]
        cls.cases = {row["id"]: row for row in rows}
        if len(rows) != len(cls.cases):
            raise AssertionError("Duplicate recon evaluation IDs")

    def code(self, case, file):
        namespace = {}
        exec(compile(self.cases[case]["files"][file], file, "exec"), namespace)
        return namespace

    def test_actual_batch_accepts_distinct_timestamps(self):
        case = self.cases["payload-consumer-boundary"]
        decode = self.code(case["id"], "consumer.py")["decode"]
        request = json.loads(case["files"]["request.json"])
        items, deleted = decode(request)
        self.assertNotEqual(request["occurred_ms"], items[0]["end_ms"])
        self.assertEqual((len(items), deleted), (1, ["s0"]))

    def test_deletion_only_is_valid_but_reversed_sample_range_is_not(self):
        decode = self.code("payload-consumer-boundary", "consumer.py")["decode"]
        self.assertEqual(decode({"occurred_ms":2000,"data_json":json.dumps({"deleted_ids":["s0"]})}), ([], ["s0"]))
        with self.assertRaisesRegex(ValueError, "sample time"):
            decode({"occurred_ms":2000,"data_json":json.dumps({"items":[{"start_ms":2,"end_ms":1}]})})

    def test_configured_session_step_precedes_feature_gate(self):
        case = self.cases["configured-entry-and-mapping"]
        code = self.code(case["id"], "entry.py")
        config = json.loads(case["files"]["config.json"])
        self.assertEqual(code["handle"]("/v1/jobs", 7, config), "login invalid")
        configured = {**config, "parse_session_paths":["/v1/jobs"]}
        self.assertEqual(code["handle"]("/v1/jobs", 7, configured), [])
        self.assertEqual(code["forward"]({"common.user_id":7,"common.device_id":"D"}, config["mapping"]),
                         {"user_id":7,"device_id":"D"})

    def test_extra_state_cost_grows_with_fanout_and_runner_is_process_local(self):
        code = self.code("mechanism-and-work-budget", "pipeline.py")
        for count in (0, 1, 10):
            with self.subTest(fanout=count):
                base, extra, runner = code["Store"](), code["Store"](), code["Runner"]()
                subscriptions = [str(i) for i in range(count)]
                code["deliver"]("event", subscriptions, base, runner)
                code["deliver"]("event", subscriptions, extra, runner, extra_state=True)
                self.assertEqual(extra.writes-base.writes, 2+4*count)
                self.assertEqual(extra.bytes-base.bytes, 2+4*count)
                self.assertEqual(runner.executions, count)
                restarted = code["Runner"]()
                code["deliver"]("event", subscriptions, code["Store"](), restarted)
                self.assertEqual(restarted.executions, count)  # IDs alone do not make this durable.

    def test_nested_retries_and_replica_scan_must_be_counted_together(self):
        code = self.code("mechanism-and-work-budget", "pipeline.py")
        attempts = []
        def timeout():
            attempts.append(1)
            raise TimeoutError("unknown result")
        with self.assertRaises(TimeoutError):
            code["send_with_retries"](timeout)
        self.assertEqual(len(attempts), 9)
        self.assertEqual(code["scan"](list(range(5)), 4), 20)

    def test_deleted_task_and_unsubscribe_success_are_different_states(self):
        case = self.cases["task-and-shared-resource-lifecycle"]
        code = self.code(case["id"], "lifecycle.py")
        state = copy.deepcopy(json.loads(case["files"]["state.json"]))
        def gateway(sub):
            if sub == "s1": state["subscriptions"][sub]["active"] = False; return 204
            return 503
        self.assertEqual(code["cancel_task"]("t1", state["tasks"], state["subscriptions"], gateway), {"code":0})
        self.assertEqual(code["active_watches"](state["subscriptions"]), {"w1"})
        self.assertEqual(code["cancel_task"]("t2", state["tasks"], state["subscriptions"], gateway), {"code":0})
        self.assertFalse(state["tasks"])
        self.assertTrue(state["subscriptions"]["s2"]["active"])
        self.assertEqual(code["active_watches"](state["subscriptions"]), {"w1"})

    def test_async_receipt_has_other_log_id_and_no_device_apply_evidence(self):
        files = self.cases["async-runtime-correlation"]["files"]
        logs, query = json.loads(files["logs.json"]), json.loads(files["query.json"])
        self.assertEqual((query["rows"], query["coverage"], query["timeout"]), (0, "partial", True))
        receipt = next(x for x in logs if x["op"] == "SendCMD")
        self.assertNotEqual(receipt["log_id"], query["filter"]["log_id"])
        self.assertEqual((receipt["device"], receipt["revision"], receipt["result"]), ("D1", 7, "accepted"))
        self.assertNotEqual(logs[0]["requested_env"], logs[0]["runtime_env"])
        self.assertNotIn("applied", {x["op"] for x in logs})  # Only absence in this provided snapshot.


if __name__ == "__main__":
    unittest.main()
