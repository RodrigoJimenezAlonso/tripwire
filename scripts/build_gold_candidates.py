"""Build candidate gold.yaml from per-page text extracted with pdftotext -layout.

Every item's `evidence` must appear verbatim (whitespace-collapsed) on its
primary page, otherwise the script aborts. Extra pages are added to `pages`
only when they contain both the formatted number and the item's keyword.
"""
import re
import sys
from pathlib import Path

TXT = Path(sys.argv[1])
OUT = Path(sys.argv[2])
NPAGES = {"sika": 285, "swissre": 327, "ubs": 380}


def norm(s: str) -> str:
    s = s.replace("­", "").replace("–", "-").replace(" ", " ")
    return re.sub(r"\s+", " ", s)


def page(doc: str, p: int) -> str:
    return norm((TXT / f"{doc}-{p:03d}.txt").read_text(encoding="utf-8"))


# (id, doc, difficulty, question, answer, value, unit, primary_page, evidence, number_token, keyword, notes)
ITEMS = [
    # ---------------- Sika ----------------
    ("sika-net-sales-2025", "sika", "easy",
     "What were Sika's net sales in the 2025 financial year?",
     "CHF 11,201.3 million", 11201.3, "CHF mn", 5,
     "In 2025, Sika generated sales of CHF 11,201.3 million", "11,201.3", r"sales",
     "At a glance; also five-year review and income statement"),
    ("sika-ebitda-reported-2025", "sika", "easy",
     "What was Sika's reported EBITDA for 2025, including the one-off Fast Forward costs?",
     "CHF 2,064.7 million", 2064.7, "CHF mn", 5,
     "CHF 2,064.7 million (2024: CHF 2,269.5 million)", "2,064.7", r"EBITDA",
     "reported figure, not adjusted"),
    ("sika-ebitda-margin-adjusted-2025", "sika", "hard",
     "Excluding the one-off costs of the Fast Forward programme, what EBITDA margin did Sika achieve in 2025?",
     "19.2%", 19.2, "%", 5,
     "the EBITDA margin was 19.2%", "19.2%", r"Fast Forward",
     "trap: reported margin is 18.4%"),
    ("sika-net-profit-2025", "sika", "easy",
     "How much net profit did Sika report for 2025?",
     "CHF 1,045.3 million", 1045.3, "CHF mn", 5,
     "Net profit for 2025 was CHF 1,045.3 million", "1,045.3", r"[Nn]et profit",
     "includes non-controlling interests; attributable to shareholders is 1,044.0"),
    ("sika-lc-sales-growth-2025", "sika", "easy",
     "By how much did Sika's sales grow in local currencies in 2025?",
     "+0.6%", 0.6, "%", 31,
     "+0.6%", "0.6%", r"local currenc",
     "group performance; currency effect was -5.4%"),
    ("sika-organic-growth-2025", "sika", "hard",
     "What was Sika's organic sales growth for the full year 2025?",
     "-0.4%", -0.4, "%", 32,
     "Organic growth for full year 2025 was -0.4%", "-0.4%", r"[Oo]rganic",
     "text, two-column layout; +1.2% excluding Chinese construction business"),
    ("sika-basic-eps-2025", "sika", "hard",
     "What were Sika's basic earnings per share in 2025?",
     "CHF 6.51", 6.51, "CHF/share", 218,
     "Basic earnings per share (in CHF) 9 7.76 6.51", "6.51", r"earnings per share",
     "consolidated income statement; diluted is 6.50"),
    ("sika-dividend-2025", "sika", "easy",
     "What dividend per share does Sika's board propose for the 2025 financial year?",
     "CHF 3.70", 3.70, "CHF/share", 9,
     "DIVIDEND PER SHARE CHF 3.70", "3.70", r"[Dd]ividend",
     "proposal to AGM of 24 March 2026; 2024: CHF 3.60"),
    ("sika-employees-2025", "sika", "easy",
     "How many people did Sika employ at the end of 2025?",
     "33,707 employees", 33707, "count", 112,
     "workforce consists of 33,707 employees", "33,707", r"[Ee]mployees",
     "sustainability report; also facts & figures and five-year review"),
    ("sika-net-debt-2025", "sika", "hard",
     "What was Sika's net debt at the end of 2025?",
     "CHF 4,734.5 million", 4734.5, "CHF mn", 268,
     "Net debt 1 f 2,547.1 2,051.6 5,219.7 5,039.6 4,734.5", "4,734.5", r"[Nn]et debt",
     "key balance sheet data, five-year review"),
    ("sika-americas-ebitda-2025", "sika", "hard",
     "What EBITDA did Sika's Americas region generate in 2025?",
     "CHF 850 million", 850, "CHF mn", 266,
     "907 850", "850", r"Americas",
     "segment information, five-year review; multi-column table (EMEA and Americas side by side)"),
    # ---------------- Swiss Re ----------------
    ("swissre-net-income-2025", "swissre", "easy",
     "What net income did the Swiss Re Group report for 2025?",
     "USD 4,762 million (about USD 4.8 billion)", 4762, "USD mn", 14,
     "Net income/loss 4 762 3 238 47", "4 762", r"[Nn]et income",
     "income statement; highlights round it to USD 4.8 bn (pages 3, 6, 13)"),
    ("swissre-roe-2025", "swissre", "easy",
     "What return on equity did Swiss Re achieve in 2025?",
     "19.6%", 19.6, "%", 6,
     "an ROE of 19.6%", "19.6%", r"ROE|[Rr]eturn on equity",
     "financial highlights"),
    ("swissre-sst-ratio", "swissre", "easy",
     "What was Swiss Re's estimated Group Swiss Solvency Test ratio as of 1 January 2026?",
     "250%", 250, "%", 6,
     "250%", "250%", r"SST|Solvency",
     "estimate, subject to FINMA review; 1 Jan 2025: 257%"),
    ("swissre-insurance-revenue-2025", "swissre", "hard",
     "How much insurance revenue did the Swiss Re Group record in 2025?",
     "USD 43,136 million (about USD 43.1 billion)", 43136, "USD mn", 14,
     "Insurance revenue 43 136 45 598 -5", "43 136", r"[Ii]nsurance revenue",
     "income statement; numbers use space as thousands separator"),
    ("swissre-pcre-combined-ratio-2025", "swissre", "easy",
     "What combined ratio did Swiss Re's Property & Casualty Reinsurance business achieve in 2025?",
     "79.4%", 79.4, "%", 6,
     "79.4% 86.5%", "79.4", r"[Cc]ombined ratio",
     "trap: Corporate Solutions is 86.5% in the same row"),
    ("swissre-cs-combined-ratio-2025", "swissre", "easy",
     "What was the combined ratio of Swiss Re Corporate Solutions in 2025?",
     "86.5%", 86.5, "%", 6,
     "79.4% 86.5%", "86.5", r"[Cc]ombined ratio",
     "trap: P&C Re is 79.4% in the same row"),
    ("swissre-eps-usd-2025", "swissre", "hard",
     "What were Swiss Re's earnings per share for 2025 in US dollars?",
     "USD 15.67", 15.67, "USD/share", 13,
     "USD 15.67 or CHF 13.05", "15.67", r"[Ee]arnings per share",
     "group results text; CHF equivalent 13.05"),
    ("swissre-dividend-2025", "swissre", "easy",
     "What ordinary dividend per share has Swiss Re proposed for the 2025 financial year?",
     "USD 8.00", 8.00, "USD/share", 6,
     "dividend of USD 8.00 per share to be paid", "8.00", r"[Dd]ividend",
     "paid in 2026; +9%"),
    ("swissre-headcount-2025", "swissre", "hard",
     "What was Swiss Re's total headcount at the end of 2025?",
     "15,238 persons", 15238, "count", 77,
     "Headcount1 number of persons 15 238 15 360 15 032", "15 238", r"[Hh]eadcount",
     "sustainability report employee data table; permanent employees only: 14,893"),
    # ---------------- UBS ----------------
    ("ubs-net-profit-2025", "ubs", "easy",
     "What net profit attributable to shareholders did UBS Group report for 2025?",
     "USD 7,767 million", 7767, "USD mn", 10,
     "Net profit / (loss) attributable to shareholders 7,767 5,085 27,366", "7,767", r"[Nn]et profit",
     "key figures table"),
    ("ubs-cet1-ratio-2025", "ubs", "easy",
     "What was UBS's common equity tier 1 capital ratio at the end of 2025?",
     "14.4%", 14.4, "%", 10,
     "Common equity tier 1 capital ratio (%)6 14.4 14.3 14.3", "14.4", r"(CET1|tier 1 capital ratio)",
     "key figures table"),
    ("ubs-rote-reported-2025", "ubs", "hard",
     "What was UBS's reported (not underlying) return on tangible equity for 2025?",
     "9.5%", 9.5, "%", 10,
     "Return on tangible equity (%)3 9.5 6.5 40.8", "9.5", r"tangible equity",
     "trap: underlying RoTE is 12.1% one row below"),
    ("ubs-underlying-cost-income-2025", "ubs", "hard",
     "What was UBS's underlying cost/income ratio in 2025?",
     "74.4%", 74.4, "%", 10,
     "Underlying cost / income ratio (%)3,4,5 74.4 79.5 87.2", "74.4", r"cost / income",
     "trap: reported is 81.1%"),
    ("ubs-diluted-eps-2025", "ubs", "easy",
     "What were UBS's diluted earnings per share for 2025?",
     "USD 2.36", 2.36, "USD/share", 10,
     "Diluted earnings per share (USD)1 2.36 1.52 8.30", "2.36", r"[Ee]arnings per share",
     "key figures table"),
    ("ubs-internal-fte-2025", "ubs", "easy",
     "How many internal staff, measured in full-time equivalents, did UBS have at the end of 2025?",
     "103,177 FTE", 103177, "count", 10,
     "Internal personnel (full-time equivalents) 103,177 108,648 112,842", "103,177", r"personnel",
     "trap: internal + external personnel is 119,589"),
    ("ubs-invested-assets-2025", "ubs", "easy",
     "What was the total of UBS's invested assets at the end of 2025?",
     "USD 7,005 billion (about USD 7.0 trillion)", 7005, "USD bn", 10,
     "Invested assets (USD bn)3,8 7,005 6,087 5,714", "7,005", r"[Ii]nvested assets",
     "GWM + AM + P&C; GWM alone is 4,753"),
    ("ubs-underlying-pbt-2025", "ubs", "hard",
     "What was UBS Group's underlying profit before tax for 2025?",
     "USD 11,729 million", 11729, "USD mn", 64,
     "Operating profit / (loss) before tax (underlying) 6,320 2,857 975 2,712 (321) (813) 11,729", "11,729", r"underlying",
     "divisional table, Total column; reported is 8,853"),
    ("ubs-gwm-nna-2025", "ubs", "hard",
     "How much in net new assets did UBS Global Wealth Management attract in 2025?",
     "USD 100.8 billion", 100.8, "USD bn", 71,
     "Net new assets (USD bn)1 100.8 96.7", "100.8", r"[Nn]et new assets",
     "GWM divisional table; trap: net new money is 7.9"),
    ("ubs-dividend-2025", "ubs", "easy",
     "What dividend per share does UBS's board intend to propose for 2025?",
     "USD 1.10", 1.10, "USD/share", 5,
     "propose a dividend of USD 1.10 per share", "1.10", r"[Dd]ividend",
     "letter to shareholders"),
]


# manually checked false positives
EXCLUDE = {("ubs-cet1-ratio-2025", 360)}  # subsidiary table, other entity


def yq(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


errors, out = [], []
for (iid, doc, diff, q, a, val, unit, p, ev, tok, kw, notes) in ITEMS:
    if norm(ev) not in page(doc, p):
        errors.append(f"{iid}: evidence not found on {doc} p{p}")
        continue
    extra = []
    tok_re = re.compile(r"(?<![\d.,])(?<!\d-)" + re.escape(norm(tok)) + r"(?![\d])")
    for pp in range(1, NPAGES[doc] + 1):
        if pp == p:
            continue
        lines = [norm(l) for l in (TXT / f"{doc}-{pp:03d}.txt").read_text(encoding="utf-8").splitlines()]
        for i, l in enumerate(lines):
            if tok_re.search(l) and re.search(kw, " ".join(lines[max(0, i - 1): i + 2])):
                extra.append(pp)
                break
    extra = [x for x in extra if (iid, x) not in EXCLUDE]
    pages = [p] + extra
    out.append(
        f"  - id: {iid}\n"
        f"    doc_id: {doc}-ar-2025\n"
        f"    difficulty: {diff}\n"
        f"    question: {yq(q)}\n"
        f"    answer: {yq(a)}\n"
        f"    value: {val}\n"
        f"    unit: {yq(unit)}\n"
        f"    pages: {pages}\n"
        f"    evidence: {yq(ev)}\n"
        f"    notes: {yq(notes)}\n"
        f"    verified: false\n"
    )

if errors:
    print("\n".join(errors))
    sys.exit(1)

header = """# Tripwire gold set - candidate entries (DRAFT, needs human verification)
#
# Conventions
#   pages     : 1-based PDF viewer page numbers. pages[0] is where `evidence` was found;
#               the others contain the same number next to the same keyword (same or adjacent
#               line). Check them and delete any that is not the same fact.
#               Retrieval counts as a hit if ANY listed page is retrieved.
#   value     : plain number, '.' as decimal separator, negatives with '-'.
#   unit      : CHF mn | CHF bn | USD mn | USD bn | % | count | CHF/share | USD/share
#               Percentages as 19.6, not 0.196. Scorer must convert mn<->bn and allow rounding
#               (e.g. 4762 USD mn == 4.8 USD bn within 1%).
#   evidence  : exact text from pdftotext -layout on pages[0] (whitespace collapsed).
#   verified  : set to true only after checking value AND page in the PDF viewer.
#               The scorer must ignore entries with verified: false.
#
# Source files (sha256 prefix): sika e2ba745f1a3b974d, swissre e3333b190ab7b4ff, ubs a124e365580a1d85
items:
"""
OUT.write_text(header + "\n".join(out), encoding="utf-8")
print(f"wrote {len(out)} items to {OUT}")