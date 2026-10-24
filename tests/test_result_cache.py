import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from src.intelligence.localization import LocalizationService, Translation
from src.intelligence.result_cache import ResultCache


class TestResultCache(unittest.TestCase):
    def test_persistence_expiry_bounded_size_and_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'results.json'
            now = [100.0]
            cache = ResultCache(path, ttl=10, limit=2, now=lambda: now[0])
            value = {'nodes': [{'title': 'A completed learning map'}]}
            cache.put('one', value)
            value['nodes'].clear()
            read = cache.get('one')
            read['nodes'].clear()
            self.assertEqual(len(cache.get('one')['nodes']), 1)
            restored = ResultCache(path, ttl=10, limit=2, now=lambda: now[0])
            self.assertEqual(len(restored.get('one')['nodes']), 1)
            restored.put('two', {})
            restored.put('three', {})
            self.assertIsNone(restored.get('one'))
            now[0] += 11
            self.assertIsNone(restored.get('two'))
            self.assertIsNone(ResultCache(path, ttl=10, now=lambda: now[0]).get('three'))

    def test_invalid_cache_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'results.json'
            for value in ('not-json', '[]', '{"version":1,"items":{"key":null}}'):
                path.write_text(value)
                self.assertIsNone(ResultCache(path).get('key'))


class TestLocalization(unittest.TestCase):
    def test_translation_is_cached_without_touching_graph_or_course_facts(self):
        value = {'summary': 'Build practical analysis skills.', 'nodes': [{'node_id': 'node_1',
            'title': 'Clean a dataset', 'objective': 'Check missing records', 'deliverable': 'A checked dataset',
            'skill_ids': ['skill:sql'], 'hours': 12}], 'edges': [], 'courses': [{'title': 'Original course title'}]}
        client = Mock()
        client.generate.return_value = SimpleNamespace(value=Translation(texts=['Bina kemahiran analisis.',
            'Bersihkan set data', 'Semak rekod yang hilang', 'Set data yang disemak']))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'translations.json'
            service = LocalizationService(path, client_factory=lambda: client)
            result = service.localize(value, 'ms', 'roadmap')
            self.assertEqual(result['nodes'][0]['title'], 'Bersihkan set data')
            self.assertEqual(result['nodes'][0]['skill_ids'], value['nodes'][0]['skill_ids'])
            self.assertEqual(result['courses'], value['courses'])
            self.assertEqual(value['nodes'][0]['title'], 'Clean a dataset')
            service.localize(value, 'ms', 'roadmap')
            restored = LocalizationService(path, client_factory=lambda: client)
            self.assertEqual(restored.localize(value, 'ms', 'roadmap'), result)
            client.generate.assert_called_once()

    def test_outlook_keeps_source_title_quote_url_and_dates_in_original(self):
        client = Mock()
        client.generate.return_value = SimpleNamespace(value=Translation(texts=['研究任务', '发现变化', '可能影响', '练习方法', '证据说明']))
        value = {'interpretations': [{'task_label': 'Task', 'what_changed': 'Finding', 'role_relevance': 'May affect tasks',
            'learning_action': 'Practice', 'evidence_quote': 'Exact original quotation',
            'source': {'title': 'Original research', 'source_url': 'https://example.org', 'published_at': '2026-01-01'}}],
            'source_review': {'articles': [{'outcome': 'connected', 'reason': 'Explanation'}]}}
        result = LocalizationService(client_factory=lambda: client).localize(value, 'zh', 'trends')
        self.assertEqual(result['interpretations'][0]['evidence_quote'], 'Exact original quotation')
        self.assertEqual(result['interpretations'][0]['source'], value['interpretations'][0]['source'])
        self.assertEqual(result['interpretations'][0]['learning_action'], '练习方法')

    def test_failed_or_incomplete_translation_is_not_cached_or_claimed_as_translated(self):
        client = Mock()
        client.generate.return_value = SimpleNamespace(value=Translation(texts=[]))
        service = LocalizationService(client_factory=lambda: client)
        value = {'summary': 'An original learning summary', 'nodes': [], 'edges': []}
        result = service.localize(value, 'ms', 'roadmap')
        self.assertEqual(result['summary'], value['summary'])
        self.assertEqual(result['content_language'], 'en')
        self.assertEqual(result['translation_status'], 'unavailable')
        service.localize(value, 'ms', 'roadmap')
        self.assertEqual(client.generate.call_count, 2)


if __name__ == '__main__':
    unittest.main()
