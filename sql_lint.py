import re
import streamlit as st
import pandas as pd
import sqlparse
from dataclasses import dataclass
from typing import List, Optional

# ---------------- CONFIG ----------------
st.set_page_config(
    page_title="SQL Lint Pro",
    page_icon="🧹",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🧹 SQL Lint Pro")
st.caption("Enterprise-grade SQL Linter with Safe Auto-Fixes")

# ---------------- DATA MODELS ----------------
@dataclass
class Finding:
    rule_id: str
    message: str
    severity: str
    line: int
    col: int
    suggestion: Optional[str] = None

SQL_KEYWORDS = {"select","from","where","group","order","limit","join","inner","left","right","on","and","or","insert","into","update","set","delete","create","table"}

def _lines(s: str): return s.splitlines() or [""]

# ---------------- RULES ----------------
def rule_semicolon(sql: str, enabled=True) -> List[Finding]:
    if not enabled: return []
    if not sql.strip(): return []
    if not sql.strip().endswith(";"):
        last_line = len(_lines(sql))
        return [Finding("L001", "Statement should end with ';'", "warning", last_line, 1, "Add trailing ';'")]
    return []

def rule_no_select_star(sql: str, enabled=True) -> List[Finding]:
    if not enabled: return []
    out = []
    for i, line in enumerate(_lines(sql), start=1):
        if re.search(r"(?i)\bselect\s+\*", line):
            out.append(Finding("L002", "Avoid SELECT *", "error", i, line.lower().find("select"), "List explicit columns"))
    return out

def rule_uppercase_keywords(sql: str, enabled=True) -> List[Finding]:
    if not enabled: return []
    out = []
    for i, line in enumerate(_lines(sql), start=1):
        for w in re.findall(r"[A-Za-z]+", line):
            if w.lower() in SQL_KEYWORDS and w != w.upper():
                out.append(Finding("L003", f"Keyword '{w}' should be UPPERCASE", "info", i, line.find(w), f"Use '{w.upper()}'"))
    return out

# ---------------- AUTO-FIX ----------------
def auto_fix(sql: str, upper=True, semicolon=True) -> str:
    formatted = sqlparse.format(
        sql,
        keyword_case="upper" if upper else None,
        reindent=True,
        indent_width=2
    )
    if semicolon and not formatted.strip().endswith(";"):
        formatted += ";"
    return formatted

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.header("⚙️ Rules")
    r1 = st.checkbox("L001: Require semicolon", True)
    r2 = st.checkbox("L002: Disallow SELECT *", True)
    r3 = st.checkbox("L003: Uppercase keywords", True)

    st.header("🛠️ Auto-Fix Options")
    fix_upper = st.checkbox("Uppercase keywords", True)
    fix_semicolon = st.checkbox("Ensure semicolon", True)

# ---------------- INPUT ----------------
st.subheader("📥 Input SQL")
sql_text = st.text_area(
    "Paste your SQL below",
    value="-- Example\nselect * from users",
    height=200
)

uploaded = st.file_uploader("Or upload a .sql file", type=["sql"])
if uploaded:
    sql_text = uploaded.read().decode("utf-8")

# ---------------- RUN ----------------
def lint(sql: str) -> List[Finding]:
    findings = []
    findings += rule_semicolon(sql, r1)
    findings += rule_no_select_star(sql, r2)
    findings += rule_uppercase_keywords(sql, r3)
    return findings

col1, col2 = st.columns([1,1])
with col1:
    if st.button("🔎 Run Linter"):
        findings = lint(sql_text)
        if not findings:
            st.success("✅ No issues found!")
        else:
            df = pd.DataFrame([f.__dict__ for f in findings])
            st.dataframe(df, use_container_width=True, hide_index=True)
with col2:
    if st.button("🛠️ Auto-Fix SQL"):
        fixed = auto_fix(sql_text, fix_upper, fix_semicolon)
        st.code(fixed, language="sql")
        st.download_button("⬇️ Download Fixed SQL", fixed, "fixed.sql", "text/sql")

st.markdown("---")
st.caption("Built with ❤️ on Streamlit. Ready for production use.")
