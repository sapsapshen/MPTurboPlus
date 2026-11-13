import json
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.controllers.manager.base_manager import TaskQueueFullError
from app.controllers.manager.memory_manager import InMemoryTaskManager
from app.controllers.manager.redis_manager import RedisTaskManager, build_redis_url
from app.models.schema import VideoParams
from app.services import task as tm


class TestInMemoryTaskManager(unittest.TestCase):
    def test_concurrency_slot_is_reserved_before_the_worker_runs(self):
        started = threading.Event()
        release = threading.Event()
        second_started = threading.Event()

        def first():
            started.set()
            release.wait(2)

        def second():
            second_started.set()

        manager = InMemoryTaskManager(max_concurrent_tasks=1, max_queued_tasks=1)
        try:
            manager.add_task(first)
            self.assertTrue(started.wait(2))
            self.assertEqual(manager.current_tasks, 1)

            manager.add_task(second)
            self.assertEqual(manager.queue_size(), 1)
            self.assertFalse(second_started.is_set())

            with self.assertRaises(TaskQueueFullError):
                manager.add_task(lambda: None)
        finally:
            release.set()

        self.assertTrue(second_started.wait(2))
        deadline = time.time() + 2
        while manager.current_tasks and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual(manager.current_tasks, 0)
        self.assertTrue(manager.is_queue_empty())

    def test_failed_task_releases_the_concurrency_slot(self):
        done = threading.Event()

        def boom():
            raise RuntimeError("boom")

        def follow_up():
            done.set()

        manager = InMemoryTaskManager(max_concurrent_tasks=1, max_queued_tasks=1)
        manager.add_task(boom)
        manager.add_task(follow_up)

        self.assertTrue(done.wait(2))
        deadline = time.time() + 2
        while manager.current_tasks and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual(manager.current_tasks, 0)


class _FakeRedis:
    def __init__(self):
        self.items = []

    def rpush(self, key, value):
        self.items.append(value)


class TestRedisTaskQueue(unittest.TestCase):
    def test_build_redis_url_omits_empty_password_and_quotes_special_characters(self):
        self.assertEqual(
            build_redis_url("localhost", 6379, 0, None),
            "redis://localhost:6379/0",
        )
        self.assertEqual(
            build_redis_url("localhost", 6379, 0, ""),
            "redis://localhost:6379/0",
        )
        self.assertEqual(
            build_redis_url("localhost", 6379, 0, "p@ss"),
            "redis://:p%40ss@localhost:6379/0",
        )

    def test_enqueue_serializes_video_params_with_model_dump(self):
        manager = RedisTaskManager.__new__(RedisTaskManager)
        manager.queue = "task_queue"
        manager.redis_client = _FakeRedis()
        params = VideoParams(video_subject="海浪")

        manager.enqueue({"func": tm.start, "args": (), "kwargs": {"params": params}})

        payload = json.loads(manager.redis_client.items[0])
        self.assertEqual(payload["func"], "start")
        self.assertEqual(payload["kwargs"]["params"]["video_subject"], "海浪")


if __name__ == "__main__":
    unittest.main()
