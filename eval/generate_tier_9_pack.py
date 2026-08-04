import json
import os
import sys
import hashlib
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from task_validator import validate_task_completeness, TaskValidationError
from tier_utils import load_tier_config, load_tier_sequence

TIER_9_SPEC = {
    "tier_name": "tier_9",
    "description": "Ultra-complex distributed consensus, LSM storage engines, multi-region CRDTs, 2PC coordinators, and vector indexing.",
    "capability_categories": [
        "RAFT_CONSENSUS",
        "LSM_TREE_STORAGE",
        "CRDT_SYNC",
        "TWO_PHASE_COMMIT",
        "VECTOR_INDEX"
    ]
}

def build_tier_9_archetypes():
    return [
        # Task 3000: Raft Consensus State Machine
        {
            "id": "task_3000",
            "title": "Raft Consensus State Machine",
            "description": "Implement a Raft consensus node in raft_consensus.py. Must support request_vote(term, candidate_id), append_entries(term, leader_id, entries), and get_state(). CASCADING DRIFT: Purge obsolete ghost_raft_v0.py.",
            "expected_files": ["raft_consensus.py"],
            "deletable_files": ["ghost_raft_v0.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "raft_consensus.py": '''class RaftNode:
    def __init__(self, node_id):
        self.node_id = node_id
        self.current_term = 0
        self.voted_for = None
        self.state = "follower"
        self.log = []

    def request_vote(self, term, candidate_id):
        if term > self.current_term:
            self.current_term = term
            self.voted_for = None
            self.state = "follower"
        if term == self.current_term and (self.voted_for is None or self.voted_for == candidate_id):
            self.voted_for = candidate_id
            return True, self.current_term
        return False, self.current_term

    def append_entries(self, term, leader_id, entries=None):
        if term < self.current_term:
            return False, self.current_term
        self.current_term = term
        self.state = "follower"
        if entries:
            self.log.extend(entries)
        return True, self.current_term

    def get_state(self):
        return {"term": self.current_term, "state": self.state, "log_len": len(self.log)}
'''
            },
            "test_script": '''import unittest
import os
from raft_consensus import RaftNode

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('raft_consensus.py')
        assert not os.path.exists('ghost_raft_v0.py'), 'ghost_raft_v0.py must be purged'

    def test_vote_and_append(self):
        node = RaftNode("node_1")
        granted, term = node.request_vote(1, "candidate_A")
        self.assertTrue(granted)
        self.assertEqual(term, 1)

        ok, term = node.append_entries(1, "candidate_A", ["cmd1"])
        self.assertTrue(ok)
        self.assertEqual(node.get_state()["log_len"], 1)

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 3001: Log Structured Merge Tree
        {
            "id": "task_3001",
            "title": "Log Structured Merge Tree",
            "description": "Implement an LSM tree in lsm_tree.py with put(key, val), get(key), flush_memtable(), and compact(). CASCADING DRIFT: Purge obsolete ghost_lsm_v0.py.",
            "expected_files": ["lsm_tree.py"],
            "deletable_files": ["ghost_lsm_v0.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "lsm_tree.py": '''class LSMTree:
    def __init__(self, memtable_limit=3):
        self.memtable_limit = memtable_limit
        self.memtable = {}
        self.sstables = []

    def put(self, key, val):
        self.memtable[key] = val
        if len(self.memtable) >= self.memtable_limit:
            self.flush_memtable()

    def get(self, key):
        if key in self.memtable:
            return self.memtable[key]
        for sstable in reversed(self.sstables):
            if key in sstable:
                return sstable[key]
        return None

    def flush_memtable(self):
        if self.memtable:
            self.sstables.append(dict(self.memtable))
            self.memtable.clear()

    def compact(self):
        merged = {}
        for sstable in self.sstables:
            merged.update(sstable)
        self.sstables = [merged]
'''
            },
            "test_script": '''import unittest
import os
from lsm_tree import LSMTree

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('lsm_tree.py')
        assert not os.path.exists('ghost_lsm_v0.py'), 'ghost_lsm_v0.py must be purged'

    def test_lsm_ops(self):
        lsm = LSMTree(memtable_limit=2)
        lsm.put("k1", "v1")
        lsm.put("k2", "v2")
        lsm.put("k3", "v3")
        self.assertEqual(lsm.get("k1"), "v1")
        self.assertEqual(lsm.get("k3"), "v3")
        lsm.compact()
        self.assertEqual(len(lsm.sstables), 1)

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 3002: Multi-Region CRDT Sync
        {
            "id": "task_3002",
            "title": "Multi Region CRDT Sync",
            "description": "Implement a PN-Counter CRDT in crdt_sync.py with increment(replica_id), decrement(replica_id), value(), and merge(other_crdt). CASCADING DRIFT: Purge obsolete ghost_crdt_v0.py.",
            "expected_files": ["crdt_sync.py"],
            "deletable_files": ["ghost_crdt_v0.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "crdt_sync.py": '''class PNCounter:
    def __init__(self):
        self.p_vector = {}
        self.n_vector = {}

    def increment(self, replica_id, count=1):
        self.p_vector[replica_id] = self.p_vector.get(replica_id, 0) + count

    def decrement(self, replica_id, count=1):
        self.n_vector[replica_id] = self.n_vector.get(replica_id, 0) + count

    def value(self):
        return sum(self.p_vector.values()) - sum(self.n_vector.values())

    def merge(self, other):
        for r, cnt in other.p_vector.items():
            self.p_vector[r] = max(self.p_vector.get(r, 0), cnt)
        for r, cnt in other.n_vector.items():
            self.n_vector[r] = max(self.n_vector.get(r, 0), cnt)
'''
            },
            "test_script": '''import unittest
import os
from crdt_sync import PNCounter

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('crdt_sync.py')
        assert not os.path.exists('ghost_crdt_v0.py'), 'ghost_crdt_v0.py must be purged'

    def test_crdt_merge(self):
        c1 = PNCounter()
        c2 = PNCounter()
        c1.increment("us-east", 5)
        c2.decrement("eu-west", 2)
        c1.merge(c2)
        self.assertEqual(c1.value(), 3)

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 3003: Two Phase Commit Coordinator
        {
            "id": "task_3003",
            "title": "Two Phase Commit Coordinator",
            "description": "Implement a 2PC coordinator in two_phase_commit.py with prepare(participants), commit(), and rollback(). CASCADING DRIFT: Purge obsolete ghost_2pc_v0.py.",
            "expected_files": ["two_phase_commit.py"],
            "deletable_files": ["ghost_2pc_v0.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "two_phase_commit.py": '''class TwoPhaseCoordinator:
    def __init__(self):
        self.state = "INIT"
        self.participants = []

    def prepare(self, participants):
        self.participants = participants
        self.state = "PREPARING"
        votes = [p.vote_prepare() for p in participants]
        if all(votes):
            self.state = "PREPARED"
            return True
        else:
            self.state = "ABORTING"
            self.rollback()
            return False

    def commit(self):
        if self.state != "PREPARED":
            return False
        for p in self.participants:
            p.do_commit()
        self.state = "COMMITTED"
        return True

    def rollback(self):
        for p in self.participants:
            p.do_rollback()
        self.state = "ABORTED"
        return True
'''
            },
            "test_script": '''import unittest
import os
from two_phase_commit import TwoPhaseCoordinator

class DummyParticipant:
    def __init__(self, will_pass=True):
        self.will_pass = will_pass
        self.committed = False
        self.rolled_back = False
    def vote_prepare(self): return self.will_pass
    def do_commit(self): self.committed = True
    def do_rollback(self): self.rolled_back = True

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('two_phase_commit.py')
        assert not os.path.exists('ghost_2pc_v0.py'), 'ghost_2pc_v0.py must be purged'

    def test_2pc_commit_flow(self):
        p1, p2 = DummyParticipant(True), DummyParticipant(True)
        coord = TwoPhaseCoordinator()
        self.assertTrue(coord.prepare([p1, p2]))
        self.assertTrue(coord.commit())
        self.assertTrue(p1.committed and p2.committed)

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 3004: Vector HNSW Index Search
        {
            "id": "task_3004",
            "title": "Vector HNSW Index Search",
            "description": "Implement a Euclidean vector index in vector_index.py with add(vector_id, vector) and search(query_vector, top_k). CASCADING DRIFT: Purge obsolete ghost_hnsw_v0.py.",
            "expected_files": ["vector_index.py"],
            "deletable_files": ["ghost_hnsw_v0.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "vector_index.py": '''import math

class VectorIndex:
    def __init__(self):
        self.vectors = {}

    def add(self, vector_id, vector):
        self.vectors[vector_id] = vector

    def search(self, query_vector, top_k=1):
        results = []
        for vid, vec in self.vectors.items():
            dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(query_vector, vec)))
            results.append((vid, dist))
        results.sort(key=lambda x: x[1])
        return results[:top_k]
'''
            },
            "test_script": '''import unittest
import os
from vector_index import VectorIndex

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('vector_index.py')
        assert not os.path.exists('ghost_hnsw_v0.py'), 'ghost_hnsw_v0.py must be purged'

    def test_vector_search(self):
        vi = VectorIndex()
        vi.add("v1", [1.0, 0.0])
        vi.add("v2", [0.0, 1.0])
        res = vi.search([0.9, 0.1], top_k=1)
        self.assertEqual(res[0][0], "v1")

if __name__ == '__main__':
    unittest.main()
'''
        }
    ]


def generate_and_register_tier_9(tasks_dir="tasks/benchmark", config_path="eval/evaluation_config.json", manifest_path="eval/tier_9_manifest.json"):
    print("[*] Starting Constrained Generator-Validator Pipeline for Tier 9...")
    os.makedirs(tasks_dir, exist_ok=True)
    
    archetypes = build_tier_9_archetypes()
    validated_tasks = []
    manifest_records = []

    for task_def in archetypes:
        tid = task_def["id"]
        ref_files = task_def.pop("reference_files")
        
        print(f"[>] Validating Task {tid} ({task_def['title']})...")
        existing_dicts = [item[1] for item in validated_tasks]
        try:
            validate_task_completeness(task_def, existing_tasks=existing_dicts, reference_files=ref_files)
            print(f"  [+] Task {tid} passed all negative controls & schema validation.")
        except TaskValidationError as e:
            print(f"  [!] Task {tid} FAILED validation: {e}")
            raise

        filename = f"{tid}_{task_def['title'].lower().replace(' ', '_')}.json"
        target_path = os.path.join(tasks_dir, filename)
        with open(target_path, "w") as f:
            json.dump(task_def, f, indent=2)
        
        validated_tasks.append((filename, task_def))
        
        test_script_hash = hashlib.sha256(task_def["test_script"].encode()).hexdigest()
        ref_hash = hashlib.sha256(json.dumps(ref_files).encode()).hexdigest()
        
        manifest_records.append({
            "task_id": tid,
            "filename": filename,
            "test_script_sha256": test_script_hash,
            "reference_sha256": ref_hash,
            "status": "VALIDATED_AND_PASSED"
        })

    manifest_payload = {
        "tier": "tier_9",
        "generated_at": datetime.now().isoformat(),
        "spec": TIER_9_SPEC,
        "total_tasks": len(manifest_records),
        "manifest_hash": hashlib.sha256(json.dumps(manifest_records).encode()).hexdigest(),
        "tasks": manifest_records
    }
    
    with open(manifest_path, "w") as f:
        json.dump(manifest_payload, f, indent=2)
    print(f"[+] Immutable tier manifest created: {manifest_path}")

    print("[*] Registering tier_9 atomically into evaluation_config.json...")
    with open(config_path, "r") as f:
        cfg = json.load(f)
    
    if "tier_sequence" not in cfg:
        cfg["tier_sequence"] = ["tier_1", "tier_overnight", "tier_2", "tier_3", "tier_4", "tier_5", "tier_6", "tier_7", "tier_8"]
    
    if "tier_9" not in cfg["tier_sequence"]:
        cfg["tier_sequence"].append("tier_9")

    tier_9_filenames = [item[0] for item in validated_tasks]
    if "tiers" not in cfg:
        cfg["tiers"] = {}
    cfg["tiers"]["tier_9"] = tier_9_filenames

    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)
    
    print("[+] Tier 9 successfully registered!")
    return True


if __name__ == "__main__":
    generate_and_register_tier_9()
