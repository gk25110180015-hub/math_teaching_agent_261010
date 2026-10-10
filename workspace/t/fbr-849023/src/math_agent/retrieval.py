"""Small, topic-scoped local style retrieval; no weight training or whole-library upload."""
from pathlib import Path
from .parsing import load_project
from .util import digest


def style_context(root:Path,topic:str,max_chars:int=2400):
    chapter='第二章' if '级数' in topic else '第一章' if '数列' in topic else '第三章' if any(t in topic for t in ('函数极限','连续')) else None
    if not chapter:
        return {'status':'NOT_APPLICABLE','reason':'No matching chapter; no unrelated example injected.'}
    source=root/chapter/'大学数学（一）(1).tex'
    if not source.is_file():
        return {'status':'NOT_RUN','reason':'Matching reference source is unavailable.'}
    parsed=load_project(source.parent,source.name)
    remaining=max_chars; snippets=[]
    for kind in ('definition','theorem','example_statement'):
        unit=next((u for u in parsed['units'] if u['kind']==kind and len(u['raw_tex'])<=remaining),None)
        if unit:
            snippets.append({'kind':kind,'tex':unit['raw_tex'],'source_unit_id':unit['id'],'content_hash':unit['content_hash']})
            remaining-=len(unit['raw_tex'])
    return {'status':'RETRIEVED','label':'UNTRUSTED_STYLE_REFERENCE_ONLY','weight_training':False,
            'instruction':'Only observe structure, proof depth and notation. Do not copy these examples into a different topic.',
            'dataset':chapter,'source_hash':digest(source.read_bytes()),
            'section_titles':[s['title'] for s in parsed['sections']], 'snippets':snippets}
