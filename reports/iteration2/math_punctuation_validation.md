# CH03 Chinese punctuation missing-glyph recovery

Actual run `a45be503af594ce8aae0bb1e4c30184b` failed compilation in S01 after two local repairs. The final source contained seven bare Chinese full stops (`。`, U+3002) in explicit display mathematics: S01.U08 × 1, S01.U09 × 2, S01.U11 × 2, S01.U13 × 2. XeLaTeX reported all seven as missing from Latin Modern Roman. A PDF existed, but the compiler correctly retained `FAIL`; PDF existence was not treated as successful output.

The exact original source, compile JSON, all four compiler logs, raw and normalized candidates, and final repair record are copied under `math-punctuation/original-failure/`. `math-punctuation/original-manifest.json` records hashes. The original workspace files and approval are untouched.

The fragment normalizer now recognizes explicit math delimiters (`$`, `$$`, `\(`, `\[`) and known display environments. Only ungrouped literal punctuation from `。，；：！？、` is wrapped as `\text{original character}`. It inserts a font-selection wrapper while retaining each original punctuation character, surrounding mathematical tokens and Chinese text. It neither substitutes ASCII punctuation nor deletes missing characters.

This is deliberately conservative: prose, comments, verbatim, existing text arguments, unknown macro arguments, grouped expressions, superscript/subscript positions and delimiter arguments are left unchanged. Ambiguous/unbalanced structures preserve the original unit and block normalization. Unhandled glyph problems remain subject to the unchanged compiler missing-glyph gate. This is not a general TeX expansion parser.

Normalizer evidence schema 3 records the exact character span, original character, replacement, coordinate space and before/after hashes separately from teaching-shell and equation-label changes. Repeating normalization is idempotent. Unit IDs/relations, explicit calculations, calculation limitations and uncertainties remain unchanged. The captured CH03 test verifies that removing only the seven inserted `\text{...}` wrappers recovers the original source exactly.

Evidence and outcomes:

- `math_punctuation_red.log`: 9 failing fixtures before the implementation, 11 existing/no-change cases passed.
- `math_punctuation_targeted.log/.xml`: 59 passed in 21.66 seconds, including existing wrapper and equation-reference tests and actual Windows compilation.
- `math_punctuation_final.log/.xml`: 24 passed in 8.14 seconds after adding explicit superscript, delimiter and grouped-expression exclusions.
- `math-punctuation/pre-post-evidence.json` and `validation-summary.json`: actual Windows XeLaTeX compiled the captured source before and after normalization. Before is `FAIL` with exactly seven missing-glyph issues; after is `PASS`. Both have three pages. PDFs, sources and full compile logs are preserved as `before.*`, `after.*`, `before-logs/` and `after-logs/`.

No model API call, worker/driver restart or change to the original failed run occurred in this work. Model fixtures are offline. These results prove the measured source/compiler behavior; automated layout inspection and teacher visual acceptance of the repaired PDF are NOT_RUN in this validation. No missing-glyph rule was weakened.
