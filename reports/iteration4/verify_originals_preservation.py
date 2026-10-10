"""Read-only verification of exactly the 53 previously manifested originals."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / 'reports/iteration3/originals-recheck-20260920-113945-235484.json'
OUTPUT = ROOT / 'reports/iteration4'


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        while block := source.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
assert baseline['file_count'] == len(baseline['original_files']) == 53
files = []
for item in baseline['original_files']:
    row = {'path': item['path'], 'expected_sha256': item['expected_sha256'],
           'previous_observed_sha256': item['observed_sha256'], 'observed_sha256': None}
    try:
        row['observed_sha256'] = digest(Path(item['path']))
        row['status'] = 'PASS' if row['observed_sha256'] == row['expected_sha256'] else 'CHANGED'
    except OSError as error:
        row['status'] = 'UNREADABLE'
        row['error'] = {'type': type(error).__name__, 'message': str(error)}
    files.append(row)
counts = dict(Counter(row['status'] for row in files))
report = {
    'created_at': datetime.now(timezone.utc).isoformat(),
    'verification_mode': 'READ_ONLY_SHA256_NO_ORIGINAL_WRITES',
    'baseline_manifest': str(BASELINE), 'baseline_manifest_sha256': digest(BASELINE),
    'file_count': len(files), 'counts': counts,
    'status': 'PASS' if counts == {'PASS': 53} else 'NOT_PASS',
    'checked_scope': 'Exactly the 53 manifest-listed originals; files outside this list are not covered.',
    'reference_index_updated': False, 'original_files': files,
}
with (OUTPUT / 'originals-preservation.json').open('x', encoding='utf-8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
lines = [
    '# 原始资料保留核对', '',
    f"结果：**{report['status']}**。清单中的 53 个原件：{counts.get('PASS', 0)} 个哈希一致，"
    f"{counts.get('CHANGED', 0)} 个更改，{counts.get('UNREADABLE', 0)} 个不可读。", '',
    f"核对时间（UTC）：{report['created_at']}。", '',
    '仅以读取方式计算 SHA-256；未写入原件，也未运行或更新参考资料索引。', '',
    '范围严格限定于 iteration3 的 53 项原件清单。**清单外文件、后续新增文件不在本报告覆盖范围内**；本报告不构成全部目录的新清点。', '',
    '[基准清单](../iteration3/originals-recheck-20260920-113945-235484.json) · [机器可读逐项结果](originals-preservation.json)', '',
    '| 原件路径 | 原 SHA-256 | 当前 SHA-256 | 结果 |',
    '|---|---|---|---|',
]
for row in files:
    lines.append(f"| {row['path']} | `{row['expected_sha256']}` | `{row['observed_sha256'] or 'UNREADABLE'}` | {row['status']} |")
with (OUTPUT / 'originals-preservation.md').open('x', encoding='utf-8') as stream:
    stream.write('\n'.join(lines) + '\n')
print(json.dumps({'status': report['status'], 'file_count': len(files), 'counts': counts}))
