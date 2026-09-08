import json
import unittest
from unittest.mock import patch

from summarizer import summarize_bacheca


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        payload = {"title": "Titolo breve", "summary": "Riassunto utile."}
        return json.dumps({"output": [{"content": [{"type": "output_text", "text": json.dumps(payload)}]}]}).encode()


class SummarizerTests(unittest.TestCase):
    @patch("summarizer.urlopen", return_value=FakeResponse())
    def test_requests_structured_italian_summary(self, mocked_urlopen):
        result = summarize_bacheca("Avviso", language="it", api_key="test-key")
        self.assertEqual("Titolo breve", result["title"])
        request = mocked_urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual("json_schema", body["text"]["format"]["type"])
        self.assertIn("in Italian", body["input"][0]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
