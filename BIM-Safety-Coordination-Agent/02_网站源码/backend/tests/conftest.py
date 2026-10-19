"""All tests use a private database, never the operator's runtime database."""
import os
import tempfile
from pathlib import Path

test_runtime = Path(tempfile.mkdtemp(prefix='bim-agent-tests-'))
os.environ['RUNTIME_DIR'] = str(test_runtime)
os.environ['DB_PATH'] = str(test_runtime / 'app.db')
os.environ['DATA_ROOT'] = str(Path(__file__).resolve().parents[3] / '01_资料与依据')
os.environ['DEMO_MODE'] = 'true'
for key in ('MODEL_BASE_URL', 'MODEL_API_KEY', 'MODEL_NAME', 'VISION_BASE_URL', 'VISION_API_KEY', 'VISION_MODEL'):
    os.environ[key] = ''
