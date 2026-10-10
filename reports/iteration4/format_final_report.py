"""Fix Markdown pipe escaping and one inherited source-line reference; keep prior reports."""
from pathlib import Path
import json,shutil
root=Path(__file__).resolve().parents[2]
reports=root/'reports/iteration4'
audit=reports/'ch01-final-audit-20260924-final'
backup=audit/'before-markdown-format'
backup.mkdir(exist_ok=False)
for name in ['final-audit.md','final-audit.json']:shutil.copyfile(audit/name,backup/name)
data=json.loads((audit/'final-audit.json').read_bytes())
criteria={row['id']:row for row in data['criteria']}
row=criteria['CH01-X01']
row['reason']=row['reason'].replace('447行之后',str(data['source']['unit_lines']['S01.U10']-1)+'行之后')
lines=(audit/'final-audit.md').read_text(encoding='utf-8').splitlines()
for index,line in enumerate(lines):
    if line.startswith('|CH01-'):
        ident=line[1:].split(' ',1)[0]
        row=criteria[ident]
        text=row['reason'].rstrip('。').replace('|',r'\|')
        lines[index]='|'+ident+' '+row['title']+'|'+row['status']+'|'+text+'；'+', '.join(x['unit_id']+'@'+str(x['line']) for x in row['tex_units'])+'|'
(audit/'final-audit.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
(audit/'final-audit.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
final=reports/'FINAL_ACCEPTANCE.md'
final.write_text(final.read_text(encoding='utf-8').replace('极限比較','极限比较'),encoding='utf-8')
original=reports/'originals-recheck-20260924T080903/originals-preservation.md'
original.write_text(original.read_text(encoding='utf-8').replace(
 '../iteration3/originals-recheck-20260920-113945-235484.json',
 (root/'reports/iteration3/originals-recheck-20260920-113945-235484.json').as_posix()),encoding='utf-8')
print('REPORT_FORMAT_UPDATED; no verdict or generated artifact changed')
