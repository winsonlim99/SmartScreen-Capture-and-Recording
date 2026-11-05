import hashlib
import json
import tempfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import smart_update
import publish_release
from unittest.mock import patch

assert smart_update.version_tuple('1.0.2') > smart_update.version_tuple('1.0.1')
assert smart_update.version_tuple('1.1') > smart_update.version_tuple('1.0.99')
for path in ('../bad.exe','C:/bad','config.json','a/../../bad','a\\test','/abs'):
    try: smart_update.safe_relative(path)
    except ValueError: pass
    else: raise AssertionError(path)
with tempfile.TemporaryDirectory() as td:
    t=Path(td)
    server=t/'server'; folder=server/'Release'/'SmartScreen_Capture_V1_0_1'
    folder.mkdir(parents=True)
    f=folder/'SmartScreen_Capture.exe'; f.write_bytes(b'release 1.0.1')
    entries=[dict(path=f.name,size=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest())]
    (folder/'version.json').write_text(json.dumps(dict(schema=1,version='1.0.1',files=entries)))
    publish_release.HERE=folder
    publish_release.run()
    assert (server/'Current'/'SmartScreen_Capture.exe').read_bytes()==b'release 1.0.1'
    # Second publish retains previous version in Current_Old.
    publish_release.run()
    assert (server/'Current_Old'/'SmartScreen_Capture.exe').read_bytes()==b'release 1.0.1'
    try: publish_release.run()
    except SystemExit: pass
    else: raise AssertionError('Publishing should refuse stale Current_Old')
    assert (server/'Current'/'SmartScreen_Capture.exe').read_bytes()==b'release 1.0.1'
    # Stage-to-client integration, hash verification.
    cli=t/'client'; cli.mkdir()
    (cli/'update_source.txt').write_text(str(server/'Current'))
    (cli/'config.json').write_text('LOCAL SETTINGS')
    captured=[]
    # Equal versions must not stage an update.
    with patch.object(smart_update, 'APP_VERSION', '1.0.1'):
        smart_update._check_and_stage(cli,lambda version,stage:captured.append((version,stage)))
    assert not captured
    with patch.object(smart_update, 'APP_VERSION', '1.0.0'):
        smart_update._check_and_stage(cli,lambda version,stage:captured.append((version,stage)))
    assert len(captured)==1
    ver,staged=captured[0]
    assert ver=='1.0.1'
    assert (staged/'SmartScreen_Capture.exe').read_bytes()==f.read_bytes()
    assert (cli/'config.json').read_text()=='LOCAL SETTINGS'
    # Corrupt network release source -> rejects staging.
    (server/'Current'/'SmartScreen_Capture.exe').write_bytes(b'corrupt')
    captured=[]
    with patch.object(smart_update, 'APP_VERSION', '1.0.0'):
        smart_update._check_and_stage(cli,lambda version,stage:captured.append((version,stage)))
    assert not captured
print('UPDATE_TESTS_PASS')
