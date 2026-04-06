from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import optimized_params_store as store


class OptimizedParamsStoreTests(unittest.TestCase):
    def test_write_runtime_optimized_params_normalizes_permissions(self):
        payload = {"version": "runtime-test"}

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "runtime_optimized_params.json"
            output_path.write_text("{}", encoding="utf-8")
            output_path.chmod(0o600)

            with patch.object(store, "RUNTIME_OPTIMIZED_PARAMS_PATH", output_path):
                written = store.write_runtime_optimized_params(payload)

            self.assertEqual(output_path, written)
            self.assertEqual(payload, json.loads(output_path.read_text(encoding="utf-8")))
            self.assertEqual(0o664, output_path.stat().st_mode & 0o777)


if __name__ == "__main__":
    unittest.main()
