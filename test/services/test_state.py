import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models import const
from app.services.state import MemoryState, RedisState


class _FakeRedis:
    def __init__(self, batches):
        self.batches = batches
        self.data = {}
        for key in [key for batch in batches for key in batch]:
            index = int(key.decode("utf-8").split(":")[-1])
            self.data[key] = {
                b"task_id": key,
                b"state": b"1",
                b"progress": str(index).encode("utf-8"),
            }

    def scan(self, cursor, count):
        batch_index = int(cursor)
        next_cursor = batch_index + 1
        if next_cursor >= len(self.batches):
            next_cursor = 0
        return next_cursor, self.batches[batch_index]

    def hgetall(self, key):
        return self.data[key]


class TestRedisState(unittest.TestCase):
    def _build_state(self, batch_sizes):
        keys = [f"task:{i}".encode("utf-8") for i in range(sum(batch_sizes))]
        batches = []
        offset = 0
        for batch_size in batch_sizes:
            batches.append(keys[offset : offset + batch_size])
            offset += batch_size

        state = RedisState.__new__(RedisState)
        state._redis = _FakeRedis(batches)
        return state

    def test_get_all_tasks_paginates_across_scan_batches(self):
        """
        Redis SCAN 分批返回 key 时，分页切片必须按当前批次起始位置计算。

        这个用例复现 PR #890 描述的 18 条任务、page_size=10 场景：
        第一批 10 条，第二批 8 条。旧逻辑第一页会返回空列表，第二页
        只返回 2 条；修复后第一页返回 10 条，第二页返回剩余 8 条。
        """
        state = self._build_state([10, 8])

        first_page, first_total = state.get_all_tasks(page=1, page_size=10)
        second_page, second_total = state.get_all_tasks(page=2, page_size=10)

        self.assertEqual(first_total, 18)
        self.assertEqual(second_total, 18)
        self.assertEqual(len(first_page), 10)
        self.assertEqual(len(second_page), 8)
        self.assertEqual(
            [task["task_id"] for task in first_page],
            [f"task:{i}" for i in range(10)],
        )
        self.assertEqual(
            [task["task_id"] for task in second_page],
            [f"task:{i}" for i in range(10, 18)],
        )


class _HashRedis:
    def __init__(self):
        self.hashes = {}

    def hset(self, name, key, value):
        bucket = self.hashes.setdefault(name, {})
        field = key.encode("utf-8") if isinstance(key, str) else key
        stored = value.encode("utf-8") if isinstance(value, str) else value
        bucket[field] = stored

    def hgetall(self, name):
        return dict(self.hashes.get(name, {}))


class TestTaskStateUpdates(unittest.TestCase):
    def test_memory_failure_keeps_progress_and_existing_fields(self):
        state = MemoryState()
        state.update_task(
            "task-1",
            state=const.TASK_STATE_PROCESSING,
            progress=40,
            script="hello",
        )

        state.update_task("task-1", state=const.TASK_STATE_FAILED, error="boom")

        task = state.get_task("task-1")
        self.assertEqual(task["state"], const.TASK_STATE_FAILED)
        self.assertEqual(task["progress"], 40)
        self.assertEqual(task["script"], "hello")
        self.assertEqual(task["error"], "boom")

    def test_memory_progress_update_keeps_state(self):
        state = MemoryState()
        state.update_task(
            "task-1",
            state=const.TASK_STATE_PROCESSING,
            progress=10,
            script="hello",
        )

        state.update_task("task-1", progress=150)

        task = state.get_task("task-1")
        self.assertEqual(task["state"], const.TASK_STATE_PROCESSING)
        self.assertEqual(task["progress"], 100)
        self.assertEqual(task["script"], "hello")

    def test_memory_bare_update_resets_task(self):
        state = MemoryState()
        state.update_task(
            "task-1",
            state=const.TASK_STATE_COMPLETE,
            progress=80,
            script="hello",
        )

        state.update_task("task-1")

        task = state.get_task("task-1")
        self.assertEqual(task["state"], const.TASK_STATE_PROCESSING)
        self.assertEqual(task["progress"], 0)
        self.assertNotIn("script", task)

    def test_redis_failure_keeps_progress(self):
        state = RedisState.__new__(RedisState)
        state._redis = _HashRedis()
        state.update_task(
            "task-1",
            state=const.TASK_STATE_PROCESSING,
            progress=40,
            script="hello",
        )

        state.update_task("task-1", state=const.TASK_STATE_FAILED, error="boom")

        task = state.get_task("task-1")
        self.assertEqual(task["state"], const.TASK_STATE_FAILED)
        self.assertEqual(task["progress"], 40)
        self.assertEqual(task["script"], "hello")
        self.assertEqual(task["error"], "boom")


if __name__ == "__main__":
    unittest.main()
