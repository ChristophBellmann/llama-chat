"""SDK setup must not install old wheels or inherit the old GPU libraries."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class RuntimeSetupTests(unittest.TestCase):
    def test_new_sdk_setup_and_smoke_are_isolated(self):
        source = Path(__file__).resolve().parents[1] / "voice/run.sh"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            voice = root / "voice"
            voice.mkdir()
            (voice / "run.sh").write_text(source.read_text())
            (root / "env.local.sh").write_text("")
            python = root / "venv/bin/python3"
            python.parent.mkdir(parents=True)
            log = root / "calls.jsonl"
            python.write_text(
                "#!/usr/bin/python3\nimport json,os,sys\n"
                "with open(os.environ['TEST_CALLS'],'a') as f:\n"
                " f.write(json.dumps({'args':sys.argv[1:],'env':{k:os.environ.get(k) for k in "
                "('ROCM_PATH','LD_PRELOAD','LD_LIBRARY_PATH','HSA_OVERRIDE_GFX_VERSION')}})+'\\n')\n"
            )
            python.chmod(0o755)
            env = dict(os.environ, VENV_DIR=str(python.parent.parent), VOICE_ROCM_RUNTIME="python-sdk",
                       TEST_CALLS=str(log), ROCM_PATH="/old/rocm", LD_PRELOAD="/old/rocm/libfake.so",
                       LD_LIBRARY_PATH="/old/rocm/lib", HSA_OVERRIDE_GFX_VERSION="10.3.0")
            result = subprocess.run(["bash", str(voice / "run.sh"), "setup-orpheus"], env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            installs = [row for row in calls if "install" in row["args"]]
            self.assertTrue(any("torch[device-gfx1031]==2.12.0+rocm10.1.0" in row["args"] for row in installs))
            self.assertFalse(any("torch-current.whl" in arg for row in calls for arg in row["args"]))
            for row in calls:
                self.assertTrue(all(value is None for value in row["env"].values()))


if __name__ == "__main__":
    unittest.main()
