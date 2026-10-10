"""Render every physical page and report measured geometry without pretending vision."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def parse_overlay_map(nav_path: Path, page_count: int) -> dict:
    result = {'status': 'FAIL', 'source': str(nav_path), 'frames': [], 'pages': [], 'issues': []}
    if not nav_path.is_file():
        result['issues'].append('Beamer .nav 文件缺失，不能推断 overlay 映射。')
        return result
    nav = nav_path.read_text(encoding='utf-8', errors='replace')
    pairs = re.findall(r'\\beamer@framepages\s*\{(\d+)\}\s*\{(\d+)\}', nav)
    if not pairs:
        pairs = re.findall(r'\\slideentry\s*\{\d+\}\s*\{\d+\}\s*\{\d+\}\s*\{(\d+)/(\d+)\}', nav)
    # Optional deterministic IDs from the renderer; nav remains the physical-page authority.
    ids_path = nav_path.parent / 'frame_ids.json'
    ids = json.loads(ids_path.read_text(encoding='utf-8')) if ids_path.is_file() else []
    if not ids and (nav_path.parent / 'frame_ids.txt').is_file():
        ids = (nav_path.parent / 'frame_ids.txt').read_text(encoding='utf-8').splitlines()
    seen = []
    for index, (start, end) in enumerate(pairs):
        start, end = int(start), int(end)
        if end < start or start < 1 or end > page_count:
            result['issues'].append(f'非法 frame 页区间 {start}..{end}')
            continue
        frame_id = ids[index].strip() if index < len(ids) and ids[index].strip() else f'F{index + 1:03d}'
        pages = list(range(start, end + 1))
        result['frames'].append({'frame_id': frame_id, 'physical_pages': pages})
        for overlay, physical in enumerate(pages, 1):
            result['pages'].append({'physical_page': physical, 'frame_id': frame_id, 'overlay_index': overlay})
        seen.extend(pages)
    if sorted(seen) != list(range(1, page_count + 1)):
        result['issues'].append('nav 映射未恰好覆盖所有 PDF 物理页面。')
    if ids and len(ids) != len(pairs):
        result['issues'].append('renderer frame IDs 数量与实际 nav frames 不一致。')
    result['status'] = 'PASS' if not result['issues'] else 'FAIL'
    return result


def _box(obj: dict) -> list[float]:
    return [round(float(obj.get(k, 0)), 3) for k in ('x0', 'top', 'x1', 'bottom')]


def _inside_page(box, width, height):
    return box[0]>=-.75 and box[1]>=-.75 and box[2]<=width+.75 and box[3]<=height+.75


def match_pgf_hidden_character(char: dict, source_page: dict, peers: list[dict]) -> dict | None:
    """Recognize only PGF's exact 2000bp cover translation with a visible peer.

    Same nav frame, distinct physical page, identical glyph/font/size and all four
    corrected coordinates must agree. Generic off-page content remains blocking.
    """
    if not source_page.get('frame_id') or not source_page.get('nav_verified'):
        return None
    original = _box(char)
    corrected = [original[0]-2000, original[1]+2000, original[2]-2000, original[3]+2000]
    if not _inside_page(corrected, source_page['width'], source_page['height']):
        return None
    font = char.get('fontname','').split('+')[-1]
    for peer in peers:
        if peer['physical_page']==source_page['physical_page'] or peer['frame_id']!=source_page['frame_id']:
            continue
        target = peer['char']
        if target.get('text')!=char.get('text') or target.get('fontname','').split('+')[-1]!=font:
            continue
        if abs(float(target.get('size',0))-float(char.get('size',0)))>.01:
            continue
        box = _box(target)
        if not _inside_page(box,peer['width'],peer['height']):
            continue
        delta = max(abs(a-b) for a,b in zip(corrected,box))
        if delta > .1:
            continue
        return {'classification':'verified_pgf_hidden_overlay_character', 'text':char.get('text'),
            'original_bbox_pt':original,'translation_pt':[2000,2000],
            'corrected_bbox_pt':[round(v,3) for v in corrected], 'visible_bbox_pt':box,
            'max_coordinate_residual_pt':round(delta,4),'matching_tolerance_pt':.1,
            'frame_id':source_page['frame_id'],'source_physical_page':source_page['physical_page'],
            'source_character_index':source_page.get('character_index'),
            'visible_physical_page':peer['physical_page'],'visible_overlay_index':peer['overlay_index'],
            'visible_character_index':peer.get('character_index'), 'font':font,
            'evidence':'Valid nav frame + distinct overlay + identical text/font/size + visible in-page corrected bbox'}
    return None


def inspect_pdf(pdf_path: Path, output_dir: Path, *, beamer: bool = False) -> dict:
    """PDF parsers run separately and never inherit model credentials."""
    from .compiler import safe_child_env, terminate_tree
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    env = safe_child_env(Path(sys.executable), output_dir)
    env['PYTHONPATH'] = str(Path(__file__).resolve().parent.parent)
    Path(env['TEMP']).mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen([sys.executable, '-m', 'math_agent.pdfcheck', '--child'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        start_new_session=os.name != 'nt')
    payload = json.dumps({'pdf_path': str(Path(pdf_path).resolve()), 'output_dir': str(output_dir), 'beamer': beamer})
    try:
        stdout, stderr = process.communicate(payload.encode('utf-8'), timeout=480)
    except subprocess.TimeoutExpired:
        terminate_tree(process)
        raise RuntimeError('PDF_RENDER_TIMEOUT; 已保留已渲染页面。')
    if process.returncode:
        from .compiler import scrub
        raise RuntimeError('PDF inspection failed: ' + scrub(stderr.decode('utf-8', 'replace'))[-1200:])
    return json.loads(stdout)


def probe_pdf(pdf_path: Path) -> dict:
    """Fresh-output validation with the same credential-free processor boundary."""
    from .compiler import safe_child_env
    pdf_path = Path(pdf_path).resolve()
    env = safe_child_env(Path(sys.executable), pdf_path.parent)
    env['PYTHONPATH'] = str(Path(__file__).resolve().parent.parent)
    process = subprocess.run([sys.executable, '-m', 'math_agent.pdfcheck', '--probe'],
        input=json.dumps({'pdf_path': str(pdf_path)}).encode('utf-8'), capture_output=True,
        env=env, timeout=30, check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if process.returncode:
        raise ValueError('PDF parser could not open the new output: ' + process.stderr.decode('utf-8', 'replace')[-500:])
    return json.loads(process.stdout)


def measure_layout_probe(pdf_path: Path) -> dict:
    """Measure only a generated marker probe, in a credential-free PDF subprocess."""
    from .compiler import safe_child_env
    pdf_path = Path(pdf_path).resolve()
    env = safe_child_env(Path(sys.executable), pdf_path.parent)
    env['PYTHONPATH'] = str(Path(__file__).resolve().parent.parent)
    process = subprocess.run([sys.executable, '-m', 'math_agent.pdfcheck', '--measure-probe'],
        input=json.dumps({'pdf_path': str(pdf_path)}).encode('utf-8'), capture_output=True,
        env=env, timeout=30, check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if process.returncode:
        raise ValueError('Layout probe extraction failed: ' + process.stderr.decode('utf-8', 'replace')[-500:])
    return json.loads(process.stdout)


def _union_boxes(objects):
    if not objects:
        return None
    return [round(min(o['x0'] for o in objects), 3), round(min(o['top'] for o in objects), 3),
            round(max(o['x1'] for o in objects), 3), round(max(o['bottom'] for o in objects), 3)]


def _measure_layout_probe(pdf_path: Path) -> dict:
    import pdfplumber
    markers = {'large':'LargeSizeProbe', 'normalsize':'NormalSizeProbe',
               'small':'SmallSizeProbe', 'footnotesize':'FootnoteSizeProbe'}
    with pdfplumber.open(pdf_path) as document:
        for index, page in enumerate(document.pages):
            words = page.extract_words(extra_attrs=['size', 'fontname'])
            by_text = {word['text']: word for word in words}
            if 'BodyTopProbe' not in by_text or 'BodyRightProbe' not in by_text:
                continue
            titles = [w for w in words if w['text']=='FrameTitleProbe']
            if not titles or any(marker not in by_text for marker in markers.values()):
                raise ValueError('Probe marker coverage incomplete')
            title = max(titles, key=lambda w: w['size'])
            title_box = _box(title)
            headline = [w for w in words if w['bottom'] <= title['top']-1]
            footer = [w for w in words if w['top'] >= page.height * .88]
            footer_box = _union_boxes(footer)
            left, right = by_text['BodyTopProbe']['x0'], by_text['BodyRightProbe']['x1']
            region = [round(left-1,3), round(max(title['bottom']+2,by_text['BodyTopProbe']['top']-2),3), round(right+1,3),
                      round(footer_box[1]-4 if footer_box else page.height-8,3)]
            return {'status':'measured_probe', 'physical_page':index+1,
                'page_size_pt':[round(page.width,3),round(page.height,3)],
                'title_bbox_pt':title_box, 'headline_bbox_pt':_union_boxes(headline),
                'footer_bbox_pt':footer_box, 'footer_status':'measured' if footer else 'not_present',
                'body_region_estimate_pt':region,
                'body_markers':{k:_box(by_text[k]) for k in ['BodyTopProbe','BodyRightProbe']},
                'text_size_probes':{size:{'marker':marker,'size_pt':round(by_text[marker]['size'],3),
                    'font_name':by_text[marker]['fontname'],'bbox_pt':_box(by_text[marker])}
                    for size,marker in markers.items()},
                'limitations':['单个短标题与正文标记探针；不是所有标题、block、图片和长目录的完整校准。',
                    '正文区域是由真实标题/页脚/左右标记推导的保守估计；接壤风险仍需人工复核。']}
    raise ValueError('No actual PDF page contained the body markers')


def _load_layout_profile(pdf_path: Path) -> dict | None:
    path = Path(__file__).resolve().parents[2] / 'reference_index' / 'layout_probe_profiles.json'
    if not path.is_file():
        return None
    try:
        profiles = json.loads(path.read_text(encoding='utf-8'))['profiles']
        theme = 'fduclassroom' if (pdf_path.parent/'beamerthemefduclassroom.sty').exists() else 'default'
        profile = profiles[theme]
        if profile.get('engine'):
            engine_file = pdf_path.parent / '.math-agent-engine.json'
            if not engine_file.is_file():
                return None
            actual_engine = json.loads(engine_file.read_text(encoding='utf-8'))
            if actual_engine != profile['engine']:
                return None
        for relative, expected in profile['template_fingerprints'].items():
            actual = pdf_path.parent / relative
            if not actual.is_file() or hashlib.sha256(actual.read_bytes()).hexdigest() != expected:
                return None
        return profile
    except (KeyError, OSError, ValueError):
        return None


def _inspect_pdf(pdf_path: Path, output_dir: Path, *, beamer: bool = False) -> dict:
    import pdfplumber
    import pypdfium2 as pdfium

    pdf_path, output_dir = Path(pdf_path).resolve(), Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {
        'schema_version': 1, 'status': 'PASS', 'page_count': 0, 'pages': [], 'overlay_map': None,
        'renderer': {'name': 'pypdfium2', 'version': importlib.metadata.version('pypdfium2'), 'scale': 1.6},
        'geometry_engine': {'name': 'pdfplumber', 'version': importlib.metadata.version('pdfplumber')},
        'visual_review': {'status': 'NOT_RUN', 'mode': 'human', 'reviewed_page_hashes': []},
        'limitations': [
            '几何检查是启发式，只能定位可测风险，不能证明所有正文均无裁切或遮挡。',
            '尚未做模型视觉复核或教师人工逐页审核；每页图片及哈希供独立审核。',
            '数学上下标的自然小字号不判为违规；PDF 文字提取不是数学内容真值。',
            '正文安全区为未校准初始估计，实际主题区域需通过探针和人工复核校准。',
        ],
    }
    profile = _load_layout_profile(pdf_path) if beamer else None
    result['template_geometry_profile'] = profile
    if profile:
        result['limitations'][-1] = '正文安全区来自匹配模板的实际 measured_probe；仍是单个探针估计，不是完整版式校准。'
    with pdfium.PdfDocument(str(pdf_path)) as document, pdfplumber.open(pdf_path) as geometry_pdf:
        count = len(document)
        result['page_count'] = count
        if count != len(geometry_pdf.pages) or count < 1 or count > 5000:
            raise ValueError('Invalid or inconsistent PDF page count')
        result['overlay_map'] = parse_overlay_map(pdf_path.with_suffix('.nav'), count) if beamer else {
            'status': 'NOT_APPLICABLE', 'frames': [], 'pages': []}
        lookup = {p['physical_page']: p for p in result['overlay_map'].get('pages', [])}
        visible_peer_cache = {}
        def peer_characters(physical, char):
            mapping = lookup.get(physical,{})
            if result['overlay_map']['status']!='PASS' or not mapping.get('frame_id'):
                return []
            group = [p for p in result['overlay_map']['pages']
                     if p['frame_id']==mapping['frame_id'] and p['physical_page']!=physical]
            if not group:
                return []
            key = (char.get('text'),char.get('fontname','').split('+')[-1])
            candidates=[]
            for peer in group:
                peer_number=peer['physical_page']
                if peer_number not in visible_peer_cache:
                    peer_page=geometry_pdf.pages[peer_number-1]
                    index_by_glyph={}
                    for char_index,target in enumerate(peer_page.chars):
                        if target.get('text','').strip() and _inside_page(_box(target),peer_page.width,peer_page.height):
                            glyph=(target.get('text'),target.get('fontname','').split('+')[-1])
                            index_by_glyph.setdefault(glyph,[]).append({**peer,'width':peer_page.width,
                                'height':peer_page.height,'char':target,'character_index':char_index})
                    visible_peer_cache[peer_number]=index_by_glyph
                candidates.extend(visible_peer_cache[peer_number].get(key,[]))
            return candidates
        for index in range(count):
            physical = index + 1
            page = document[index]
            bitmap = page.render(scale=1.6)
            image = bitmap.to_pil()
            image_path = output_dir / f'page-{physical:04d}.png'
            image.save(image_path)
            image.close()
            bitmap.close()
            page.close()
            measured = geometry_pdf.pages[index]
            width, height = float(measured.width), float(measured.height)
            if profile and any(abs(a-b)>.1 for a,b in zip((width,height),profile['measurement']['page_size_pt'])):
                profile = None
                result['template_geometry_profile'] = None
                result['limitations'].append('PDF 页面尺寸与探针不一致，已停用旧正文区域估计。')
            chars = [c for c in measured.chars if c.get('text', '').strip()]
            raw_character_count=len(chars)
            original_indices={id(c):i for i,c in enumerate(measured.chars)}
            images = measured.images
            issues = []
            outliers = []
            hidden_objects=[]
            hidden_ids=set()
            for char in chars:
                box = _box(char)
                if not _inside_page(box,width,height):
                    mapping=lookup.get(physical,{})
                    source_info={'physical_page':physical,'frame_id':mapping.get('frame_id'),
                        'width':width,'height':height,'nav_verified':result['overlay_map']['status']=='PASS',
                        'character_index':original_indices[id(char)]}
                    match=match_pgf_hidden_character(char,source_info,peer_characters(physical,char)) if beamer else None
                    if match:
                        hidden_objects.append(match)
                        hidden_ids.add(id(char))
                        continue
                    outliers.append({'bbox': box, 'text': char.get('text', '')[:20]})
            chars=[c for c in chars if id(c) not in hidden_ids]
            if outliers:
                issues.append({'rule_id': 'PDF_CONTENT_OUTSIDE_PAGE', 'severity': 'blocking',
                    'message': '检测到文字包围盒超出物理页面边界。', 'evidence': outliers[:30],
                    'location': {'physical_page': physical}})
            image_outliers = [_box(obj) for obj in images
                if float(obj.get('x0', 0)) < -.75 or float(obj.get('top', 0)) < -.75
                or float(obj.get('x1', 0)) > width + .75 or float(obj.get('bottom', 0)) > height + .75]
            if image_outliers:
                issues.append({'rule_id': 'PDF_IMAGE_OUTSIDE_PAGE', 'severity': 'blocking',
                    'message': '检测到图像超出物理页面边界。', 'evidence': image_outliers[:30],
                    'location': {'physical_page': physical}})
            if not chars and not images:
                issues.append({'rule_id': 'POSSIBLE_EMPTY_PAGE', 'severity': 'review',
                    'message': '页面没有可抽取文字或图像，需要检查矢量内容和空白。',
                    'location': {'physical_page': physical}})
            minimum_size = min(p['size_pt'] for p in profile['measurement']['text_size_probes'].values())-.3 if profile else 7.5
            def region_role(char):
                if not profile:
                    return 'unknown_region'
                measured_profile = profile['measurement']
                footer_box = measured_profile['footer_bbox_pt']
                if footer_box and char['top'] >= footer_box[1]-2:
                    return 'footer'
                if char['bottom'] <= measured_profile['title_bbox_pt'][1]-1:
                    return 'headline'
                if char['top'] <= measured_profile['title_bbox_pt'][3]+1:
                    return 'frame_title'
                return 'body'
            small_cjk = [{'text': c.get('text'), 'size_pt': round(float(c.get('size', 0)), 3), 'bbox': _box(c), 'region':region_role(c)}
                for c in chars if any('\u3400' <= letter <= '\u9fff' for letter in c.get('text', ''))
                and float(c.get('size', 0)) < minimum_size]
            if beamer and small_cjk:
                issues.append({'rule_id': 'SUSPICIOUS_SMALL_CJK', 'severity': 'review',
                    'message': '存在小于初始 footnotesize 参考值的中文文本，需核对模板有效字体。',
                    'evidence': small_cjk[:30], 'location': {'physical_page': physical}})
            body_contacts = []
            if profile:
                body_region = profile['measurement']['body_region_estimate_pt']
                for char in chars:
                    if region_role(char) != 'body':
                        continue
                    if char['top'] < body_region[1]+1 or char['bottom'] > body_region[3]-1:
                        body_contacts.append({'text':char.get('text','')[:20], 'bbox':_box(char),
                                              'region':'body', 'boundary':'header' if char['top']<body_region[1]+1 else 'footer'})
                if body_contacts:
                    issues.append({'rule_id':'BODY_REGION_CONTACT', 'severity':'review',
                        'message':'正文文字接近或跨过实测探针估计的标题/页脚安全边界，需结合页面复核。',
                        'evidence':body_contacts[:30], 'location':{'physical_page':physical}})
            bbox = None if not chars else [round(min(c['x0'] for c in chars), 3),
                round(min(c['top'] for c in chars), 3), round(max(c['x1'] for c in chars), 3),
                round(max(c['bottom'] for c in chars), 3)]
            sizes = sorted(set(round(float(c.get('size', 0)), 3) for c in chars))
            mapping = lookup.get(physical, {'frame_id': None, 'overlay_index': None})
            result['pages'].append({
                'physical_page': physical, 'frame_id': mapping['frame_id'], 'overlay_index': mapping['overlay_index'],
                'image_path': str(image_path), 'sha256': hashlib.sha256(image_path.read_bytes()).hexdigest(),
                'geometry': {'page_width_pt': round(width, 3), 'page_height_pt': round(height, 3),
                    'text_bbox_pt': bbox, 'character_count': len(chars), 'image_count': len(images),
                    'raw_character_count':raw_character_count,'pgf_hidden_character_count':len(hidden_objects),
                    'line_count': len(measured.lines), 'rectangle_count': len(measured.rects),
                    'font_sizes_pt': sizes, 'font_names': sorted(set(c.get('fontname', '') for c in chars)),
                    'body_region': {'bbox_pt': profile['measurement']['body_region_estimate_pt'] if profile else
                                    ([8.0, 30.0, round(width - 8, 3), round(height - 14, 3)] if beamer else None),
                                    'calibration_status': 'measured_probe' if profile else 'uncalibrated',
                                    'profile_fingerprint': profile.get('profile_sha256') if profile else None},
                    'text_outside_page_count': len(outliers), 'image_outside_page_count': len(image_outliers)},
                'issues': issues, 'review_status': 'NOT_RUN', 'overlay_hidden_objects':hidden_objects,
            })
    image_hashes={p['physical_page']:p['sha256'] for p in result['pages']}
    for page in result['pages']:
        for hidden in page['overlay_hidden_objects']:
            hidden['source_page_image_sha256']=page['sha256']
            hidden['visible_page_image_sha256']=image_hashes[hidden['visible_physical_page']]
    if any(i['severity'] == 'blocking' for p in result['pages'] for i in p['issues']):
        result['status'] = 'FAIL'
    elif any(p['issues'] for p in result['pages']):
        result['status'] = 'NEEDS_REVIEW'
    if beamer and result['overlay_map']['status'] != 'PASS':
        result['status'] = 'FAIL'
    result['issues'] = [i for p in result['pages'] for i in p['issues']]
    if beamer and result['overlay_map']['status'] != 'PASS':
        result['issues'].append({'rule_id': 'OVERLAY_MAP_INCOMPLETE', 'severity': 'blocking',
            'message': '实际 nav 映射没有完整对应 PDF 页数。', 'evidence': result['overlay_map']['issues']})
    return result


if __name__ == '__main__' and '--child' in sys.argv:
    request = json.loads(sys.stdin.buffer.read(65536))
    response = _inspect_pdf(Path(request['pdf_path']), Path(request['output_dir']), beamer=request.get('beamer', False))
    sys.stdout.buffer.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
elif __name__ == '__main__' and '--probe' in sys.argv:
    import pypdfium2 as pdfium
    request = json.loads(sys.stdin.buffer.read(65536))
    with pdfium.PdfDocument(request['pdf_path']) as document:
        response = {'page_count': len(document)}
    sys.stdout.buffer.write(json.dumps(response).encode('utf-8'))
elif __name__ == '__main__' and '--measure-probe' in sys.argv:
    request = json.loads(sys.stdin.buffer.read(65536))
    response = _measure_layout_probe(Path(request['pdf_path']))
    sys.stdout.buffer.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
