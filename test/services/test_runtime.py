import json
import socket
import sys
import unittest
from pathlib import Path

from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import start_helper
from app.asgi import app, resolve_cors_settings, validation_exception_handler
from app.services.subtitle import normalize_whisper_option
from app.utils import file_security, utils


class TestRuntimeGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_ping_is_plain_text_and_not_shadowed_by_static_files(self):
        response = self.client.get("/ping")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "pong")
        self.assertIn("text/plain", response.headers["content-type"])

    def test_validation_error_names_the_missing_field(self):
        response = self.client.post("/api/v1/videos", json={})

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["status"], 400)
        self.assertIn("video_subject", body["message"])
        self.assertTrue(body["data"])

    def test_validation_handler_uses_the_first_error_message(self):
        error = RequestValidationError(
            [
                {
                    "loc": ("body", "video_subject"),
                    "msg": "Field required",
                    "type": "missing",
                }
            ]
        )

        response = validation_exception_handler(None, error)

        self.assertEqual(response.status_code, 400)
        body = json.loads(response.body)
        self.assertEqual(body["message"], "video_subject: Field required")

    def test_wildcard_cors_does_not_enable_credentials(self):
        origins, allow_credentials = resolve_cors_settings("")
        self.assertEqual(origins, ["*"])
        self.assertFalse(allow_credentials)

        origins, allow_credentials = resolve_cors_settings("*,")
        self.assertEqual(origins, ["*"])
        self.assertFalse(allow_credentials)

    def test_explicit_cors_origins_enable_credentials(self):
        origins, allow_credentials = resolve_cors_settings(
            "http://localhost:8501, http://127.0.0.1:8501"
        )

        self.assertEqual(
            origins,
            ["http://localhost:8501", "http://127.0.0.1:8501"],
        )
        self.assertTrue(allow_credentials)

    def test_get_response_keeps_empty_collections(self):
        self.assertEqual(utils.get_response(200, []), {"status": 200, "data": []})
        self.assertEqual(utils.get_response(200, {}), {"status": 200, "data": {}})
        self.assertEqual(utils.get_response(200), {"status": 200})

    def test_sanitize_filename_drops_directory_segments(self):
        self.assertEqual(
            file_security.sanitize_filename(r"..\..\secret.mp4"),
            "secret.mp4",
        )
        self.assertEqual(
            file_security.sanitize_filename("folder/clip.mov"),
            "clip.mov",
        )
        with self.assertRaises(ValueError):
            file_security.sanitize_filename("..")
        with self.assertRaises(ValueError):
            file_security.sanitize_filename("")

    def test_safe_audio_extension_rejects_unexpected_suffixes(self):
        self.assertEqual(file_security.safe_audio_extension("voice.WAV"), ".wav")
        self.assertEqual(file_security.safe_audio_extension("../../x.mp3"), ".mp3")
        self.assertEqual(file_security.safe_audio_extension("notes.exe"), ".mp3")
        self.assertEqual(file_security.safe_audio_extension(""), ".mp3")

    def test_whisper_device_is_case_insensitive(self):
        self.assertEqual(normalize_whisper_option("CPU", "cpu"), "cpu")
        self.assertEqual(normalize_whisper_option(" Cuda ", "cpu"), "cuda")
        self.assertEqual(normalize_whisper_option("   ", "int8"), "int8")
        self.assertEqual(normalize_whisper_option(None, "cpu"), "cpu")


class TestStartHelper(unittest.TestCase):
    def test_check_and_find_skip_a_listening_port(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        busy_port = sock.getsockname()[1]
        sock.listen(1)
        try:
            self.assertTrue(start_helper.check_port("127.0.0.1", busy_port))
            free_port = start_helper.find_free_port(
                "127.0.0.1", busy_port, busy_port + 20
            )
            self.assertNotEqual(free_port, busy_port)
            self.assertGreater(free_port, busy_port)
            self.assertFalse(start_helper.check_port("127.0.0.1", free_port))
        finally:
            sock.close()


if __name__ == "__main__":
    unittest.main()
