import streamlit as st
from openai import OpenAI
import os

# ------------------ CONFIG ------------------
st.set_page_config(page_title="AI Legal Clause Checker", layout="wide")

# Load API key from Streamlit secrets
api_key = st.secrets.get("OPENAI_API_KEY", None)
client = OpenAI(api_key=api_key)

# ------------------ CUSTOM CSS ------------------
def local_css():
    st.markdown(
        """
        <style>
        .stApp {
            background-color: #FFFFFF;
            color: #333333;
            font-family: 'Segoe UI', sans-serif;
        }

        h1, h2, h3, h4 {
            color: #A30000;
            font-weight: 600;
        }

        .stTextArea textarea {
            border: 1px solid #D7B15C;
            border-radius: 10px;
            padding: 12px;
            font-size: 15px;
        }

        .stButton>button {
            background-color: #A30000;
            color: #FFFFFF;
            border-radius: 12px;
            padding: 0.6rem 1.2rem;
            font-size: 16px;
            font-weight: 500;
            border: none;
            transition: 0.3s;
        }

        .stButton>button:hover {
            background-color: #D7B15C;
            color: #000000;
        }

        .report-box {
            border: 2px solid #D7B15C;
            background-color: #FAF8F2;
            padding: 16px;
            border-radius: 12px;
            margin-top: 20px;
        }

        /* Top Navigation */
        .top-nav {
            background-color: #D7B15C;
            padding: 12px;
            border-radius: 0 0 12px 12px;
            text-align: center;
        }
        .top-nav a {
            margin: 0 15px;
            text-decoration: none;
            color: #000000;
            font-weight: 500;
            font-size: 16px;
        }
        .top-nav a:hover {
            color: #A30000;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

local_css()

# ------------------ NAVIGATION BAR ------------------
st.markdown(
    """
    <div class='top-nav'>
        <a href='#'>Home</a>
        <a href='#about'>About</a>
        <a href='#contact'>Contact</a>
    </div>
    """,
    unsafe_allow_html=True,
)

# ------------------ HEADER ------------------
st.title("⚖️ AI Legal Clause Checker")
st.write("Paste your contract below and the AI will flag risky clauses in **plain language**.")

# ------------------ INPUT ------------------
contract_text = st.text_area("Paste contract here:", height=300)

# ------------------ AI ANALYSIS ------------------
def analyze_contract(text: str) -> str:
    if not api_key:
        return "⚠️ No API key found. Please set OPENAI_API_KEY in Streamlit Secrets."
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a legal assistant. Highlight risky or unusual clauses in contracts in plain English."},
                {"role": "user", "content": text}
            ],
            max_tokens=500,
            temperature=0.3,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ Error: {str(e)}"

# ------------------ BUTTON ------------------
if st.button("🔍 Analyze Contract"):
    if contract_text.strip():
        with st.spinner("Analyzing contract, please wait..."):
            report = analyze_contract(contract_text)
            st.markdown(f"<div class='report-box'><b>Analysis Report:</b><br>{report}</div>", unsafe_allow_html=True)
    else:
        st.warning("Please paste a contract first!")
