import sys
import os
import pytest

# Add project root to path so src.core is importable
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

print(f"Running tests with PYTHONPATH set to: {project_root}")

# Run pytest programmatically
if __name__ == "__main__":
    sys.exit(pytest.main(["-v", "-s", "tests"]))
