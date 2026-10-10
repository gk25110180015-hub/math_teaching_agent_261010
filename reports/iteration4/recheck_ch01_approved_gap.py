"""Reuse the formal recheck driver for CH01's existing approved objective."""
from pathlib import Path
import runpy

root = Path(__file__).resolve().parents[2]
namespace = runpy.run_path(str(root / 'scripts/recheck_live_chapter.py'))
namespace['RUNS']['CH01'] = '05748ab6260c40989a560a98e1e2065a'
namespace['main']()
