# file: app.py
"""AI Legal Clause Checker (Streamlit MVP)

Neat, modern UI using your palette:
- Primary (brand): #3B0100 (dark red)
- Accent: #D7B15C (gold)
- Text: #333333 (dark gray)
- Background: #FFFFFF

Run locally:
  pip install -r requirements.txt
  streamlit run app.py

Environment:
  - Set OPENAI_API_KEY (or use sidebar -> 'Use mock analysis' for no-key demo).

Notes:
  - Minimal inline comments; documentation prioritized.
  - JSON-first prompting for robust parsing.
  - Graceful fallbacks & clear errors.
"""
from __future__ import annotations

import io
import json
import os
import re
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

import streamlit as st

# Optional imports guarded at runtime
try:
    import docx  # python-docx
except Exception:  # pragma: no cover
    docx = None

try:
    import PyPDF2
except Exception:  # pragma: no cover
    PyPDF2 = None

# --------------
# Theme & Styles
# --------------
PALETTE = {
    "brand": "#3B0100",
    "accent": "#D7B15C",
    "text": "#333333",
    "bg": "#FFFFFF",
    "muted": "#8F8F8F",
    "safe": "#16a34a",      # green-600
    "review": "#D7B15C",    # gold (accent)
    "risky": "#3B0100",     # brand (danger)
}

st.set_page_config(
    page_title="AI Legal Clause Checker",
    page_icon="⚖️",
    layout="wide",
)

CUSTOM_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

:root {{
  --brand: {PALETTE['brand']};
  --accent: {PALETTE['accent']};
  --text: {PALETTE['text']};
  --bg: {PALETTE['bg']};
  --muted: {PALETTE['muted']};
  --safe: {PALETTE['safe']};
  --review: {PALETTE['review']};
  --risky: {PALETTE['risky']};
}}

html, body, [class*="css"] {{
  font-family: 'Inter', system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  color: var(--text);
  background: var(--bg);
}}

/* Header */
header .stAppHeader {{
  background: var(--bg) !important;
  border-bottom: 1px solid #eee;
}}

/* Titles */
h1, h2, h3, h4 {{ color: var(--brand); letter-spacing: -0.2px; }}

/* Buttons */
.stButton > button {{
  background: var(--accent) !important;
  color: var(--brand) !important; /* contrasty brand text */
  border: 0 !important;
  border-radius: 14px !important;
  padding: 0.6rem 1rem !important;
  font-weight: 700 !important;
  box-shadow: 0 2px 10px rgba(0,0,0,0.08);
}}
.stButton > button:hover {{ filter: brightness(0.95); }}

/* Text inputs & textareas */
textarea, .stTextArea textarea, .stTextInput input {{
  border-radius: 14px !important;
  border: 1px solid #e5e7eb !important;
}}

/* Cards */
.block-container {{ padding-top: 1.2rem; }}
.card {{
  border: 1px solid #eee; border-radius: 18px; padding: 1rem 1.25rem; background: white;
  box-shadow: 0 4px 16px rgba(0,0,0,0.04);
}}
.badge {{
  display: inline-flex; align-items: center; gap: .4rem; font-weight: 700; font-size: .8rem;
  padding: .35rem .6rem; border-radius: 999px; color: white;
}}
.badge.safe   {{ background: var(--safe); }}
.badge.review {{ background: var(--review); color: #3b2e00; }}
.badge.risky  {{ background: var(--risky); }}

/* Progress bar */
.progress {{ height: 8px; background: #f4f4f5; border-radius: 999px; overflow: hidden; }}
.progress > span {{ display: block; height: 100%; background: var(--accent); }}

/* Small muted text */
.muted {{ color: var(--muted); font-size: .9rem; }}

/* Download buttons alignment */
.toolbar { display: flex; gap: .5rem; flex-wrap: wrap; }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# -----------------
# Data definitions
# -----------------
@dataclass
class ClauseAnalysis:
    clause: str
    meaning: str
    risk_label: str  # Safe | Review | Risky
    risk_score: int  # 1-3
    why: str
    suggestion: Optional[str] = None
    tags: Optional[List[str]] = None

    def badge_class(self) -> str:
        return {
            "safe": "safe",
            "review": "review",
            "risky": "risky",
        }.get(self.risk_label.lower(), "review")

    def to_markdown(self, idx: int) -> str:
        return (
            f"### Clause {idx}\n"
            f"**Risk**: {self.risk_label} (score {self.risk_score}/3)\n\n"
            f"**Plain English**: {self.meaning}\n\n"
            f"**Why flagged**: {self.why}\n\n"
            f"**Safer alternative**: {self.suggestion or '—'}\n\n"
            f"**Original text**: \n> {self.clause.strip()}\n"
        )

# -----------------
# Utilities
# -----------------
RISK_MAP = {"safe": 1, "review": 2, "risky": 3}

FOCUS_PRESETS = {
    "General": "payments, termination, liability, IP ownership, confidentiality, dispute resolution, auto-renewal, jurisdiction",
    "Freelancer": "scope creep, payment terms, late fees, IP ownership, portfolio rights, termination, indemnity",
    "NDA": "definition of confidential info, term length, non-disclosure scope, residuals, return or destroy obligations, exclusions",
    "Lease": "rent increases, maintenance, deposit, early termination, sublet, late fees, liability for damage, entry rights",
    "Employment": "non-compete, non-solicit, probation, termination, severance, IP assignment, arbitration, confidentiality",
}

@mystery := None  # placeholder to satisfy type checkers in some editors

@st.cache_data(show_spinner=False)
def extract_text_from_upload(uploaded) -> str:
    if uploaded is None:
        return ""
    content_type = uploaded.type or ""
    data = uploaded.read()

    if content_type.endswith("plain"):
        return data.decode("utf-8", errors="ignore")

    if content_type.endswith("pdf"):
        if PyPDF2 is None:
            st.error("PyPDF2 not installed. Add it to requirements.txt for PDF support.")
            return ""
        reader = PyPDF2.PdfReader(io.BytesIO(data))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)

    if content_type.endswith("wordprocessingml.document"):
        if docx is None:
            st.error("python-docx not installed. Add it to requirements.txt for DOCX support.")
            return ""
        document = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in document.paragraphs)

    # Fallback: try utf-8
    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""

@st.cache_data(show_spinner=False)
def normalize_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

@st.cache_data(show_spinner=False)
def split_into_clauses(text: str, min_chars: int = 250, max_chars: int = 1100) -> List[str]:
    """Chunk by section headings and sentences; enforce size window.
    Why: contracts mix bullets, headings, long sentences—this balances coherence & token usage.
    """
    text = normalize_text(text)

    # Split on typical section markers
    parts = re.split(
        r"(?im)\n(?=(?:section\s+\d+|\d+(?:\.\d+)*|[ivxlcdm]+\.)\s+)|\n\s*\n",
        text,
    )
    chunks: List[str] = []

    def flush(buf: List[str]):
        if not buf:
            return
        chunk = " ".join(buf).strip()
        if len(chunk) >= min_chars:
            chunks.append(chunk)

    buf: List[str] = []
    for part in parts:
        sentences = re.split(r"(?<=[.;:])\s+", part.strip())
        for sent in sentences:
            buf.append(sent)
            cur = " "+" ".join(buf)
            if len(cur) > max_chars:
                flush(buf)
                buf = []
        if buf:
            flush(buf)
            buf = []

    # fallback if tiny
    if not chunks and text:
        chunks = [text]
    return chunks

# -----------------
# Model calls
# -----------------

def _openai_client():
    try:  # SDK v1 style
        from openai import OpenAI  # type: ignore
        return OpenAI()
    except Exception:
        return None


def analyze_with_llm(
    clause: str,
    focus: str,
    jurisdiction: str,
    model: str = "gpt-4o-mini",
    temperature: float = 0.2,
) -> ClauseAnalysis:
    client = _openai_client()
    if client is None:
        raise RuntimeError("OpenAI SDK not available. Install `openai>=1.0.0`.")

    system = (
        "You are a contract analyst. Identify risks for the user. "
        "Be concise and practical. Output strict JSON only."
    )
    instructions = {
        "jurisdiction": jurisdiction or "unspecified",
        "focus": focus,
        "schema": {
            "clause": "str (original)",
            "meaning": "plain English",
            "risk_label": "Safe|Review|Risky",
            "risk_score": "1=Safe,2=Review,3=Risky",
            "why": "reasoning in plain English",
            "suggestion": "safer rewrite (optional)",
            "tags": "list[str] keywords",
        },
    }
    user = (
        "Analyze the clause JSON-only.\n" \
        f"FOCUS: {focus}. JURISDICTION: {jurisdiction or 'unspecified'}.\n" \
        "Return keys: clause, meaning, risk_label, risk_score(1-3), why, suggestion, tags.\n" \
        f"Clause: {json.dumps(clause)}"
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
        response_format={"type": "json_object"},  # encourage well-formed JSON
    )
    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw)

    # Validation & coercion
    label = str(data.get("risk_label", "Review")).strip()
    if label.lower() not in RISK_MAP:
        label = "Review"
    score = int(data.get("risk_score", RISK_MAP[label.lower()]))
    score = max(1, min(3, score))

    return ClauseAnalysis(
        clause=clause.strip(),
        meaning=str(data.get("meaning", "")).strip(),
        risk_label=label,
        risk_score=score,
        why=str(data.get("why", "")).strip(),
        suggestion=(str(data.get("suggestion", "")).strip() or None),
        tags=data.get("tags", None),
    )

# ---------------
# Mock heuristic
# ---------------

RISK_KEYWORDS = {
    "risky": [
        "indemnify", "hold harmless", "limitation of liability", "exclusive jurisdiction",
        "binding arbitration", "waiver of jury", "auto-renew", "perpetual", "irrevocable",
        "royalty-free", "assign without consent", "liquidated damages", "non-compete",
    ],
    "review": [
        "termination", "30 days", "confidential", "governing law", "late fee", "interest",
        "force majeure", "intellectual property", "work for hire",
    ],
}


def mock_analyze(clause: str, focus: str, jurisdiction: str) -> ClauseAnalysis:
    text = clause.lower()
    score = 1
    label = "Safe"
    reasons: List[str] = []
    for kw in RISK_KEYWORDS["risky"]:
        if kw in text:
            score = 3; label = "Risky"; reasons.append(f"Contains '{kw}'.")
    if score < 3:
        for kw in RISK_KEYWORDS["review"]:
            if kw in text:
                score = max(score, 2); label = "Review"; reasons.append(f"Mentions '{kw}'.")

    why = " ".join(reasons) or "No obvious red flags found by keyword heuristic."
    suggestion = None
    if label == "Risky":
        suggestion = (
            "Limit liability to direct damages and mutual caps; avoid perpetual/irrevocable rights; "
            "require written consent for assignment; permit court remedies where appropriate."
        )
    elif label == "Review":
        suggestion = (
            "Clarify timelines, notice periods, and mutual obligations; ensure balanced termination and payment terms."
        )

    meaning = (
        "This clause sets certain obligations/rights. Please verify it aligns with your interests, "
        "especially regarding the selected focus."
    )

    return ClauseAnalysis(
        clause=clause.strip(),
        meaning=meaning,
        risk_label=label,
        risk_score=score,
        why=why,
        suggestion=suggestion,
        tags=[focus.lower()],
    )

# --------------
# UI Components
# --------------

def risk_badge_html(label: str) -> str:
    cls = {
        "safe": "safe",
        "review": "review",
        "risky": "risky",
    }.get(label.lower(), "review")
    emoji = {"safe": "✅", "review": "⚠️", "risky": "⛔"}[cls]
    return f'<span class="badge {cls}">{emoji} {label}</span>'


def render_clause_card(idx: int, ca: ClauseAnalysis):
    st.markdown(
        f"<div class='card' style='border-left: 6px solid {PALETTE[ca.badge_class()]};'>" \
        f"<div style='display:flex;justify-content:space-between;align-items:center'>" \
        f"<h3 style='margin:0;color:var(--text)'>Clause {idx}</h3>" \
        f"{risk_badge_html(ca.risk_label)}" \
        f"</div>",
        unsafe_allow_html=True,
    )
    with st.container():
        cols = st.columns([3, 2])
        with cols[0]:
            st.markdown(f"**Plain English**\n\n{ca.meaning}")
            st.markdown(f"**Why flagged**\n\n{ca.why}")
            if ca.suggestion:
                st.markdown(f"**Safer alternative**\n\n{ca.suggestion}")
        with cols[1]:
            with st.expander("Show original text"):
                st.write(ca.clause)
    st.markdown("</div>", unsafe_allow_html=True)


# --------------
# Sidebar Config
# --------------
with st.sidebar:
    st.markdown("## ⚖️ AI Legal Clause Checker")
    st.markdown("<div class='muted'>Neat & modern UI with your palette.</div>", unsafe_allow_html=True)

    use_mock = st.toggle("Use mock analysis (no API key)", value=not bool(os.getenv("OPENAI_API_KEY")))

    if not use_mock:
        st.text_input("OpenAI API Key", type="password", key="OPENAI_API_KEY", help="Stored only in session.")
        if st.session_state.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = st.session_state["OPENAI_API_KEY"]

    model = st.selectbox("Model", ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"], index=0, help="Use *mini* for cost.")
    focus = st.selectbox("Focus preset", list(FOCUS_PRESETS.keys()), index=0)
    jurisdiction = st.text_input("Jurisdiction (optional)", placeholder="e.g., California, EU, India")
    max_clauses = st.slider("Max clauses to analyze", 3, 40, 12)
    st.markdown("---")
    st.markdown("### Legend")
    st.markdown(
        f"{risk_badge_html('Safe')} Low concern &nbsp;&nbsp; {risk_badge_html('Review')} Needs attention &nbsp;&nbsp; {risk_badge_html('Risky')} High risk",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown(
        "<div class='muted'>This tool highlights potential issues and is not legal advice.</div>",
        unsafe_allow_html=True,
    )

# --------------
# Main Content
# --------------
st.title("AI Legal Clause Checker")
st.markdown("A clean, modern analyzer for contracts. Upload a file or paste text below.")

left, right = st.columns([1, 1])

with left:
    uploaded = st.file_uploader("Upload contract (PDF/DOCX/TXT)", type=["pdf", "docx", "txt"])  # noqa: RUF100
    pasted = st.text_area("Or paste contract text", height=260, placeholder="Paste your contract here…")

with right:
    st.markdown("#### Options")
    st.write(f"Focus: **{focus}** → {FOCUS_PRESETS[focus]}")
    st.write(f"Jurisdiction: **{jurisdiction or 'unspecified'}**")
    analyze_btn = st.button("Analyze Contract", type="primary")

text_from_file = extract_text_from_upload(uploaded)
contract_text = (pasted or "").strip() or text_from_file

if analyze_btn:
    if not contract_text:
        st.warning("Please upload or paste a contract.")
        st.stop()

    chunks = split_into_clauses(contract_text)
    if not chunks:
        st.warning("Could not split the document into analyzable clauses.")
        st.stop()

    chunks = chunks[:max_clauses]
    st.markdown("### Results")

    progress = st.empty()
    results: List[ClauseAnalysis] = []

    for i, ch in enumerate(chunks, start=1):
        progress.progress(i / len(chunks), text=f"Analyzing clause {i}/{len(chunks)}…")
        try:
            if use_mock:
                ca = mock_analyze(ch, focus, jurisdiction)
            else:
                ca = analyze_with_llm(ch, FOCUS_PRESETS[focus], jurisdiction, model=model)
        except Exception as e:  # minimal surface, show error non-fatally
            ca = ClauseAnalysis(
                clause=ch.strip(),
                meaning="(Failed to analyze clause.)",
                risk_label="Review",
                risk_score=2,
                why=f"Error: {e}",
            )
        results.append(ca)
        render_clause_card(i, ca)

    progress.empty()

    # Report downloads
    md_report = ["# AI Legal Clause Checker Report\n"]
    for i, ca in enumerate(results, start=1):
        md_report.append(ca.to_markdown(i))
    md_text = "\n\n".join(md_report)

    json_text = json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False)

    st.markdown("### Export")
    c1, c2 = st.columns([1, 1])
    with c1:
        st.download_button(
            "Download Markdown Report",
            data=md_text.encode("utf-8"),
            file_name="clause_checker_report.md",
            mime="text/markdown",
        )
    with c2:
        st.download_button(
            "Download JSON",
            data=json_text.encode("utf-8"),
            file_name="clause_checker_report.json",
            mime="application/json",
        )

else:
    # Helpful example for first-time users
    example = (
        "This Agreement shall automatically renew for successive one-year terms unless either party provides 30 days' "
        "written notice prior to the end of the then-current term. The Service Provider shall not be liable for any "
        "indirect, incidental, special, or consequential damages and the total liability shall not exceed the fees paid "
        "in the three months preceding the claim. Client agrees to indemnify and hold harmless the Service Provider from "
        "any third-party claims arising out of Client's use of the Services."
    )
    with st.expander("Sample contract text (for demo)"):
        st.code(example)

# --------------
# Footer disclaimer
# --------------
st.markdown(
    "<hr><div class='muted'>This tool highlights potential issues and is not a substitute for professional legal advice.</div>",
    unsafe_allow_html=True,
)
