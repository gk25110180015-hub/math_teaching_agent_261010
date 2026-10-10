"""Run isolated in-process candidate checks; no production source installation."""
from pathlib import Path
import importlib.util
import sys
import pytest

root = Path(__file__).resolve().parents[2]
candidate = Path(__file__).resolve().parent / '待合并/mathcheck-series-domain.py'
scanner = candidate.parent / 'series_domain_text.py'
if scanner.exists():
    scanner_spec = importlib.util.spec_from_file_location('math_agent.series_domain_text', scanner)
    scanner_module = importlib.util.module_from_spec(scanner_spec)
    sys.modules['math_agent.series_domain_text'] = scanner_module
    scanner_spec.loader.exec_module(scanner_module)
spec = importlib.util.spec_from_file_location('math_agent.mathcheck', candidate)
module = importlib.util.module_from_spec(spec)
sys.modules['math_agent.mathcheck'] = module
spec.loader.exec_module(module)
raise SystemExit(pytest.main([
    str(root / 'tests/test_series_start_domain.py'), str(root / 'tests/test_series_text_domain.py'), '-q', *sys.argv[1:],
]))
