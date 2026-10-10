"""Reuse the fixed 53-file original audit with an isolated dated output."""
from datetime import datetime,timezone
from pathlib import Path
root=Path(__file__).resolve().parents[2]
source=root/'reports/iteration4/verify_originals_preservation.py'
output=root/'reports/iteration4'/('originals-recheck-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
output.mkdir(exist_ok=False)
text=source.read_text(encoding='utf-8')
assert text.count("OUTPUT = ROOT / 'reports/iteration4'")==1
text=text.replace("OUTPUT = ROOT / 'reports/iteration4'",'OUTPUT = Path('+repr(str(output))+')')
exec(compile(text,str(source),'exec'),{'__file__':str(source),'__name__':'__main__'})
print(str(output))
