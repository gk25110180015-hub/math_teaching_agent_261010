"""A bounded textual review hint must separate asserted formulae from taught errors."""
import pytest

from math_agent.mathcheck import _static_checks


def issues(tex):
    return [item for item in _static_checks([{'id': 'topic.item.9', 'kind': 'example', 'tex': tex}])
            if item['rule_id'] == 'SERIES_FIRST_TERM_DOMAIN_REVIEW']


@pytest.mark.unit
@pytest.mark.parametrize('tex,index', [
    (r'判断级数 $\sum_{n=1}^{\infty}\frac{1}{n\ln n}$ 的敛散性。', 1),
    (r'判断级数 \[\sum_{k=1}^{\infty}\frac{2}{k\log(k)}.\]', 1),
    (r'\[\sum\limits_{j=0}^{\infty}\dfrac{1}{j\,\ln{j}}\]', 0),
    (r'\[\sum_{m=1}^{\infty}\tfrac{3}{m^{2}\cdot\ln m}\]', 1),
    (r'\[\sum_{n=1}^{\infty}\frac{0}{n\ln n}\]', 1),
    (r'\[\sum_{n=1}^{\infty}\frac{1}{n\ln n}\]其中该级数从 $n=2$ 开始。', 1),
    (r'\begin{equation}\sum_{n=1}^{\infty}\frac{1}{n\ln n}\end{equation}', 1),
])
def test_supported_undefined_formula_has_precise_nonblocking_location(tex, index):
    result = issues(tex)
    assert len(result) == 1, result
    assert result[0]['severity'] == 'review'
    location = result[0]['location']
    assert location['unit_id'] == 'topic.item.9'
    assert location['at_index'] == index
    assert tex[location['start']:location['end']].startswith(r'\sum')
    assert tex[location['start']:location['end']].endswith('}')


@pytest.mark.unit
@pytest.mark.parametrize('tex', [
    r'判断 $\sum_{n=2}^{\infty}\frac{1}{n\ln n}$。',
    r'正确公式 $\sum_{n=2}^{\infty}\frac{1}{n\ln n}$。错误做法是把起点写成1。',
    r'错误示例：$\sum_{n=1}^{\infty}\frac{1}{n\ln n}$，应将起点改为2。',
    r'错误辨析：下列写法哪里有错？\[\sum_{n=1}^{\infty}\frac{1}{n\ln n}\]',
    r'$\sum_{n=1}^{\infty}\frac{1}{n\ln n}$ 的首项无定义，不能这样书写。',
    r'\verb|$\sum_{n=1}^{\infty}\frac{1}{n\ln n}$|',
    r'\begin{verbatim}$\sum_{n=1}^{\infty}\frac{1}{n\ln n}$\end{verbatim}',
    r'\iffalse $\sum_{n=1}^{\infty}\frac{1}{n\ln n}$ \fi',
    '% $\\sum_{n=1}^{\\infty}\\frac{1}{n\\ln n}$\n文字。',
    r'$\sum_{n=1}^{\infty}\frac{1}{n^2}$',
    r'$\frac{1}{n\ln n}$ 在n>1有定义。',
    r'$\sum_{k=1}^{\infty}\frac{1}{n\ln n}$',
    r'$\sum_{n=N}^{\infty}\frac{1}{n\ln n}$',
    r'$\sum_{n=1}^{\infty}\frac{1}{n\lnn}$',
    r'$\sum_{n=1}^{\infty}\frac{1}{n\log_{2}n}$',
])
def test_valid_quoted_or_unsupported_notation_is_not_flagged(tex):
    assert issues(tex) == []
