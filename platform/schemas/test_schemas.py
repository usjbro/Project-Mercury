#!/usr/bin/env python3
"""Behavioural checks of the v2 task contract schema against rules the DB also enforces (platform/db/schema.sql).

Each case mutates the valid example contract; a schema that accepts what the DB refuses (or the reverse) lets a
contract pass one check and fail the other.
"""
import copy, json, os, unittest

import jsonschema

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = json.load(open(os.path.join(HERE, "task-contract.v2.schema.json")))
EXAMPLE = json.load(open(os.path.join(HERE, "example-contract-v2.json")))
H = "a" * 64


class ContractV2Dependencies(unittest.TestCase):
    """DB task_dependencies: INTERFACE_FROZEN needs path and sha256 (CHECK constraint); other states carry neither."""

    @classmethod
    def setUpClass(cls):
        jsonschema.Draft202012Validator.check_schema(SCHEMA)
        cls.v = jsonschema.Draft202012Validator(SCHEMA)

    def valid(self, dep):
        d = copy.deepcopy(EXAMPLE)
        d["dependencies"] = [dep]
        return not list(self.v.iter_errors(d))

    def test_example_is_valid(self):
        self.assertEqual(list(self.v.iter_errors(EXAMPLE)), [])

    def test_interface_frozen_with_path_and_hash(self):
        self.assertTrue(self.valid({"task_id": "MERC-0100", "required_state": "INTERFACE_FROZEN", "path": "src/ports/a.ts", "sha256": H}))

    def test_interface_frozen_needs_both(self):
        self.assertFalse(self.valid({"task_id": "MERC-0100", "required_state": "INTERFACE_FROZEN", "path": "src/ports/a.ts"}))
        self.assertFalse(self.valid({"task_id": "MERC-0100", "required_state": "INTERFACE_FROZEN", "sha256": H}))
        self.assertFalse(self.valid({"task_id": "MERC-0100", "required_state": "INTERFACE_FROZEN"}))

    def test_hash_format(self):
        self.assertFalse(self.valid({"task_id": "MERC-0100", "required_state": "INTERFACE_FROZEN", "path": "a", "sha256": "A" * 64}))

    def test_other_states_carry_neither(self):
        for st in ("COMPLETED", "AWAITING_HUMAN"):
            self.assertTrue(self.valid({"task_id": "MERC-0100", "required_state": st}))
            self.assertFalse(self.valid({"task_id": "MERC-0100", "required_state": st, "path": "a"}))
            self.assertFalse(self.valid({"task_id": "MERC-0100", "required_state": st, "sha256": H}))

    def test_interface_frozen_by_any_project_task_id(self):
        # frozen_by joins tasks.task_id in the DB; it was a v1-only DT-nnnn pattern (R6 dispositions R-4)
        for tid, ok in (("MERC-0100", True), ("DT-0001", True), ("dt-0001", False), ("MERC-01", False)):
            d = copy.deepcopy(EXAMPLE)
            d["interface_contracts"] = [{"path": "src/ports/a.ts", "sha256": H, "frozen_by": tid}]
            self.assertEqual(not list(self.v.iter_errors(d)), ok, tid)

    def test_project_level_plan_proposal_id(self):
        # doc 16 §10: project-level planner contracts use PL-<nnnn>
        d = copy.deepcopy(EXAMPLE)
        d["dependencies"] = [{"task_id": "PL-0001", "required_state": "COMPLETED"}]
        self.assertEqual(list(self.v.iter_errors(d)), [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
