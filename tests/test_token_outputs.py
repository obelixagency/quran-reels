import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

# No external packages, credentials, or network required for these security checks.
try:
    import requests
except ImportError:
    requests = types.ModuleType('requests')
    requests.post = requests.get = requests.put = lambda *a, **k: None
    sys.modules['requests'] = requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
CANARY = 'synthetic-not-a-real-token-123456'

class Response:
    status_code = 400
    text = CANARY
    def json(self):
        return {'error': {'code': 'failed', 'message': CANARY}, 'refresh_token': CANARY}

class TokenOutputTests(unittest.TestCase):
    def test_provider_errors_do_not_echo_payloads(self):
        for name in ('meta', 'tiktok'):
            module = importlib.import_module('src.publish_' + name)
            with self.assertRaises(RuntimeError) as error:
                module._check(Response())
            self.assertNotIn(CANARY, str(error.exception))

    def test_refresh_failures_do_not_echo_new_tokens(self):
        env = {name: CANARY for name in ('YT_CLIENT_ID','YT_CLIENT_SECRET','YT_REFRESH_TOKEN',
                                       'TIKTOK_CLIENT_KEY','TIKTOK_CLIENT_SECRET','TIKTOK_REFRESH_TOKEN')}
        with patch.dict(os.environ, env), patch.object(requests, 'post', return_value=Response()):
            for name in ('youtube', 'tiktok'):
                with self.assertRaises(RuntimeError) as error:
                    importlib.import_module('src.publish_' + name).access_token()
                self.assertNotIn(CANARY, str(error.exception))

    def test_successful_token_return_unchanged(self):
        response = Response()
        response.json = lambda: {'access_token': CANARY}
        env = {name: 'dummy' for name in ('YT_CLIENT_ID','YT_CLIENT_SECRET','YT_REFRESH_TOKEN')}
        output = io.StringIO()
        with patch.dict(os.environ, env), patch.object(requests, 'post', return_value=response), contextlib.redirect_stdout(output):
            self.assertEqual(importlib.import_module('src.publish_youtube').access_token(), CANARY)
        self.assertNotIn(CANARY, output.getvalue())

    def test_runner_handoff_replaces_permissive_file_and_symlink(self):
        module = importlib.import_module('src.publish_tiktok')
        with tempfile.TemporaryDirectory() as folder:
            previous = os.getcwd()
            try:
                os.chdir(folder)
                Path('out').mkdir()
                target = Path('out/.tiktok_refresh_token')
                target.write_text('old')
                target.chmod(0o644)
                module._write_refresh_handoff(CANARY)
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                self.assertEqual(target.read_text(), CANARY)
                target.unlink()
                unrelated = Path('unrelated').resolve()
                unrelated.write_text('untouched')
                target.symlink_to(unrelated)
                module._write_refresh_handoff(CANARY)
                self.assertFalse(target.is_symlink())
                self.assertEqual(unrelated.read_text(), 'untouched')
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                self.assertEqual(target.read_text(), CANARY)
                self.assertEqual(list(Path('out').glob('.tiktok-refresh-*')), [])
            finally:
                os.chdir(previous)

    def test_signed_image_urls_removed_before_public_result_assignment(self):
        # Exercise the existing pop-and-handoff statements without importing
        # rendering dependencies or making provider calls.
        import ast
        for relative in ('src/posts.py', 'src/en/posts.py', 'src/adhkar.py', 'src/en/adhkar.py'):
            tree = ast.parse((ROOT/relative).read_text())
            found = 0
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                calls = [n for n in ast.walk(node.value) if isinstance(n, ast.Call)
                         and isinstance(n.func, ast.Attribute) and n.func.attr == 'pop'
                         and n.args and isinstance(n.args[0], ast.Constant)
                         and n.args[0].value in ('image_url', 'image_urls')]
                for call in calls:
                    key = call.args[0].value
                    source = call.func.value.id
                    signed = 'https://cdn.example/image?signature=' + CANARY
                    result = {'photo_id':'photo123', 'post_id':'post123', 'story_id':'story123',
                              key: [signed] if key == 'image_urls' else signed}
                    scope = {source: result}
                    exec(compile(ast.Module(body=[node], type_ignores=[]), '<handoff>', 'exec'), scope)
                    self.assertNotIn(key, result)
                    self.assertNotIn(CANARY, json.dumps(result))
                    self.assertEqual(result['post_id'], 'post123')
                    handoff = scope[node.targets[0].id]
                    self.assertIn(CANARY, str(handoff))
                    found += 1
            self.assertGreater(found, 0, relative)

    def test_private_handoff(self):
        import secure_handoff
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'credentials.json'
            output = io.StringIO()
            with patch('builtins.input', return_value=str(path)), contextlib.redirect_stdout(output):
                secure_handoff.write_credentials({'refresh_token': CANARY})
                with self.assertRaises(FileExistsError):
                    secure_handoff.write_credentials({'refresh_token': CANARY})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertNotIn(CANARY, output.getvalue())
            self.assertEqual(json.loads(path.read_text())['refresh_token'], CANARY)

    def test_setup_refuses_ci(self):
        import secure_handoff
        with patch.dict(os.environ, {'GITHUB_ACTIONS':'true'}):
            with self.assertRaises(SystemExit):
                secure_handoff.local_only()

    def test_no_workflow_credential_inputs_or_exchanges(self):
        for name in ('serenity-connect','tiktok-connect','youtube-reauth'):
            text = (ROOT/f'.github/workflows/{name}.yml').read_text()
            for forbidden in ('inputs:', 'secrets.', 'curl ', 'gh secret set'):
                self.assertNotIn(forbidden, text)

    def test_no_exception_payload_sinks(self):
        for path in (ROOT/'src').rglob('*.py'):
            source = path.read_text()
            self.assertNotIn('traceback.print_exc()', source, path)
            self.assertNotIn('"error": str(e)', source, path)

if __name__ == '__main__':
    unittest.main()
