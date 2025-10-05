import re
from difflib import get_close_matches
from dataclasses import dataclass
from typing import List, Optional

import streamlit as st
import pandas as pd
import sqlparse
import sqlglot
from sqlglot.errors import ParseError

# ---------------- CONFIG ----------------
st.set_page_config(
    page_title="SQL Lint Pro",
    page_icon="🧹",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.title("🧹 SQL Lint Pro")
st.caption("Enterprise-grade SQL Linter with Syntax Validation, Auto-Fixes, and Custom Rules")

# ---------------- MODELS ----------------
@dataclass
class Finding:
    rule_id: str
    message: str
    severity: str   # error | warning | info
    line: int
    col: int
    suggestion: Optional[str] = None

def _lines(s: str): return s.splitlines() or [""]

SQL_KEYWORDS = {
    "select","from","where","group","order","limit","join","inner","left","right","full","outer",
    "on","and","or","insert","into","update","set","delete","create","table","having","distinct",
    "union","all","case","when","then","else","end","exists","in","is","null","like","with","over","partition"
}

SUPPORTED_DIALECTS = ["sqlite", "mysql", "postgres", "tsql", "snowflake", "bigquery"]

# ---------------- VALIDATION ----------------
def validate_sql(sql: str, dialect: str) -> Optional[str]:
    try:
        sqlglot.parse_one(sql, read=dialect)
        return None
    except ParseError as e:
        return str(e)
    except ValueError as ve:
        return f"Unsupported dialect '{dialect}': {ve}"

# ---------------- BUILT-IN RULES ----------------
def rule_semicolon(sql: str, enabled=True) -> List[Finding]:
    if not enabled or not sql.strip():
        return []
    if not sql.strip().endswith(";"):
        last_line = len(_lines(sql))
        return [Finding("L001", "Statement should end with ';'", "warning", last_line, 1, "Add trailing ';'")]
    return []

def rule_no_select_star(sql: str, enabled=True) -> List[Finding]:
    if not enabled: return []
    out = []
    for i, line in enumerate(_lines(sql), start=1):
        if re.search(r"(?i)\bselect\s+\*", line):
            out.append(Finding("L002", "Avoid SELECT * (enumerate columns)", "error", i, max(1, line.lower().find("select")+1), "List explicit columns"))
    return out

def rule_uppercase_keywords(sql: str, enabled=True) -> List[Finding]:
    if not enabled: return []
    out = []
    for i, line in enumerate(_lines(sql), start=1):
        for w in re.findall(r"[A-Za-z]+", line):
            if w.lower() in SQL_KEYWORDS and w != w.upper():
                out.append(Finding("L003", f"Keyword '{w}' should be UPPERCASE", "info", i, max(1, line.find(w)+1), f"Use '{w.upper()}'"))
    return out

def rule_typo_keywords(sql: str, enabled=True) -> List[Finding]:
    if not enabled: return []
    findings = []
    for i, line in enumerate(_lines(sql), start=1):
        for w in re.findall(r"[A-Za-z]+", line):
            low = w.lower()
            if low not in SQL_KEYWORDS and len(low) >= 3:
                close = get_close_matches(low, SQL_KEYWORDS, n=1, cutoff=0.86)
                if close:
                    findings.append(Finding(
                        "L004",
                        f"Possible keyword typo '{w}' (did you mean '{close[0].upper()}')?",
                        "error", i, max(1, line.find(w)+1),
                        f"Replace with {close[0].upper()}"
                    ))
    return findings

# ---------------- CUSTOM RULES ----------------
def run_custom_rules(sql: str) -> List[Finding]:
    findings = []
    if "custom_rules" not in st.session_state:
        return findings
    
    for ridx, rule in enumerate(st.session_state["custom_rules"]):
        pattern, message, severity = rule["pattern"], rule["message"], rule["severity"]
        for i, line in enumerate(_lines(sql), start=1):
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                findings.append(Finding(
                    f"CUST{ridx+1}",
                    message,
                    severity,
                    i,
                    max(1, m.start()+1),
                    None
                ))
    return findings

# ---------------- LINT ORCHESTRATOR ----------------
def run_lint(sql: str, rules: dict) -> List[Finding]:
    findings: List[Finding] = []
    findings += rule_semicolon(sql, rules["semicolon"])
    findings += rule_no_select_star(sql, rules["select_star"])
    findings += rule_uppercase_keywords(sql, rules["upper_keywords"])
    findings += rule_typo_keywords(sql, rules["typo_keywords"])
    findings += run_custom_rules(sql)   # ✅ dynamic UI rules
    # Sort by severity then line
    severity_rank = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (severity_rank.get(f.severity, 9), f.line, f.rule_id))
    return findings

# ---------------- AUTO-FIX ----------------
def auto_fix(sql: str, *, upper=True, semicolon=True) -> str:
    formatted = sqlparse.format(
        sql,
        keyword_case="upper" if upper else None,
        reindent=True,
        indent_width=2,
    )
    if semicolon and not formatted.strip().endswith(";"):
        formatted = formatted.rstrip() + ";\n"
    return formatted

# ---------------- SIDEBAR: RULE MANAGER ----------------
with st.sidebar:
    st.header("⚙️ Built-in Rules")
    rules = {
        "semicolon": st.checkbox("L001: Require semicolon", True),
        "select_star": st.checkbox("L002: Disallow SELECT *", True),
        "upper_keywords": st.checkbox("L003: Uppercase keywords", True),
        "typo_keywords": st.checkbox("L004: Detect keyword typos", True),
    }

    st.header("➕ Add Custom Rule")
    new_pattern = st.text_input("Regex Pattern", placeholder=r"\bdelete\b")
    new_message = st.text_input("Message", "Avoid DELETE without WHERE")
    new_severity = st.selectbox("Severity", ["error", "warning", "info"])
    if st.button("Add Rule"):
        if "custom_rules" not in st.session_state:
            st.session_state["custom_rules"] = []
        st.session_state["custom_rules"].append({
            "pattern": new_pattern,
            "message": new_message,
            "severity": new_severity
        })
        st.success("Rule added!")

    if "custom_rules" in st.session_state and st.session_state["custom_rules"]:
        st.subheader("📋 Current Custom Rules")
        for idx, rule in enumerate(st.session_state["custom_rules"]):
            st.markdown(f"- `{rule['pattern']}` → {rule['message']} ({rule['severity']})")
            if st.button(f"❌ Delete {idx+1}", key=f"del_{idx}"):
                st.session_state["custom_rules"].pop(idx)
                st.experimental_rerun()

    st.header("🛠️ Auto-Fix")
    fix_upper = st.checkbox("Uppercase keywords", True)
    fix_semicolon = st.checkbox("Ensure semicolon", True)

    st.header("🗄️ Dialect")
    dialect = st.selectbox("Validate against dialect", SUPPORTED_DIALECTS, index=0)

# ---------------- INPUT ----------------
st.subheader("📥 Input SQL")
sql_text = st.text_area(
    "Paste SQL here",
    value="-- Example\nselect * from users",
    height=200,
)

uploaded = st.file_uploader("Or upload a .sql file", type=["sql"])
if uploaded:
    sql_text = uploaded.read().decode("utf-8")

# ---------------- ACTIONS ----------------
col1, col2 = st.columns(2)
with col1:
    run_btn = st.button("🔎 Validate & Lint")
with col2:
    fix_btn = st.button("🛠️ Auto-Fix SQL")

# ---------------- EXECUTION ----------------
if run_btn:
    # 1) Syntax validation
    err = validate_sql(sql_text, dialect)
    if err:
        st.error(f"❌ Invalid SQL ({dialect}): {err}")
    else:
        st.success(f"✅ SQL syntax is valid ({dialect})")

    # 2) Lint rules
    findings = run_lint(sql_text, rules)
    if not findings:
        st.success("✨ No lint findings.")
    else:
        df = pd.DataFrame([f.__dict__ for f in findings])
        st.dataframe(df, width="stretch", hide_index=True)

if fix_btn:
    fixed = auto_fix(sql_text, upper=fix_upper, semicolon=fix_semicolon)
    st.subheader("Auto-Fixed SQL")
    st.code(fixed, language="sql")
    st.download_button("⬇️ Download Fixed SQL", fixed, "fixed.sql", "text/sql")
