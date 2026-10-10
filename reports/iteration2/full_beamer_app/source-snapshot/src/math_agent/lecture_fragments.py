"""Normalize explicit generated TeX structure without rewriting mathematical bodies."""
from __future__ import annotations

import copy
import re
from collections import Counter

from .parsing import _mask_verbatim, uncomment
from .util import digest


TEACHING_ENVIRONMENTS = {'definition','theorem','proof','example','exercise','solution'}
_LABEL = re.compile(r'^[A-Za-z][A-Za-z0-9:._-]{0,119}$')
_COMMAND = re.compile(r'\\(?:(begin|end)\s*\{([A-Za-z][A-Za-z0-9*]*)\}|([A-Za-z@]+|[\s\S]))')
_BODY_TOKEN = re.compile(_COMMAND.pattern + r'|[{}]')
_DISPLAY_ENVIRONMENTS = {'equation','equation*','align','align*','alignat','alignat*',
    'flalign','flalign*','gather','gather*','multline','multline*','eqnarray','eqnarray*','displaymath'}
_INNER_MATH_ENVIRONMENTS = {'aligned','alignedat','gathered','split','array','cases',
    'matrix','pmatrix','bmatrix','Bmatrix','vmatrix','Vmatrix','smallmatrix'}


def _label_counts(units):
    counts=Counter()
    for unit in units:
        clean=uncomment(_mask_verbatim(unit['tex']))
        for token in _COMMAND.finditer(clean):
            if token.group(3)=='label':
                argument=re.match(r'\s*\{([^{}]*)\}',clean[token.end():])
                if argument:
                    counts[argument[1]]+=1
    return counts


def _number_labeled_displays(raw, label_counts):
    """Promote one untagged, uniquely labeled display to one equation number.

    Only the two delimiter tokens are replaced. Labelled ambiguous displays are
    rejected; explicitly tagged or already numbered mathematics stays intact.
    Coordinates refer to the input *after* any teaching shell was removed.
    """
    clean=uncomment(_mask_verbatim(raw))
    stack=[]; opening=None; enclosing=[]; spans=[]
    for token in _COMMAND.finditer(clean):
        command,name,simple=token.groups()
        if command=='begin':
            stack.append(name)
        elif command=='end':
            if stack:
                stack.pop()
        elif simple=='[':
            if opening is not None:
                raise ValueError('Nested display delimiters require review')
            opening=token;enclosing=list(stack)
        elif simple==']' and opening is not None:
            start,end=opening.end(),token.start()
            body=clean[start:end]
            labels=[]; tagged=False; suppressed=False; braces=0; nested=False
            for part in _BODY_TOKEN.finditer(body):
                begin_or_end,env,macro=part.groups()
                if part[0]=='{':
                    braces+=1
                elif part[0]=='}':
                    braces-=1
                elif begin_or_end=='begin' and env in _DISPLAY_ENVIRONMENTS:
                    nested=True
                elif macro=='label':
                    argument=re.match(r'\s*\{([^{}]*)\}',body[part.end():])
                    labels.append((argument[1] if argument else None,braces))
                elif macro=='tag':
                    tagged=True
                elif macro in ('notag','nonumber'):
                    suppressed=True
            if labels:
                if (len(labels)!=1 or labels[0][0] is None or not _LABEL.fullmatch(labels[0][0])
                        or label_counts[labels[0][0]]!=1 or labels[0][1]!=0):
                    raise ValueError('A labeled display needs exactly one unique literal ungrouped label')
                if nested or set(enclosing)&(_DISPLAY_ENVIRONMENTS|_INNER_MATH_ENVIRONMENTS):
                    raise ValueError('A labeled display nested in display mathematics requires review')
                if suppressed:
                    raise ValueError('A labeled display explicitly suppresses numbering; review required')
                if not tagged:
                    spans.append({'label':labels[0][0],
                        'opening_span':{'start':opening.start(),'end':opening.end()},
                        'closing_span':{'start':token.start(),'end':token.end()},
                        'coordinate_space':'after_teaching_shell_normalization',
                        'preserved_body_hash':digest(raw[start:end]),
                        'mathematical_body_preserved':True,
                        'action':'labeled_unnumbered_display_to_equation'})
            opening=None;enclosing=[]
    output=raw
    for span in reversed(spans):
        first,last=span['opening_span'],span['closing_span']
        output=(output[:first['start']]+r'\begin{equation}'+output[first['end']:last['start']]
                +r'\end{equation}'+output[last['end']:])
    return output,spans


def _optional_title(text, offset):
    cursor=offset
    while cursor<len(text) and text[cursor].isspace():
        cursor+=1
    if cursor==len(text) or text[cursor]!='[':
        return None,offset
    start=cursor+1; square=1; braces=0; cursor+=1
    while cursor<len(text):
        char=text[cursor]
        if char=='\\':
            cursor+=2
            continue
        if char=='{':
            braces+=1
        elif char=='}':
            braces-=1
            if braces<0:
                raise ValueError('Optional title has unbalanced braces')
        elif char=='[' and braces==0:
            square+=1
        elif char==']' and braces==0:
            square-=1
            if square==0:
                return (start,cursor),cursor+1
        cursor+=1
    raise ValueError('Optional title is unclosed')


def _teaching_nodes(raw):
    clean=uncomment(_mask_verbatim(raw))
    stack=[]; nodes=[]; braces=0; math_mode=None; cursor=0
    while cursor<len(clean):
        char=clean[cursor]
        if char=='\\':
            match=re.match(r'\\(begin|end)\s*\{([A-Za-z][A-Za-z0-9*]*)\}',clean[cursor:])
            if match:
                command,name=match.groups()
                end=cursor+len(match[0])
                if command=='begin':
                    title,content_start=_optional_title(clean,end)
                    node={'name':name,'start':cursor,'opening_end':content_start,
                        'title_span':title,'top_level':not stack and braces==0 and math_mode is None}
                    stack.append(node)
                    if name in TEACHING_ENVIRONMENTS:
                        nodes.append(node)
                    cursor=content_start
                else:
                    if not stack or stack[-1]['name']!=name:
                        raise ValueError('Unbalanced or mismatched TeX environment')
                    node=stack.pop()
                    node.update(closing_start=cursor,end=end)
                    cursor=end
                continue
            pair=clean[cursor:cursor+2]
            if pair in (r'\[',r'\('):
                if math_mode is not None:
                    raise ValueError('Nested math delimiters require review')
                math_mode=pair
            elif pair in (r'\]',r'\)'):
                expected=r'\[' if pair==r'\]' else r'\('
                if math_mode!=expected:
                    raise ValueError('Mismatched math delimiters require review')
                math_mode=None
            command=re.match(r'\\(?:[A-Za-z@]+|.)',clean[cursor:])
            cursor+=len(command[0]) if command else 1
            continue
        if char=='$':
            delimiter='$$' if clean[cursor:cursor+2]=='$$' else '$'
            if math_mode is None:
                math_mode=delimiter
            elif math_mode==delimiter:
                math_mode=None
            else:
                raise ValueError('Mixed math delimiters require review')
            cursor+=len(delimiter)
            continue
        if char=='{':
            braces+=1
        elif char=='}':
            braces-=1
            if braces<0:
                raise ValueError('Unbalanced closing brace')
        cursor+=1
    if stack or braces or math_mode is not None:
        raise ValueError('Unclosed environment, group or math delimiter')
    return nodes


def normalize_written_section(data: dict) -> tuple[dict, dict]:
    """Keep IDs/relations/body bytes; reject ambiguous shells instead of flattening.

    Matching optional titles become ``\\textbf{original title}\\par`` at the
    original shell opening. Evidence BLOCKED means the caller must not treat this
    as a normalized, validated section. This function is not a TeX safety gate.
    """
    result=copy.deepcopy(data)
    evidence={'schema_version':2,'status':'PASS','raw_hash':digest(data),'normalized_hash':None,
        'units':[],'issues':[], 'mathematical_content_rewritten':False,
        'limitations':['只处理单个明确匹配的顶层教学环境外壳；不推断自定义环境语义。',
            '可选标题保留为正文加粗标题，不改变内部数学或环境外解释。',
            '带唯一合法标签且无显式编号、无嵌套显示数学的无编号公式仅替换定界符为 equation；数学正文逐字保留。',
            '标签唯一性在当前节检查，跨节标签由独立交叉引用检查负责；已有显式 tag 不改写。',
            '归一化不是数学核验、安全预检或教师验收。']}
    label_counts=_label_counts(result.get('units',[]))
    for unit in result.get('units',[]):
        raw=unit['tex']
        record={'unit_id':unit.get('id'),'kind':unit.get('kind'),'raw_hash':digest(raw),
            'normalized_hash':digest(raw),'action':'unchanged','removed_spans':[], 'equation_normalizations':[]}
        try:
            normalized=raw
            nodes=_teaching_nodes(raw)
            if nodes:
                if len(nodes)!=1 or not nodes[0]['top_level']:
                    raise ValueError('Nested, grouped or multiple teaching wrappers are ambiguous')
                node=nodes[0]
                if node['name']!=unit.get('kind'):
                    raise ValueError('Teaching environment does not match declared unit kind')
                title_span=node['title_span']
                title=raw[title_span[0]:title_span[1]] if title_span else None
                replacement='\\textbf{'+title+'}\\par\n' if title else ''
                normalized=(raw[:node['start']]+replacement+raw[node['opening_end']:node['closing_start']]+raw[node['end']:])
                record.update(action='matching_top_level_shell_removed',normalized_hash=digest(normalized),
                    removed_spans=[{'start':node['start'],'end':node['opening_end'],'role':'opening_and_optional_title'},
                        {'start':node['closing_start'],'end':node['end'],'role':'closing'}],
                    preserved_title=title,title_strategy='bold_body_title' if title else 'not_present',
                    preserved_prefix_hash=digest(raw[:node['start']]),
                    preserved_body_hash=digest(raw[node['opening_end']:node['closing_start']]),
                    preserved_suffix_hash=digest(raw[node['end']:]))
            record['display_normalization_input_hash']=digest(normalized)
            normalized,displays=_number_labeled_displays(normalized,label_counts)
            if displays:
                record['action']=('matching_top_level_shell_removed_and_labeled_displays_numbered'
                    if nodes else 'labeled_displays_numbered')
            record.update(equation_normalizations=displays,normalized_hash=digest(normalized))
            unit['tex']=normalized
        except ValueError as exc:
            unit['tex']=raw
            record.update(action='blocked_unchanged',normalized_hash=digest(raw),removed_spans=[],equation_normalizations=[])
            evidence['status']='BLOCKED'
            evidence['issues'].append({'rule_id':'LECTURE_FRAGMENT_AMBIGUOUS','severity':'blocking',
                'unit_id':unit.get('id'),'message':str(exc),'raw_hash':digest(raw)})
        evidence['units'].append(record)
    evidence['normalized_hash']=digest(result)
    evidence['unit_ids_preserved']=[u.get('id') for u in data.get('units',[])]==[u.get('id') for u in result.get('units',[])]
    evidence['relations_preserved']=[u.get('relates_to') for u in data.get('units',[])]==[u.get('relates_to') for u in result.get('units',[])]
    return result,evidence
