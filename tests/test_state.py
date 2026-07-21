import threading
import unittest

from src.state import (
    _cancel_job as cancel_job,
    is_job_cancelled,
    _remove_job_cancel as remove_job_cancel,
    request_shutdown,
    reset_shutdown_event,
    is_shutdown_requested,
)


class TestJobCancellation(unittest.TestCase):
    def setUp(self):
        remove_job_cancel("test-job-id")
        remove_job_cancel("job-a")
        remove_job_cancel("job-b")

    def tearDown(self):
        remove_job_cancel("test-job-id")
        remove_job_cancel("job-a")
        remove_job_cancel("job-b")

    def test_job_not_cancelled_initially(self):
        self.assertFalse(is_job_cancelled("test-job-id"))

    def test_cancel_job_sets_flag(self):
        cancel_job("test-job-id")
        self.assertTrue(is_job_cancelled("test-job-id"))

    def test_is_job_cancelled_unknown_id(self):
        self.assertFalse(is_job_cancelled("unknown-id"))

    def test_multiple_jobs_independent(self):
        cancel_job("job-a")
        self.assertTrue(is_job_cancelled("job-a"))
        self.assertFalse(is_job_cancelled("job-b"))

        cancel_job("job-b")
        self.assertTrue(is_job_cancelled("job-a"))
        self.assertTrue(is_job_cancelled("job-b"))


class TestShutdownEvent(unittest.TestCase):
    def setUp(self):
        reset_shutdown_event()

    def test_not_requested_initially(self):
        self.assertFalse(is_shutdown_requested())

    def test_request_then_reset(self):
        request_shutdown()
        self.assertTrue(is_shutdown_requested())
        reset_shutdown_event()
        self.assertFalse(is_shutdown_requested())

    def test_shutdown_does_not_affect_job_cancel(self):
        request_shutdown()
        self.assertTrue(is_shutdown_requested())
        self.assertFalse(is_job_cancelled("test-job-id"))
        reset_shutdown_event()


if __name__ == "__main__":
    unittest.main()
