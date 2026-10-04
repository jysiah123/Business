"""
LAUNCHPAD — AI CAREER OS
Portfolio-grade Streamlit application

Features
--------
- Resume PDF parsing
- Resume/job description analysis
- Weighted skill matching
- TF-IDF semantic similarity
- Missing skill detection
- Resume evidence extraction
- Tailored cover-letter generation
- Persistent SQLite application tracker
- Application status management
- Dashboard analytics
- CSV export

Install
-------
pip install streamlit pypdf scikit-learn plotly sqlalchemy pandas

Run
---
streamlit run launchpad.py
"""

from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from typing import Dict, List, Set

import pandas as pd
import plotly.express as px
import streamlit as st

from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="LaunchPad — AI Career OS",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# DATABASE
# ============================================================

Base = declarative_base()

engine = create_engine(
    "sqlite:///launchpad.db",
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine)


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True)

    company = Column(String(200), nullable=False)
    role = Column(String(200), nullable=False)

    match_score = Column(Float, default=0)
    semantic_score = Column(Float, default=0)

    matched_skills = Column(Text, default="")
    missing_skills = Column(Text, default="")

    status = Column(String(50), default="Applied")

    notes = Column(Text, default="")

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
    )


Base.metadata.create_all(bind=engine)


# ============================================================
# CONSTANTS
# ============================================================

STATUSES = [
    "Saved",
    "Applied",
    "Interview",
    "Technical Interview",
    "Offer",
    "Rejected",
    "Withdrawn",
]

# More realistic skill bank than the original version.
# Each skill has a category and a relative importance weight.
SKILLS = {
    # Programming
    "python": ("Programming", 1.5),
    "javascript": ("Programming", 1.2),
    "typescript": ("Programming", 1.2),
    "java": ("Programming", 1.1),
    "c++": ("Programming", 1.1),
    "c": ("Programming", 1.0),
    "go": ("Programming", 1.2),
    "rust": ("Programming", 1.2),

    # Web
    "react": ("Web", 1.2),
    "next.js": ("Web", 1.2),
    "node.js": ("Web", 1.1),
    "html": ("Web", 0.8),
    "css": ("Web", 0.8),
    "tailwind": ("Web", 0.9),

    # Backend
    "fastapi": ("Backend", 1.3),
    "flask": ("Backend", 1.1),
    "django": ("Backend", 1.1),
    "rest api": ("Backend", 1.2),
    "graphql": ("Backend", 1.1),
    "microservices": ("Backend", 1.3),

    # Data / AI
    "machine learning": ("AI/ML", 1.5),
    "deep learning": ("AI/ML", 1.5),
    "artificial intelligence": ("AI/ML", 1.4),
    "natural language processing": ("AI/ML", 1.4),
    "computer vision": ("AI/ML", 1.3),
    "pandas": ("AI/ML", 1.0),
    "numpy": ("AI/ML", 1.0),
    "scikit-learn": ("AI/ML", 1.2),
    "pytorch": ("AI/ML", 1.5),
    "tensorflow": ("AI/ML", 1.4),
    "transformers": ("AI/ML", 1.4),
    "llm": ("AI/ML", 1.5),
    "generative ai": ("AI/ML", 1.5),
    "rag": ("AI/ML", 1.4),

    # Databases
    "sql": ("Database", 1.2),
    "postgresql": ("Database", 1.2),
    "mysql": ("Database", 1.1),
    "sqlite": ("Database", 0.9),
    "mongodb": ("Database", 1.0),
    "redis": ("Database", 1.0),

    # Cloud / infrastructure
    "aws": ("Cloud", 1.4),
    "azure": ("Cloud", 1.3),
    "gcp": ("Cloud", 1.3),
    "docker": ("Infrastructure", 1.4),
    "kubernetes": ("Infrastructure", 1.5),
    "terraform": ("Infrastructure", 1.3),
    "linux": ("Infrastructure", 1.3),
    "ci/cd": ("Infrastructure", 1.2),

    # Development
    "git": ("Development", 1.0),
    "github": ("Development", 1.0),
    "testing": ("Development", 1.0),
    "pytest": ("Development", 1.1),
    "agile": ("Development", 0.7),

    # Professional
    "communication": ("Professional", 0.6),
    "leadership": ("Professional", 0.7),
    "problem solving": ("Professional", 0.8),
    "project management": ("Professional", 0.8),
}


# ============================================================
# TEXT PROCESSING
# ============================================================

def normalize_text(text: str) -> str:
    """
    Normalize text for matching.
    """
    text = text.lower()

    replacements = {
        "node js": "node.js",
        "nodejs": "node.js",
        "next js": "next.js",
        "nextjs": "next.js",
        "scikit learn": "scikit-learn",
        "machine-learning": "machine learning",
        "deep-learning": "deep learning",
        "restful api": "rest api",
        "restful apis": "rest api",
        "generative-ai": "generative ai",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return re.sub(r"\s+", " ", text).strip()


def extract_text_from_pdf(file) -> str:
    """
    Extract text from every page of a PDF.
    """
    reader = PdfReader(file)

    pages = []

    for page in reader.pages:
        page_text = page.extract_text() or ""

        if page_text.strip():
            pages.append(page_text)

    return "\n".join(pages)


def contains_skill(text: str, skill: str) -> bool:
    """
    Detect a skill without accidental substring matches.

    Example:
    'c' should not match every occurrence of the letter c.
    """
    text = normalize_text(text)
    skill = normalize_text(skill)

    escaped = re.escape(skill)

    # Word boundaries work for most skills.
    pattern = rf"(?<![a-z0-9+#]){escaped}(?![a-z0-9+#])"

    return re.search(pattern, text) is not None


def extract_skills(text: str) -> Set[str]:
    """
    Return skills found in the provided text.
    """
    found = set()

    for skill in SKILLS:
        if contains_skill(text, skill):
            found.add(skill)

    return found


def extract_skill_evidence(text: str, skill: str) -> str:
    """
    Find a sentence containing the skill.
    This gives the user evidence for why the skill was detected.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text)

    for sentence in sentences:
        if contains_skill(sentence, skill):
            cleaned = sentence.strip()

            if len(cleaned) > 220:
                cleaned = cleaned[:217] + "..."

            return cleaned

    return ""


# ============================================================
# MATCHING ENGINE
# ============================================================

def semantic_similarity(
    resume_text: str,
    job_description: str,
) -> float:
    """
    TF-IDF cosine similarity between resume and job description.
    """
    if not resume_text.strip() or not job_description.strip():
        return 0.0

    try:
        vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            max_features=5000,
        )

        vectors = vectorizer.fit_transform(
            [resume_text, job_description]
        )

        similarity = cosine_similarity(
            vectors[0],
            vectors[1],
        )[0][0]

        return round(float(similarity) * 100, 1)

    except ValueError:
        return 0.0


def weighted_skill_score(
    resume_skills: Set[str],
    job_skills: Set[str],
) -> float:
    """
    Calculate weighted skill overlap.

    Required skills with larger weights contribute more.
    """
    if not job_skills:
        return 0.0

    total_weight = sum(
        SKILLS[skill][1]
        for skill in job_skills
    )

    matched_weight = sum(
        SKILLS[skill][1]
        for skill in resume_skills & job_skills
    )

    if total_weight == 0:
        return 0.0

    return round(
        (matched_weight / total_weight) * 100,
        1,
    )


def analyze_match(
    resume_text: str,
    job_description: str,
) -> Dict:
    """
    Complete resume/job analysis.
    """

    resume_text = normalize_text(resume_text)
    job_description = normalize_text(job_description)

    resume_skills = extract_skills(resume_text)
    job_skills = extract_skills(job_description)

    matched = sorted(resume_skills & job_skills)
    missing = sorted(job_skills - resume_skills)

    semantic_score = semantic_similarity(
        resume_text,
        job_description,
    )

    skill_score = weighted_skill_score(
        resume_skills,
        job_skills,
    )

    # Skills matter more than raw textual similarity.
    final_score = round(
        (skill_score * 0.65)
        + (semantic_score * 0.35),
        1,
    )

    evidence = {}

    for skill in matched:
        evidence[skill] = extract_skill_evidence(
            resume_text,
            skill,
        )

    return {
        "score": final_score,
        "semantic_score": semantic_score,
        "skill_score": skill_score,
        "resume_skills": sorted(resume_skills),
        "job_skills": sorted(job_skills),
        "matched_skills": matched,
        "missing_skills": missing,
        "evidence": evidence,
    }


# ============================================================
# COVER LETTER
# ============================================================

def generate_cover_letter(
    company: str,
    role: str,
    analysis: Dict,
) -> str:
    """
    Generate a conservative cover letter.

    Important:
    It only references skills detected in the resume.
    """

    matched = analysis["matched_skills"]

    if matched:
        skill_text = ", ".join(matched[:4])
    else:
        skill_text = "software development and problem solving"

    return f"""Dear Hiring Manager,

I am writing to apply for the {role} position at {company}.

My background includes hands-on experience with {skill_text}. I have focused on learning by building projects, solving practical problems, and turning ideas into working software.

One of my current projects is LaunchPad, a career-analysis application that analyzes resumes and job descriptions, identifies relevant skills, calculates a compatibility score, and tracks applications using Python, Streamlit, SQLAlchemy, and data-analysis tools.

I am particularly interested in opportunities where I can continue developing my software engineering and AI skills while contributing to real products.

Thank you for considering my application. I would welcome the opportunity to discuss how my projects and technical background could contribute to your team.

Best regards,

Jysiah Gutierrez
GitHub: github.com/jysiahgutierrez
Portfolio: business-ai-jysiah.streamlit.app
"""


# ============================================================
# DATABASE FUNCTIONS
# ============================================================

def save_application(
    company: str,
    role: str,
    analysis: Dict,
) -> None:

    db = SessionLocal()

    try:
        application = Application(
            company=company,
            role=role,
            match_score=analysis["score"],
            semantic_score=analysis["semantic_score"],
            matched_skills=", ".join(
                analysis["matched_skills"]
            ),
            missing_skills=", ".join(
                analysis["missing_skills"]
            ),
            status="Saved",
        )

        db.add(application)
        db.commit()

    finally:
        db.close()


def get_applications() -> List[Application]:

    db = SessionLocal()

    try:
        return (
            db.query(Application)
            .order_by(Application.created_at.desc())
            .all()
        )

    finally:
        db.close()


def update_application_status(
    application_id: int,
    status: str,
) -> None:

    db = SessionLocal()

    try:
        application = (
            db.query(Application)
            .filter(Application.id == application_id)
            .first()
        )

        if application:
            application.status = status
            db.commit()

    finally:
        db.close()


def delete_application(application_id: int) -> None:

    db = SessionLocal()

    try:
        application = (
            db.query(Application)
            .filter(Application.id == application_id)
            .first()
        )

        if application:
            db.delete(application)
            db.commit()

    finally:
        db.close()


# ============================================================
# UI HELPERS
# ============================================================

def score_label(score: float) -> str:

    if score >= 80:
        return "Strong alignment"

    if score >= 65:
        return "Good alignment"

    if score >= 50:
        return "Partial alignment"

    return "Low alignment"


def score_message(score: float) -> str:

    if score >= 80:
        return "Your resume contains strong overlap with this job."

    if score >= 65:
        return "You have meaningful overlap, but there are still gaps."

    if score >= 50:
        return "There is some overlap, but tailoring would help."

    return "Your resume currently has limited overlap with this role."


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.title("🚀 LaunchPad")

    st.caption(
        "AI Career OS for analyzing jobs, "
        "improving applications, and tracking progress."
    )

    st.divider()

    st.subheader("Navigation")

    page = st.radio(
        "Go to",
        [
            "🎯 Job Analyzer",
            "📊 Application Dashboard",
            "🧠 Skill Inventory",
        ],
        label_visibility="collapsed",
    )

    st.divider()

    st.caption(
        "Built with Python • Streamlit • SQLite • scikit-learn"
    )


# ============================================================
# JOB ANALYZER
# ============================================================

if page == "🎯 Job Analyzer":

    st.title("🎯 Job Analyzer")

    st.markdown(
        """
        **Paste your resume and a job description.**
        LaunchPad will analyze technical overlap, semantic similarity,
        missing skills, and application fit.
        """
    )

    col1, col2 = st.columns(2, gap="large")

    with col1:

        st.subheader("Your Resume")

        resume_file = st.file_uploader(
            "Upload PDF",
            type=["pdf"],
        )

        resume_text_input = st.text_area(
            "Or paste resume text",
            height=300,
            placeholder=(
                "Paste your resume here..."
            ),
        )

        final_resume_text = resume_text_input

        if resume_file:

            try:
                pdf_text = extract_text_from_pdf(
                    resume_file
                )

                if pdf_text.strip():

                    final_resume_text = pdf_text

                    st.success(
                        f"PDF loaded — {len(pdf_text):,} characters"
                    )

                    with st.expander(
                        "Preview extracted resume"
                    ):
                        st.text(
                            pdf_text[:4000]
                        )

                else:

                    st.warning(
                        "The PDF contains little or no selectable text. "
                        "It may be a scanned image."
                    )

            except Exception as exc:

                st.error(
                    f"Could not read the PDF: {exc}"
                )

    with col2:

        st.subheader("Target Job")

        company = st.text_input(
            "Company",
            placeholder="Example: OpenAI",
        )

        role = st.text_input(
            "Role",
            placeholder="Example: Software Engineer",
        )

        job_description = st.text_area(
            "Job Description",
            height=300,
            placeholder=(
                "Paste the complete job description here..."
            ),
        )

    st.divider()

    analyze_button = st.button(
        "🚀 Analyze Job",
        type="primary",
        use_container_width=True,
    )

    if analyze_button:

        if not final_resume_text.strip():

            st.error(
                "Please upload a resume or paste your resume text."
            )

        elif not job_description.strip():

            st.error(
                "Please paste the job description."
            )

        else:

            with st.spinner(
                "Analyzing resume and job description..."
            ):

                analysis = analyze_match(
                    final_resume_text,
                    job_description,
                )

            st.session_state["analysis"] = analysis
            st.session_state["company"] = company or "Target Company"
            st.session_state["role"] = role or "Target Role"

    # --------------------------------------------------------
    # RESULTS
    # --------------------------------------------------------

    if "analysis" in st.session_state:

        analysis = st.session_state["analysis"]
        company = st.session_state["company"]
        role = st.session_state["role"]

        st.divider()

        st.header(
            f"Results — {role}"
        )

        st.caption(company)

        score = analysis["score"]

        st.success(
            f"{score_label(score)} — {score_message(score)}"
        )

        metric1, metric2, metric3, metric4 = st.columns(4)

        metric1.metric(
            "Overall Match",
            f"{score:.0f}%",
        )

        metric2.metric(
            "Skill Match",
            f"{analysis['skill_score']:.0f}%",
        )

        metric3.metric(
            "Semantic Match",
            f"{analysis['semantic_score']:.0f}%",
        )

        metric4.metric(
            "Missing Skills",
            len(analysis["missing_skills"]),
        )

        # ----------------------------------------------------
        # SKILLS
        # ----------------------------------------------------

        st.subheader("🧠 Skill Analysis")

        skill_col1, skill_col2 = st.columns(2)

        with skill_col1:

            st.markdown("### ✅ Skills You Have")

            if analysis["matched_skills"]:

                for skill in analysis["matched_skills"]:

                    category = SKILLS[skill][0]

                    st.write(
                        f"**{skill}** · {category}"
                    )

                    evidence = analysis[
                        "evidence"
                    ].get(skill)

                    if evidence:

                        st.caption(
                            f"Resume evidence: {evidence}"
                        )

            else:

                st.info(
                    "No recognized overlapping skills were detected."
                )

        with skill_col2:

            st.markdown("### 🎯 Skills Missing")

            if analysis["missing_skills"]:

                for skill in analysis["missing_skills"]:

                    category = SKILLS[skill][0]

                    st.write(
                        f"**{skill}** · {category}"
                    )

            else:

                st.success(
                    "No missing skills were detected from the current skill bank."
                )

        # ----------------------------------------------------
        # CHART
        # ----------------------------------------------------

        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:

            chart_data = pd.DataFrame(
                {
                    "Category": [
                        "Skill Match",
                        "Semantic Match",
                    ],
                    "Score": [
                        analysis["skill_score"],
                        analysis["semantic_score"],
                    ],
                }
            )

            fig = px.bar(
                chart_data,
                x="Category",
                y="Score",
                range_y=[0, 100],
                title="Match Components",
                text="Score",
            )

            fig.update_traces(
                texttemplate="%{text:.0f}%",
                textposition="outside",
            )

            fig.update_layout(
                height=350,
                margin=dict(
                    t=60,
                    b=20,
                    l=20,
                    r=20,
                ),
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
            )

        with chart_col2:

            matched_count = len(
                analysis["matched_skills"]
            )

            missing_count = len(
                analysis["missing_skills"]
            )

            if matched_count + missing_count > 0:

                pie_data = pd.DataFrame(
                    {
                        "Type": [
                            "Matched",
                            "Missing",
                        ],
                        "Count": [
                            matched_count,
                            missing_count,
                        ],
                    }
                )

                fig2 = px.pie(
                    pie_data,
                    values="Count",
                    names="Type",
                    hole=0.55,
                    title="Detected Job Skills",
                )

                fig2.update_layout(
                    height=350,
                    margin=dict(
                        t=60,
                        b=20,
                        l=20,
                        r=20,
                    ),
                )

                st.plotly_chart(
                    fig2,
                    use_container_width=True,
                )

        # ----------------------------------------------------
        # COVER LETTER
        # ----------------------------------------------------

        st.divider()

        st.subheader(
            "✍️ Tailored Cover Letter"
        )

        cover_letter = generate_cover_letter(
            company,
            role,
            analysis,
        )

        st.text_area(
            "Generated draft",
            value=cover_letter,
            height=420,
        )

        st.download_button(
            "⬇️ Download Cover Letter",
            data=cover_letter,
            file_name=(
                f"{company.lower().replace(' ', '_')}"
                "_cover_letter.txt"
            ),
            mime="text/plain",
        )

        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        st.divider()

        if st.button(
            "💾 Save Application",
            type="secondary",
            use_container_width=True,
        ):

            save_application(
                company,
                role,
                analysis,
            )

            st.success(
                "Application saved to your tracker."
            )

            st.rerun()


# ============================================================
# APPLICATION DASHBOARD
# ============================================================

elif page == "📊 Application Dashboard":

    st.title("📊 Application Dashboard")

    applications = get_applications()

    if not applications:

        st.info(
            "No applications yet. Analyze a job and save it to build your tracker."
        )

    else:

        df = pd.DataFrame(
            [
                {
                    "ID": app.id,
                    "Company": app.company,
                    "Role": app.role,
                    "Match": app.match_score,
                    "Status": app.status,
                    "Date": (
                        app.created_at.strftime(
                            "%Y-%m-%d"
                        )
                        if app.created_at
                        else ""
                    ),
                }
                for app in applications
            ]
        )

        # ----------------------------------------------------
        # METRICS
        # ----------------------------------------------------

        total = len(df)

        interviews = len(
            df[
                df["Status"].isin(
                    [
                        "Interview",
                        "Technical Interview",
                        "Offer",
                    ]
                )
            ]
        )

        offers = len(
            df[df["Status"] == "Offer"]
        )

        average_match = (
            df["Match"].mean()
        )

        m1, m2, m3, m4 = st.columns(4)

        m1.metric(
            "Applications",
            total,
        )

        m2.metric(
            "Interview Stage",
            interviews,
        )

        m3.metric(
            "Offers",
            offers,
        )

        m4.metric(
            "Average Match",
            f"{average_match:.0f}%",
        )

        st.divider()

        # ----------------------------------------------------
        # STATUS MANAGEMENT
        # ----------------------------------------------------

        st.subheader(
            "Application Tracker"
        )

        for app in applications:

            with st.expander(
                f"{app.company} — {app.role} "
                f"({app.match_score:.0f}%)"
            ):

                col1, col2, col3 = st.columns(
                    [2, 2, 1]
                )

                with col1:

                    new_status = st.selectbox(
                        "Status",
                        STATUSES,
                        index=(
                            STATUSES.index(app.status)
                            if app.status in STATUSES
                            else 0
                        ),
                        key=f"status_{app.id}",
                    )

                with col2:

                    st.write(
                        f"**Created:** "
                        f"{app.created_at.strftime('%Y-%m-%d')}"
                        if app.created_at
                        else ""
                    )

                    st.write(
                        f"**Match:** "
                        f"{app.match_score:.0f}%"
                    )

                with col3:

                    if st.button(
                        "Delete",
                        key=f"delete_{app.id}",
                    ):

                        delete_application(
                            app.id
                        )

                        st.rerun()

                if new_status != app.status:

                    if st.button(
                        "Save Status",
                        key=f"save_{app.id}",
                    ):

                        update_application_status(
                            app.id,
                            new_status,
                        )

                        st.success(
                            "Status updated."
                        )

                        st.rerun()

                st.write(
                    "**Matched:** "
                    + (
                        app.matched_skills
                        or "None detected"
                    )
                )

                st.write(
                    "**Missing:** "
                    + (
                        app.missing_skills
                        or "None detected"
                    )
                )

        st.divider()

        # ----------------------------------------------------
        # DATA TABLE
        # ----------------------------------------------------

        st.subheader(
            "All Applications"
        )

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
        )

        # ----------------------------------------------------
        # CHARTS
        # ----------------------------------------------------

        chart1, chart2 = st.columns(2)

        with chart1:

            fig = px.bar(
                df,
                x="Company",
                y="Match",
                color="Status",
                title="Match Score by Company",
                range_y=[0, 100],
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
            )

        with chart2:

            status_counts = (
                df["Status"]
                .value_counts()
                .reset_index()
            )

            status_counts.columns = [
                "Status",
                "Applications",
            ]

            fig2 = px.pie(
                status_counts,
                values="Applications",
                names="Status",
                title="Application Pipeline",
                hole=0.5,
            )

            st.plotly_chart(
                fig2,
                use_container_width=True,
            )

        # ----------------------------------------------------
        # CSV EXPORT
        # ----------------------------------------------------

        csv_data = df.to_csv(
            index=False
        ).encode("utf-8")

        st.download_button(
            "⬇️ Export Applications CSV",
            data=csv_data,
            file_name="launchpad_applications.csv",
            mime="text/csv",
        )


# ============================================================
# SKILL INVENTORY
# ============================================================

elif page == "🧠 Skill Inventory":

    st.title("🧠 Skill Inventory")

    st.markdown(
        """
        This is the skill vocabulary LaunchPad currently understands.
        You can expand this list as you target different careers.
        """
    )

    skill_rows = []

    for skill, (
        category,
        weight,
    ) in SKILLS.items():

        skill_rows.append(
            {
                "Skill": skill,
                "Category": category,
                "Importance Weight": weight,
            }
        )

    skills_df = pd.DataFrame(
        skill_rows
    ).sort_values(
        ["Category", "Skill"]
    )

    st.dataframe(
        skills_df,
        use_container_width=True,
        hide_index=True,
    )

    st.metric(
        "Recognized Skills",
        len(SKILLS),
    )

    st.info(
        "For a production version, move this skill bank into a database "
        "or configuration file so it can be updated without changing code."
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "LaunchPad AI Career OS • Portfolio Project • "
    "Python + Streamlit + SQLAlchemy + scikit-learn"
)