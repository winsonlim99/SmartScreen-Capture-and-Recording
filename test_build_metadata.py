"""Exercise the setup metadata options with real setuptools, without freezing."""
import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent


class BuildMetadataTests(unittest.TestCase):
    def test_setup_egg_info_outside_source_for_each_architecture(self):
        # Read the actual setup() options; avoid executing its Windows/FFmpeg
        # prerequisites, while exercising the real setuptools metadata command.
        tree = ast.parse((ROOT / 'setup.py').read_text())
        setup_call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                          and isinstance(n.func, ast.Name) and n.func.id == 'setup')
        options = next(k.value for k in setup_call.keywords if k.arg == 'options')
        expression = ast.unparse(options)
        for arch in ('x64', 'x86'):
            with self.subTest(arch=arch), tempfile.TemporaryDirectory() as td:
                source = Path(td) / 'nested source' / 'project'
                source.mkdir(parents=True)
                (source / 'app.py').write_text('print("application")\n')
                output = Path(td) / 'short output'
                code = '''
from pathlib import Path
from setuptools import Distribution
from build_paths import BUILD, BUILD_WORK, METADATA
METADATA.mkdir(parents=True, exist_ok=True)
build_options = {}
options = OPTIONS
# build_exe belongs to cx_Freeze; metadata itself belongs to setuptools.
options.pop('build_exe')
dist = Distribution(dict(name='SmartScreen Capture Recording', version='1.0.6',
                         py_modules=['app'], options=options))
dist.script_name = 'setup.py'
dist.run_command('egg_info')
command = dist.get_command_obj('egg_info')
assert Path(command.egg_info).parent == METADATA
assert (Path(command.egg_info) / 'PKG-INFO').is_file()
assert not list(Path.cwd().glob('*.egg-info'))
assert dist.get_command_obj('build').build_base == str(BUILD_WORK)
assert METADATA.name == ARCH
'''.replace('OPTIONS', expression).replace('ARCH', repr(arch))
                env = dict(os.environ, PYTHONPATH=str(ROOT),
                           SMARTSCREEN_OUTPUT_ROOT=str(output), SMARTSCREEN_BUILD_ARCH=arch)
                result = subprocess.run([sys.executable, '-c', code], cwd=source,
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
