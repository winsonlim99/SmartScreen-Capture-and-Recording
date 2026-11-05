"""Admin tool: py Set_Release_Version.py 1.0.1 (before rebuilding)."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
if len(sys.argv) != 2 or not re.fullmatch(r'\d+(\.\d+){1,3}', sys.argv[1]):
    raise SystemExit('Usage: py Set_Release_Version.py 1.0.1')
version = sys.argv[1]
major_minor = '.'.join(version.split('.')[:2])
files = [('smart_update.py', r"APP_VERSION = '[0-9.]+'", "APP_VERSION = '" + version + "'"),
         ('setup.py', r'APP_VERSION = "[0-9.]+"', 'APP_VERSION = "' + version + '"'),
         ('SmartScreen_Capture_V1_0.py', r'SmartScreen Capture & Recording V[0-9.]+', 'SmartScreen Capture & Recording V' + version),
         ('SmartScreen_Capture_V1_0.py', r'SmartScreen Capture & Recording — v[0-9.]+', 'SmartScreen Capture & Recording — v' + version)]
for name, old, new in files:
    path = ROOT / name
    content = path.read_text(encoding='utf-8')
    content, count = re.subn(old, lambda _: new, content)
    if count == 0:
        raise SystemExit('Version string not found in ' + name + ' (' + old + ')')
    path.write_text(content, encoding='utf-8')
print('Updated application/release version to', version)
print('Now rebuild with Build_cxFreeze.bat and publish the new Release folder.')
