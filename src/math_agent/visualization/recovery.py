"""Resume the last rejected program without changing the approved teaching plan."""
import json
from pathlib import Path
from ..util import digest, within
from .models import Program


def contract_hash():
    root = Path(__file__).parent
    paths = [root / n for n in ('player.js', 'models.py', 'render.py', 'pipeline.py', 'document.py', 'contracts.py', 'generation.py')]
    paths += [root.parent / 'prompts' / (n + '.md') for n in ('visualization_writer', 'visualization_reviewer')]
    return digest({p.name: digest(p.read_bytes()) for p in paths})


def failure_identity(run):
    return digest({'plan_hash': run['plan']['hash'], 'input_hash': run['input_hash']})


def last_failure(store, workspace, run):
    saved = store.cached_step(run['id'], 'visualization.last_failure', failure_identity(run))
    if saved:
        return saved
    # Before v2, rejected code was published only as immutable diagnostics.
    # Read only matching, hash-verified artifacts; never modify those originals.
    with store.connect() as c:
        rows = c.execute("SELECT * FROM artifacts WHERE run_id=? ORDER BY created_at DESC,rowid DESC", (run['id'],)).fetchall()
    groups = {}
    for row in rows:
        meta = json.loads(row['metadata_json'])
        if meta.get('kind') != 'visualization_draft' or meta.get('plan_hash') != run['plan']['hash']:
            continue
        path = within(Path(workspace), Path(workspace) / row['storage_key'])
        if not path.is_file() or digest(path.read_bytes()) != row['sha256']:
            continue
        if row['name'].startswith(('program-', 'issues-')) and path.suffix == '.json':
            groups.setdefault(path.parent, {})[path.name] = json.loads(path.read_text(encoding='utf-8'))
    for files in groups.values():
        attempts = sorted(int(n[8:-5]) for n in files if n.startswith('program-') and n[8:-5].isdigit())
        paired = [i for i in attempts if f'issues-{i}.json' in files]
        if paired:
            i = paired[-1]
            return {'previous_program': Program.model_validate(files[f'program-{i}.json']).model_dump(),
                    'repair_issues': files[f'issues-{i}.json'],
                    'repair_history': [{'issues': files[f'issues-{n}.json']} for n in paired],
                    'source': 'verified_legacy_diagnostics'}
    return {}
