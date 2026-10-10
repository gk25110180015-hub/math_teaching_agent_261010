"""Preserve source theorem environments without redefining Beamer's built-ins."""
from __future__ import annotations

import re

from .parsing import _group, _optional, uncomment


# Mathematical Greek in plain model/user headings must use math fonts: Latin
# Modern Sans has no Greek text glyphs. Keep variant letters distinct.
TITLE_GREEK_MATH = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "ε": r"\varepsilon", "ϵ": r"\epsilon", "ζ": r"\zeta", "η": r"\eta",
    "θ": r"\theta", "ϑ": r"\vartheta", "ι": r"\iota", "κ": r"\kappa",
    "ϰ": r"\varkappa", "λ": r"\lambda", "μ": r"\mu", "ν": r"\nu",
    "ξ": r"\xi", "ο": "o", "π": r"\pi", "ϖ": r"\varpi",
    "ρ": r"\rho", "ϱ": r"\varrho", "σ": r"\sigma", "ς": r"\varsigma",
    "τ": r"\tau", "υ": r"\upsilon", "φ": r"\varphi", "ϕ": r"\phi",
    "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega",
    "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda",
    "Ξ": r"\Xi", "Π": r"\Pi", "Σ": r"\Sigma", "Υ": r"\Upsilon",
    "Φ": r"\Phi", "Ψ": r"\Psi", "Ω": r"\Omega",
    **{greek: r"\mathrm{" + latin + "}" for greek, latin in
       zip("ΑΒΕΖΗΙΚΜΝΟΡΤΧ", "ABEZHIKMNOPTX")},
}


# Beamer declares these environments with the theorem counter, so it has no
# separate c@definition, c@example, etc. A source shared counter must follow it.
_SHARED_THEOREM_COUNTERS = {
    "corollary", "fact", "lemma", "problem", "solution", "definition",
    "definitions", "example", "examples",
}


def theorem_environment_preamble(parsed: dict) -> str:
    """Keep unknown/source exercise environments, including cached opaque units."""
    declarations = []
    for item in parsed.get("macros", {}).get("definitions", []):
        if item.get("command") in {"newenvironment", "NewDocumentEnvironment"} and item.get("name") == "exercise":
            declarations.append(r"\@ifundefined{exercise}{" + item["raw_tex"] + "}{}")
            continue
        if item.get("command") != "newtheorem":
            continue
        raw = uncomment(item["raw_tex"]).strip()
        match = re.match(r"\\newtheorem(\*)?\s*", raw)
        if not match:
            continue
        name, end = _group(raw, match.end())
        shared, label_start = _optional(raw, end)
        label, label_end = _group(raw, label_start)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9@]*", name):
            continue
        declaration = raw
        if shared in _SHARED_THEOREM_COUNTERS:
            # Select at TeX execution time: a theme may provide a real counter.
            fallback = r"\newtheorem{" + name + r"}[theorem]{" + label + "}"
            declaration = (r"\@ifundefined{c@" + shared + "}{" + fallback
                           + "}{" + raw + "}")
        if label in {"练习", "习题", "问题"} or name == "exercise":
            declaration = r"\theoremstyle{definition}" + declaration + r"\theoremstyle{plain}"
        declarations.append(r"\@ifundefined{" + name + "}{" + declaration + "}{}")
    # Exercise is also a supported scanner environment without a declaration.
    declarations.append(r"\@ifundefined{exercise}{\theoremstyle{definition}\newtheorem{exercise}[theorem]{练习}\theoremstyle{plain}}{}")
    return "\n".join([r"\makeatletter", *declarations, r"\makeatother"])


SECTION_LABEL_PREAMBLE = r"""\makeatletter
\newcommand{\mathagentsectionlabelcontext}{%
\protected@edef\@currentlabel{\thesection}%
\edef\@currentHref{Outline\the\c@part.\the\c@section}%
}
\newcommand{\mathagentexerciselabelcontext}[1]{%
\hypertarget<1>{#1}{}%
\edef\@currentHref{#1}%
}
\makeatother"""


def leading_section_label_unit(section: dict, units: dict) -> str | None:
    """Only labels immediately following the original heading bind to a section."""
    ids = section.get("source_unit_ids", [])
    if not ids:
        return None
    unit = units.get(ids[0], {})
    if unit.get("kind") != "explanation" or unit.get("environment"):
        return None
    if re.match(r"\s*\\label\s*\{", uncomment(unit.get("raw_tex", ""))):
        return unit["id"]
    return None
