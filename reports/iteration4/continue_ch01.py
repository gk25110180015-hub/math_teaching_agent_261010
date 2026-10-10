"""Reuse the formal resume driver exclusively for CH01, without editing production scripts."""
from pathlib import Path
import runpy

root=Path(__file__).resolve().parents[2]
namespace=runpy.run_path(str(root/'scripts/continue_live_chapters.py'))
namespace['RUNS'].clear()
namespace['RUNS']['CH01']='05748ab6260c40989a560a98e1e2065a'
namespace['main']()
