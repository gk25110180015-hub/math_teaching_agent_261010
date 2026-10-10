"""Load staged modules in this test process, without installing product changes."""
from pathlib import Path
import importlib.util
import sys
import pytest

root = Path(__file__).resolve().parents[2]
folder = Path(__file__).resolve().parent / '待合并'
for name, path in [('math_agent.compile_recovery', folder / 'compile_recovery.py'),
                   ('math_agent.pipeline', folder / 'pipeline-compile-recovery.py')]:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    # Product methods locate unchanged sibling rule files relative to __file__.
    # Execute candidate code, but resolve its dependencies from the real source tree.
    if name == 'math_agent.pipeline':
        module.__file__ = str(root / 'src/math_agent/pipeline.py')
raise SystemExit(pytest.main([str(root / 'tests/test_compile_layout_recovery.py'), '-q', *sys.argv[1:]]))
