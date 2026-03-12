import os
import subprocess
from pathlib import Path


def test_related_code_loader_imports_under_launchd_python():
    python_bin = Path(".venv/bin/python")
    assert python_bin.exists()

    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    result = subprocess.run(
        [str(python_bin), "-c", "import mr_auto_reviewer.related_code_loader"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
