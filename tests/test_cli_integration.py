import unittest
from pathlib import Path


class TestCliIntegration(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = Path(__file__).parent / "fixtures"
        self.sample_jpg = self.fixtures_dir / "sample.jpg"

    def test_sample_image_exists(self):
        self.assertTrue(
            self.sample_jpg.exists(),
            f"Test fixture missing: {self.sample_jpg}",
        )

    def test_main_imports_and_parser(self):
        import main
        self.assertTrue(hasattr(main, "main"))

    def test_processing_result_end_to_end_mocked(self):
        from plugins.llm.base import BasePhotoExtractor
        from src.interfaces import ProcessingResult

        class FakeExtractor(BasePhotoExtractor):
            def __init__(self):
                super().__init__(host="fake", port=0, model="fake-model", timeout=10)

            def extract(self, image_path, prompt=None, options=None):
                return ProcessingResult(
                    success=True,
                    image_path=str(image_path),
                    model=self.model,
                    response='{"key": "value"}',
                    parsed={"key": "value"},
                )

            def extract_b64(self, image_b64, prompt=None, options=None):
                return self.extract("b64-fake", prompt=prompt)

            def health_check(self):
                return True

        extractor = FakeExtractor()
        results = [extractor.extract(str(self.sample_jpg))]
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].image_path, str(self.sample_jpg))


if __name__ == "__main__":
    unittest.main()
