import unittest

from src.interfaces import DEFAULT_PROMPT, BasePhotoExtractor, ErrorCode, ProcessingResult, make_error_result


class _MinimalExtractor(BasePhotoExtractor):
    def extract(self, image_path, prompt=None, options=None):
        return ProcessingResult()

    def extract_b64(self, image_b64, prompt=None, options=None):
        return ProcessingResult()

    def health_check(self):
        return True


class TestInterfaces(unittest.TestCase):
    def test_default_prompt_is_string(self):
        self.assertIsInstance(DEFAULT_PROMPT, str)
        self.assertIn("description", DEFAULT_PROMPT)
        self.assertIn("JSON", DEFAULT_PROMPT)

    def test_error_code_values(self):
        self.assertEqual(ErrorCode.NETWORK_ERROR.value, "network_error")
        self.assertEqual(ErrorCode.TIMEOUT.value, "timeout")
        self.assertEqual(ErrorCode.INVALID_RESPONSE.value, "invalid_response")
        self.assertEqual(ErrorCode.FORMAT_NOT_SUPPORTED.value, "format_not_supported")
        self.assertEqual(ErrorCode.PROCESSING_ERROR.value, "processing_error")

    def test_base_photo_extractor_is_abstract(self):
        with self.assertRaises(TypeError):
            BasePhotoExtractor()

    def test_base_photo_extractor_init_defaults(self):
        e = _MinimalExtractor()
        self.assertEqual(e.host, "127.0.0.1")
        self.assertEqual(e.port, 11434)
        self.assertEqual(e.model, "gemma4:e2b-it-qat")
        self.assertEqual(e.timeout, 120)
        self.assertEqual(e.base_url, "http://127.0.0.1:11434")
        self.assertEqual(e.default_prompt, DEFAULT_PROMPT)

    def test_make_error_result_without_path(self):
        result = make_error_result(ErrorCode.TIMEOUT, "Request timed out")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "timeout")
        self.assertEqual(result["error"], "Request timed out")
        self.assertNotIn("image_path", result)

    def test_make_error_result_with_path(self):
        result = make_error_result(ErrorCode.NETWORK_ERROR, "Connection refused", image_path="/photos/img.jpg")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "network_error")
        self.assertEqual(result["error"], "Connection refused")
        self.assertEqual(result["image_path"], "/photos/img.jpg")

    def test_make_error_result_all_error_codes(self):
        for code in ErrorCode:
            result = make_error_result(code, "test")
            self.assertEqual(result["error_code"], code.value)


if __name__ == "__main__":
    unittest.main()
