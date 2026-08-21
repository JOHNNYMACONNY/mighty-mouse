import json
import os
import sys
import hashlib
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from task_validator import validate_task_completeness, TaskValidationError
from tier_utils import load_tier_config, load_tier_sequence

TIER_8_SPEC = {
    "tier_name": "tier_8",
    "description": "Distributed systems, consensus, transactional storage, backpressure, and fault-tolerant retry protocols.",
    "capability_categories": [
        "DISTRIBUTED_CONSENSUS",
        "TRANSACTION_BRIDGE",
        "BACKPRESSURE_QUEUE",
        "CIRCUIT_BREAKER_FAILOVER",
        "IDEMPOTENT_RETRY_CACHE"
    ]
}

def build_tier_8_archetypes():
    return [
        # Task 2000
        {
            "id": "task_2000",
            "title": "Distributed Lock Consensus",
            "description": "Implement a distributed lock manager in distributed_lock.py. Must support acquire(key, owner, ttl_ms), release(key, owner), and extend(key, owner, ttl_ms). Must handle lock contention, ttl expiration, and re-entrancy validation. CASCADING DRIFT: Purge obsolete file ghost_lock_v1.py.",
            "expected_files": ["distributed_lock.py"],
            "deletable_files": ["ghost_lock_v1.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "distributed_lock.py": '''import time

class DistributedLockManager:
    def __init__(self):
        self.locks = {}

    def acquire(self, key, owner, ttl_ms=1000):
        now = time.time() * 1000
        if key in self.locks:
            lock = self.locks[key]
            if lock['owner'] == owner and lock['expires_at'] > now:
                lock['expires_at'] = now + ttl_ms
                return True
            if lock['expires_at'] <= now:
                self.locks[key] = {'owner': owner, 'expires_at': now + ttl_ms}
                return True
            return False
        self.locks[key] = {'owner': owner, 'expires_at': now + ttl_ms}
        return True

    def release(self, key, owner):
        now = time.time() * 1000
        if key in self.locks:
            lock = self.locks[key]
            if lock['owner'] == owner and lock['expires_at'] > now:
                del self.locks[key]
                return True
        return False

    def extend(self, key, owner, ttl_ms=1000):
        now = time.time() * 1000
        if key in self.locks:
            lock = self.locks[key]
            if lock['owner'] == owner and lock['expires_at'] > now:
                lock['expires_at'] += ttl_ms
                return True
        return False
'''
            },
            "test_script": '''import unittest
import os
import time
from distributed_lock import DistributedLockManager

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('distributed_lock.py')
        assert not os.path.exists('ghost_lock_v1.py'), 'ghost_lock_v1.py must be purged'

    def test_lock_acquire_and_release(self):
        dlm = DistributedLockManager()
        self.assertTrue(dlm.acquire("resource_1", "node_A", 500))
        self.assertFalse(dlm.acquire("resource_1", "node_B", 500))
        self.assertTrue(dlm.release("resource_1", "node_A"))
        self.assertTrue(dlm.acquire("resource_1", "node_B", 500))

    def test_lock_expiration(self):
        dlm = DistributedLockManager()
        self.assertTrue(dlm.acquire("resource_2", "node_A", 50))
        time.sleep(0.06)
        self.assertTrue(dlm.acquire("resource_2", "node_B", 100))

    def test_lock_extension(self):
        dlm = DistributedLockManager()
        self.assertTrue(dlm.acquire("resource_3", "node_A", 100))
        self.assertTrue(dlm.extend("resource_3", "node_A", 200))
        time.sleep(0.12)
        self.assertFalse(dlm.acquire("resource_3", "node_B", 100))

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 2001
        {
            "id": "task_2001",
            "title": "Transactional Storage Bridge",
            "description": "Implement a transactional storage bridge in storage_bridge.py supporting begin(), commit(), rollback(), set(k, v), get(k). Changes during an uncommitted transaction must not affect state if rolled back. CASCADING DRIFT: Purge obsolete ghost_partial_write.py.",
            "expected_files": ["storage_bridge.py"],
            "deletable_files": ["ghost_partial_write.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "storage_bridge.py": '''class StorageBridge:
    def __init__(self):
        self.store = {}
        self.transaction_stack = []

    def begin(self):
        self.transaction_stack.append({})

    def set(self, key, value):
        if self.transaction_stack:
            self.transaction_stack[-1][key] = value
        else:
            self.store[key] = value

    def get(self, key):
        for tx in reversed(self.transaction_stack):
            if key in tx:
                val = tx[key]
                if val is None:
                    return None
                return val
        return self.store.get(key)

    def delete(self, key):
        if self.transaction_stack:
            self.transaction_stack[-1][key] = None
        else:
            self.store.pop(key, None)

    def commit(self):
        if not self.transaction_stack:
            return False
        changes = self.transaction_stack.pop()
        if self.transaction_stack:
            self.transaction_stack[-1].update(changes)
        else:
            for k, v in changes.items():
                if v is None:
                    self.store.pop(k, None)
                else:
                    self.store[k] = v
        return True

    def rollback(self):
        if not self.transaction_stack:
            return False
        self.transaction_stack.pop()
        return True
'''
            },
            "test_script": '''import unittest
import os
from storage_bridge import StorageBridge

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('storage_bridge.py')
        assert not os.path.exists('ghost_partial_write.py'), 'ghost_partial_write.py must be purged'

    def test_transaction_rollback(self):
        sb = StorageBridge()
        sb.set("key1", "val1")
        sb.begin()
        sb.set("key1", "val2")
        self.assertEqual(sb.get("key1"), "val2")
        sb.rollback()
        self.assertEqual(sb.get("key1"), "val1")

    def test_transaction_commit(self):
        sb = StorageBridge()
        sb.set("key1", "v1")
        sb.begin()
        sb.set("key1", "v2")
        sb.set("key2", "v3")
        sb.commit()
        self.assertEqual(sb.get("key1"), "v2")
        self.assertEqual(sb.get("key2"), "v3")

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 2002
        {
            "id": "task_2002",
            "title": "Async Event Bus Backpressure",
            "description": "Implement BackpressureEventBus in event_bus.py. Supports publish(topic, data), subscribe(topic, callback), set_high_watermark(max_pending). Drops or raises QueueFull if pending events exceed high watermark. CASCADING DRIFT: Purge obsolete ghost_queue_v0.py.",
            "expected_files": ["event_bus.py"],
            "deletable_files": ["ghost_queue_v0.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "event_bus.py": '''class QueueFullError(Exception):
    pass

class BackpressureEventBus:
    def __init__(self, max_pending=5):
        self.max_pending = max_pending
        self.subscribers = {}
        self.pending_count = 0

    def subscribe(self, topic, callback):
        if topic not in self.subscribers:
            self.subscribers[topic] = []
        self.subscribers[topic].append(callback)

    def publish(self, topic, data):
        if self.pending_count >= self.max_pending:
            raise QueueFullError("High watermark exceeded")
        self.pending_count += 1
        try:
            for cb in self.subscribers.get(topic, []):
                cb(data)
        finally:
            self.pending_count -= 1
'''
            },
            "test_script": '''import unittest
import os
from event_bus import BackpressureEventBus, QueueFullError

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('event_bus.py')
        assert not os.path.exists('ghost_queue_v0.py')

    def test_publish_subscribe(self):
        bus = BackpressureEventBus(max_pending=3)
        received = []
        bus.subscribe("metrics", lambda d: received.append(d))
        bus.publish("metrics", {"cpu": 80})
        self.assertEqual(received, [{"cpu": 80}])

    def test_backpressure_trigger(self):
        bus = BackpressureEventBus(max_pending=1)
        def slow_cb(d):
            bus.publish("metrics", {"nested": True})
        bus.subscribe("metrics", slow_cb)
        with self.assertRaises(QueueFullError):
            bus.publish("metrics", {"start": True})

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 2003
        {
            "id": "task_2003",
            "title": "Idempotent Retry Cache",
            "description": "Implement IdempotentRetryCache in retry_cache.py. Tracks key execution results execute(key, fn, *args). If key was previously executed successfully, returns cached result without re-executing fn. CASCADING DRIFT: Purge ghost_retry_v1.py.",
            "expected_files": ["retry_cache.py"],
            "deletable_files": ["ghost_retry_v1.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "retry_cache.py": '''class IdempotentRetryCache:
    def __init__(self):
        self.cache = {}

    def execute(self, key, fn, *args, **kwargs):
        if key in self.cache:
            return self.cache[key]
        res = fn(*args, **kwargs)
        self.cache[key] = res
        return res

    def invalidate(self, key):
        return self.cache.pop(key, None) is not None
'''
            },
            "test_script": '''import unittest
import os
from retry_cache import IdempotentRetryCache

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('retry_cache.py')
        assert not os.path.exists('ghost_retry_v1.py')

    def test_idempotency_caching(self):
        cache = IdempotentRetryCache()
        counter = {"calls": 0}
        def work():
            counter["calls"] += 1
            return 42
        r1 = cache.execute("req_100", work)
        r2 = cache.execute("req_100", work)
        self.assertEqual(r1, 42)
        self.assertEqual(r2, 42)
        self.assertEqual(counter["calls"], 1)

    def test_invalidation(self):
        cache = IdempotentRetryCache()
        cache.execute("k1", lambda: "v1")
        self.assertTrue(cache.invalidate("k1"))
        self.assertFalse(cache.invalidate("k1"))

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 2004
        {
            "id": "task_2004",
            "title": "Leaky Bucket Rate Limiter",
            "description": "Implement LeakyBucketLimiter in rate_limiter.py. Constructor takes capacity and leak_rate (default 2.0). allow_request(tokens=1) returns True if bucket has space, leaking tokens over time. CASCADING DRIFT: Purge ghost_limiter_legacy.py.",
            "expected_files": ["rate_limiter.py"],
            "deletable_files": ["ghost_limiter_legacy.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "rate_limiter.py": '''import time

class LeakyBucketLimiter:
    def __init__(self, capacity=10, leak_rate=2.0):
        self.capacity = capacity
        self.leak_rate = leak_rate
        self.tokens = 0.0
        self.last_update = time.time()

    def _leak(self):
        now = time.time()
        delta = now - self.last_update
        self.last_update = now
        self.tokens = max(0.0, self.tokens - delta * self.leak_rate)

    def allow_request(self, tokens=1.0):
        self._leak()
        if self.tokens + tokens <= self.capacity:
            self.tokens += tokens
            return True
        return False
'''
            },
            "test_script": '''import unittest
import os
import time
from rate_limiter import LeakyBucketLimiter

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('rate_limiter.py')
        assert not os.path.exists('ghost_limiter_legacy.py')

    def test_bucket_capacity_enforcement(self):
        limiter = LeakyBucketLimiter(capacity=3, leak_rate=1.0)
        self.assertTrue(limiter.allow_request(2))
        self.assertTrue(limiter.allow_request(1))
        self.assertFalse(limiter.allow_request(1))

    def test_token_leakage(self):
        limiter = LeakyBucketLimiter(capacity=2, leak_rate=20.0)
        self.assertTrue(limiter.allow_request(2))
        time.sleep(0.15)
        self.assertTrue(limiter.allow_request(2))

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 2005
        {
            "id": "task_2005",
            "title": "Consistent Hash Router",
            "description": "Implement ConsistentHashRouter in hash_router.py. Supports add_node(node), remove_node(node), and get_node(key). Maps keys deterministically using MD5 hashes onto a ring. CASCADING DRIFT: Purge ghost_router_v1.py.",
            "expected_files": ["hash_router.py"],
            "deletable_files": ["ghost_router_v1.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "hash_router.py": '''import hashlib

class ConsistentHashRouter:
    def __init__(self, replicas=3):
        self.replicas = replicas
        self.ring = {}
        self.sorted_keys = []

    def _hash(self, key):
        return int(hashlib.md5(key.encode('utf-8')).hexdigest(), 16)

    def add_node(self, node):
        for i in range(self.replicas):
            vnode = f"{node}#{i}"
            h = self._hash(vnode)
            self.ring[h] = node
            self.sorted_keys.append(h)
        self.sorted_keys.sort()

    def remove_node(self, node):
        for i in range(self.replicas):
            vnode = f"{node}#{i}"
            h = self._hash(vnode)
            self.ring.pop(h, None)
            if h in self.sorted_keys:
                self.sorted_keys.remove(h)

    def get_node(self, key):
        if not self.ring:
            return None
        h = self._hash(key)
        for k in self.sorted_keys:
            if h <= k:
                return self.ring[k]
        return self.ring[self.sorted_keys[0]]
'''
            },
            "test_script": '''import unittest
import os
from hash_router import ConsistentHashRouter

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('hash_router.py')
        assert not os.path.exists('ghost_router_v1.py')

    def test_consistent_routing(self):
        router = ConsistentHashRouter(replicas=3)
        router.add_node("node_1")
        router.add_node("node_2")
        n1 = router.get_node("user_100")
        n2 = router.get_node("user_100")
        self.assertEqual(n1, n2)
        self.assertIn(n1, ["node_1", "node_2"])

    def test_node_removal(self):
        router = ConsistentHashRouter(replicas=3)
        router.add_node("server_A")
        router.add_node("server_B")
        router.remove_node("server_A")
        self.assertEqual(router.get_node("data_key"), "server_B")

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 2006
        {
            "id": "task_2006",
            "title": "WAL Log Compactor",
            "description": "Implement WALCompactor in wal_compactor.py. Supports append_log(entry_id, payload, operation=\"UPDATE\"), checkpoint(), and compact_logs(). Compaction removes overwritten update entries prior to latest checkpoint. CASCADING DRIFT: Purge ghost_wal_raw.py.",
            "expected_files": ["wal_compactor.py"],
            "deletable_files": ["ghost_wal_raw.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "wal_compactor.py": '''class WALCompactor:
    def __init__(self):
        self.entries = []
        self.last_checkpoint_index = -1

    def append_log(self, entry_id, payload, operation="UPDATE"):
        self.entries.append({"id": entry_id, "payload": payload, "op": operation})
        return len(self.entries) - 1

    def checkpoint(self):
        self.last_checkpoint_index = len(self.entries) - 1
        return self.last_checkpoint_index

    def compact_logs(self):
        if self.last_checkpoint_index < 0:
            return 0
        seen = set()
        compacted = []
        # Process entries up to checkpoint in reverse to keep latest per id
        to_process = self.entries[:self.last_checkpoint_index + 1]
        remainder = self.entries[self.last_checkpoint_index + 1:]
        for entry in reversed(to_process):
            if entry["id"] not in seen:
                seen.add(entry["id"])
                compacted.append(entry)
        compacted.reverse()
        removed = len(self.entries) - (len(compacted) + len(remainder))
        self.entries = compacted + remainder
        self.last_checkpoint_index = len(compacted) - 1
        return removed
'''
            },
            "test_script": '''import unittest
import os
from wal_compactor import WALCompactor

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('wal_compactor.py')
        assert not os.path.exists('ghost_wal_raw.py')

    def test_compaction(self):
        wal = WALCompactor()
        wal.append_log("k1", "v1")
        wal.append_log("k2", "v2")
        wal.append_log("k1", "v1_updated")
        wal.checkpoint()
        removed = wal.compact_logs()
        self.assertEqual(removed, 1)
        self.assertEqual(len(wal.entries), 2)
        self.assertEqual(wal.entries[0]["payload"], "v2")
        self.assertEqual(wal.entries[1]["payload"], "v1_updated")

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 2007
        {
            "id": "task_2007",
            "title": "Circuit Breaker State Machine",
            "description": "Implement CircuitBreaker in circuit_breaker.py with custom exception CircuitBreakerOpenError. call(fn, *args, **kwargs) executes fn and re-raises underlying exceptions; transitions between CLOSED, OPEN, and HALF_OPEN based on error thresholds and recovery timeouts, raising CircuitBreakerOpenError when OPEN. CASCADING DRIFT: Purge ghost_cb_v0.py.",
            "expected_files": ["circuit_breaker.py"],
            "deletable_files": ["ghost_cb_v0.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "circuit_breaker.py": '''import time

class CircuitBreakerOpenError(Exception):
    pass

class CircuitBreaker:
    def __init__(self, failure_threshold=2, recovery_timeout_sec=0.1):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec
        self.state = "CLOSED"
        self.failure_count = 0
        self.last_state_change = time.time()

    def call(self, fn, *args, **kwargs):
        now = time.time()
        if self.state == "OPEN":
            if now - self.last_state_change >= self.recovery_timeout_sec:
                self.state = "HALF_OPEN"
                self.last_state_change = now
            else:
                raise CircuitBreakerOpenError("Circuit is OPEN")
        try:
            res = fn(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                self.last_state_change = now
            return res
        except Exception as e:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                self.last_state_change = now
            raise e
'''
            },
            "test_script": '''import unittest
import os
import time
from circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('circuit_breaker.py')
        assert not os.path.exists('ghost_cb_v0.py')

    def test_state_transitions(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout_sec=0.05)
        def fail_fn(): raise ValueError("boom")
        def pass_fn(): return "ok"

        with self.assertRaises(ValueError): cb.call(fail_fn)
        self.assertEqual(cb.state, "CLOSED")
        with self.assertRaises(ValueError): cb.call(fail_fn)
        self.assertEqual(cb.state, "OPEN")

        with self.assertRaises(CircuitBreakerOpenError): cb.call(pass_fn)
        time.sleep(0.07)
        self.assertEqual(cb.call(pass_fn), "ok")
        self.assertEqual(cb.state, "CLOSED")

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 2008
        {
            "id": "task_2008",
            "title": "Sharded LRU Cache",
            "description": "Implement ShardedLRUCache in sharded_lru.py. Distributes keys across N shards, each with capacity K, implementing LRU eviction per shard. CASCADING DRIFT: Purge ghost_shard_v0.py.",
            "expected_files": ["sharded_lru.py"],
            "deletable_files": ["ghost_shard_v0.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "sharded_lru.py": '''from collections import OrderedDict

class ShardedLRUCache:
    def __init__(self, num_shards=2, shard_capacity=2):
        self.num_shards = num_shards
        self.shard_capacity = shard_capacity
        self.shards = [OrderedDict() for _ in range(num_shards)]

    def _get_shard_idx(self, key):
        return hash(key) % self.num_shards

    def get(self, key):
        idx = self._get_shard_idx(key)
        shard = self.shards[idx]
        if key not in shard:
            return None
        shard.move_to_end(key)
        return shard[key]

    def put(self, key, value):
        idx = self._get_shard_idx(key)
        shard = self.shards[idx]
        if key in shard:
            shard.move_to_end(key)
        shard[key] = value
        if len(shard) > self.shard_capacity:
            shard.popitem(last=False)
'''
            },
            "test_script": '''import unittest
import os
from sharded_lru import ShardedLRUCache

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('sharded_lru.py')
        assert not os.path.exists('ghost_shard_v0.py')

    def test_sharded_lru_eviction(self):
        cache = ShardedLRUCache(num_shards=1, shard_capacity=2)
        cache.put("a", 1)
        cache.put("b", 2)
        self.assertEqual(cache.get("a"), 1)
        cache.put("c", 3) # Should evict "b"
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.get("a"), 1)

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 2009
        {
            "id": "task_2009",
            "title": "Distributed Sequence Generator",
            "description": "Implement SnowflakeSequenceGenerator in seq_gen.py. Generates unique 64-bit sequence IDs combining timestamp, node_id, and sequence counter. CASCADING DRIFT: Purge ghost_seq_old.py.",
            "expected_files": ["seq_gen.py"],
            "deletable_files": ["ghost_seq_old.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "seq_gen.py": '''import time

class SnowflakeSequenceGenerator:
    def __init__(self, node_id=1):
        self.node_id = node_id & 0x3FF
        self.sequence = 0
        self.last_timestamp = -1

    def next_id(self):
        now = int(time.time() * 1000)
        if now == self.last_timestamp:
            self.sequence = (self.sequence + 1) & 0xFFF
            if self.sequence == 0:
                while now <= self.last_timestamp:
                    now = int(time.time() * 1000)
        else:
            self.sequence = 0
        self.last_timestamp = now
        return (now << 22) | (self.node_id << 12) | self.sequence
'''
            },
            "test_script": '''import unittest
import os
from seq_gen import SnowflakeSequenceGenerator

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('seq_gen.py')
        assert not os.path.exists('ghost_seq_old.py')

    def test_uniqueness_and_ordering(self):
        gen = SnowflakeSequenceGenerator(node_id=5)
        id1 = gen.next_id()
        id2 = gen.next_id()
        self.assertGreater(id2, id1)

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 2010
        {
            "id": "task_2010",
            "title": "Phi Accrual Heartbeat Detector",
            "description": "Implement HeartbeatFailureDetector in failure_detector.py with __init__(threshold=3.0), record_heartbeat(node_id) using current timestamp time.time(), and is_alive(node_id). CASCADING DRIFT: Purge ghost_hb_v0.py.",
            "expected_files": ["failure_detector.py"],
            "deletable_files": ["ghost_hb_v0.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "failure_detector.py": '''import time, math

class HeartbeatFailureDetector:
    def __init__(self, threshold=3.0):
        self.threshold = threshold
        self.heartbeats = {}

    def record_heartbeat(self, node_id):
        now = time.time()
        if node_id not in self.heartbeats:
            self.heartbeats[node_id] = []
        self.heartbeats[node_id].append(now)

    def is_alive(self, node_id):
        if node_id not in self.heartbeats or not self.heartbeats[node_id]:
            return False
        last = self.heartbeats[node_id][-1]
        elapsed = time.time() - last
        return elapsed < self.threshold
'''
            },
            "test_script": '''import unittest
import os
import time
from failure_detector import HeartbeatFailureDetector

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('failure_detector.py')
        assert not os.path.exists('ghost_hb_v0.py')

    def test_failure_detection(self):
        fd = HeartbeatFailureDetector(threshold=0.1)
        fd.record_heartbeat("node_1")
        self.assertTrue(fd.is_alive("node_1"))
        time.sleep(0.12)
        self.assertFalse(fd.is_alive("node_1"))

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 2011
        {
            "id": "task_2011",
            "title": "Vector Partition Index",
            "description": "Implement VectorIndexPartitioner in vector_index.py. Supports add_vector(vector_id, vector) and query_nearest(vector, top_k) using Euclidean distance. CASCADING DRIFT: Purge ghost_vec_old.py.",
            "expected_files": ["vector_index.py"],
            "deletable_files": ["ghost_vec_old.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "vector_index.py": '''import math

class VectorIndexPartitioner:
    def __init__(self):
        self.vectors = {}

    def add_vector(self, vector_id, vector):
        self.vectors[vector_id] = vector

    def query_nearest(self, query_vec, top_k=1):
        def dist(v1, v2):
            return math.sqrt(sum((a - b) ** 2 for a, b in zip(v1, v2)))
        scored = [(dist(query_vec, v), vid) for vid, v in self.vectors.items()]
        scored.sort()
        return [vid for _, vid in scored[:top_k]]
'''
            },
            "test_script": '''import unittest
import os
from vector_index import VectorIndexPartitioner

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('vector_index.py')
        assert not os.path.exists('ghost_vec_old.py')

    def test_vector_search(self):
        idx = VectorIndexPartitioner()
        idx.add_vector("v1", [1.0, 0.0])
        idx.add_vector("v2", [0.0, 1.0])
        res = idx.query_nearest([0.9, 0.1], top_k=1)
        self.assertEqual(res, ["v1"])

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 2012
        {
            "id": "task_2012",
            "title": "Micro-batch Pipeline Aggregator",
            "description": "Implement PipelineBatcher in pipeline_batcher.py. Batches items until batch_size is reached or flush() is called. CASCADING DRIFT: Purge ghost_batch_v0.py.",
            "expected_files": ["pipeline_batcher.py"],
            "deletable_files": ["ghost_batch_v0.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "pipeline_batcher.py": '''class PipelineBatcher:
    def __init__(self, batch_size=3):
        self.batch_size = batch_size
        self.buffer = []
        self.batches = []

    def push(self, item):
        self.buffer.append(item)
        if len(self.buffer) >= self.batch_size:
            self.flush()

    def flush(self):
        if self.buffer:
            self.batches.append(list(self.buffer))
            self.buffer.clear()
        return len(self.batches)
'''
            },
            "test_script": '''import unittest
import os
from pipeline_batcher import PipelineBatcher

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('pipeline_batcher.py')
        assert not os.path.exists('ghost_batch_v0.py')

    def test_batch_flushing(self):
        pb = PipelineBatcher(batch_size=2)
        pb.push("a")
        self.assertEqual(len(pb.batches), 0)
        pb.push("b")
        self.assertEqual(len(pb.batches), 1)
        self.assertEqual(pb.batches[0], ["a", "b"])

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 2013
        {
            "id": "task_2013",
            "title": "Quorum Replica Synchronization",
            "description": "Implement QuorumReplicaSync in replica_sync.py. Evaluates N/R/W quorum rules for reads and writes across N nodes. CASCADING DRIFT: Purge ghost_quorum_old.py.",
            "expected_files": ["replica_sync.py"],
            "deletable_files": ["ghost_quorum_old.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "replica_sync.py": '''class QuorumReplicaSync:
    def __init__(self, total_nodes=3, read_quorum=2, write_quorum=2):
        self.n = total_nodes
        self.r = read_quorum
        self.w = write_quorum
        self.nodes = [{} for _ in range(total_nodes)]

    def write(self, key, value, active_nodes):
        if len(active_nodes) < self.w:
            return False
        for idx in active_nodes[:self.w]:
            self.nodes[idx][key] = value
        return True

    def read(self, key, active_nodes):
        if len(active_nodes) < self.r:
            return None
        values = []
        for idx in active_nodes[:self.r]:
            if key in self.nodes[idx]:
                values.append(self.nodes[idx][key])
        return values[0] if values else None
'''
            },
            "test_script": '''import unittest
import os
from replica_sync import QuorumReplicaSync

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('replica_sync.py')
        assert not os.path.exists('ghost_quorum_old.py')

    def test_quorum_write_and_read(self):
        q = QuorumReplicaSync(total_nodes=3, read_quorum=2, write_quorum=2)
        self.assertFalse(q.write("k1", "v1", active_nodes=[0]))
        self.assertTrue(q.write("k1", "v1", active_nodes=[0, 1]))
        self.assertEqual(q.read("k1", active_nodes=[0, 1]), "v1")

if __name__ == '__main__':
    unittest.main()
'''
        },
        # Task 2014
        {
            "id": "task_2014",
            "title": "Token Bucket Dynamic Refill",
            "description": "Implement DynamicTokenBucket in token_bucket.py. Supports consume(tokens) and refill(rate). Handles token accumulation up to max_capacity. CASCADING DRIFT: Purge ghost_token_v0.py.",
            "expected_files": ["token_bucket.py"],
            "deletable_files": ["ghost_token_v0.py"],
            "constraints": {"language": "python", "max_files": 2},
            "reference_files": {
                "token_bucket.py": '''class DynamicTokenBucket:
    def __init__(self, max_capacity=10):
        self.max_capacity = max_capacity
        self.tokens = max_capacity

    def consume(self, count):
        if self.tokens >= count:
            self.tokens -= count
            return True
        return False

    def refill(self, amount):
        self.tokens = min(self.max_capacity, self.tokens + amount)
        return self.tokens
'''
            },
            "test_script": '''import unittest
import os
from token_bucket import DynamicTokenBucket

class TestTask(unittest.TestCase):
    def test_adherence(self):
        assert os.path.exists('token_bucket.py')
        assert not os.path.exists('ghost_token_v0.py')

    def test_consume_and_refill(self):
        tb = DynamicTokenBucket(max_capacity=5)
        self.assertTrue(tb.consume(4))
        self.assertFalse(tb.consume(2))
        tb.refill(3)
        self.assertTrue(tb.consume(2))

if __name__ == '__main__':
    unittest.main()
'''
        }
    ]

def generate_and_register_tier_8(tasks_dir="tasks/benchmark", config_path="eval/evaluation_config.json", manifest_path="eval/tier_8_manifest.json"):
    print("[*] Starting Constrained Generator-Validator Pipeline for Tier 8...")
    os.makedirs(tasks_dir, exist_ok=True)
    
    archetypes = build_tier_8_archetypes()
    validated_tasks = []
    manifest_records = []

    for task_def in archetypes:
        tid = task_def["id"]
        ref_files = task_def.pop("reference_files")
        
        print(f"[>] Validating Task {tid} ({task_def['title']})...")
        existing_dicts = [item[1] for item in validated_tasks]
        try:
            validate_task_completeness(task_def, existing_tasks=existing_dicts, reference_files=ref_files)
            print(f"  [+] Task {tid} passed all 5 negative controls & schema validation.")
        except TaskValidationError as e:
            print(f"  [!] Task {tid} FAILED validation: {e}")
            raise

        # Save task JSON
        filename = f"{tid}_{task_def['title'].lower().replace(' ', '_')}.json"
        target_path = os.path.join(tasks_dir, filename)
        with open(target_path, "w") as f:
            json.dump(task_def, f, indent=2)
        
        validated_tasks.append((filename, task_def))
        
        # Compute hashes for manifest
        test_script_hash = hashlib.sha256(task_def["test_script"].encode()).hexdigest()
        ref_hash = hashlib.sha256(json.dumps(ref_files).encode()).hexdigest()
        
        manifest_records.append({
            "task_id": tid,
            "filename": filename,
            "test_script_sha256": test_script_hash,
            "reference_sha256": ref_hash,
            "status": "VALIDATED_AND_PASSED"
        })

    # Create immutable manifest
    manifest_payload = {
        "tier": "tier_8",
        "generated_at": datetime.now().isoformat(),
        "spec": TIER_8_SPEC,
        "total_tasks": len(manifest_records),
        "manifest_hash": hashlib.sha256(json.dumps(manifest_records).encode()).hexdigest(),
        "tasks": manifest_records
    }
    
    with open(manifest_path, "w") as f:
        json.dump(manifest_payload, f, indent=2)
    print(f"[+] Immutable tier manifest created: {manifest_path}")

    # Atomic registration into evaluation_config.json
    print("[*] Registering tier_8 atomically into evaluation_config.json...")
    with open(config_path, "r") as f:
        cfg = json.load(f)
    
    if "tier_sequence" not in cfg:
        cfg["tier_sequence"] = ["tier_1", "tier_overnight", "tier_2", "tier_3", "tier_4", "tier_5", "tier_6", "tier_7"]
    
    if "tier_8" not in cfg["tier_sequence"]:
        cfg["tier_sequence"].append("tier_8")

    tier_8_filenames = [item[0] for item in validated_tasks]
    if "tiers" not in cfg:
        cfg["tiers"] = {}
    cfg["tiers"]["tier_8"] = tier_8_filenames

    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)
    
    print("[+] Tier 8 successfully registered!")
    return True

if __name__ == "__main__":
    generate_and_register_tier_8()
