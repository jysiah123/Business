import os
import json
import random
from datetime import datetime, timedelta

import pandas as pd  # type: ignore[reportMissingModuleSource]
import streamlit as st  # type: ignore[reportMissingImports]
import plotly.express as px  # type: ignore[reportMissingImports]

try:
    from openai import OpenAI  # type: ignore[reportMissingImports]
except ImportError:
    OpenAI = None


# ============================================================
# REVENUE RECOVERY AI
# AI-powered revenue leakage detection and action system
# ============================================================

st.set_page_config(
    page_title="Revenue Recovery AI",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# STYLING
# ============================================================

st.markdown(
    """
    <style>

    .stApp {
        background: #f6f7fb;
    }

    .hero {
        background: linear-gradient(
            135deg,
            #111827 0%,
            #1f2937 55%,
            #312e81 100%
        );

        padding: 2rem;
        border-radius: 20px;
        color: white;
        margin-bottom: 1.5rem;
    }

    .hero h1 {
        font-size: 2.7rem;
        margin-bottom: 0.3rem;
    }

    .hero p {
        font-size: 1.1rem;
        color: #d1d5db;
    }

    .money-card {
        background: white;
        padding: 1.3rem;
        border-radius: 15px;
        border: 1px solid #e5e7eb;
        min-height: 120px;
    }

    .money-number {
        font-size: 2rem;
        font-weight: 800;
    }

    .money-label {
        color: #6b7280;
        font-size: 0.9rem;
    }

    .opportunity {
        background: white;
        border-radius: 15px;
        padding: 1.2rem;
        border: 1px solid #e5e7eb;
        margin-bottom: 1rem;
    }

    .high {
        border-left: 6px solid #dc2626;
    }

    .medium {
        border-left: 6px solid #d97706;
    }

    .low {
        border-left: 6px solid #16a34a;
    }

    .tag {
        display: inline-block;
        padding: 0.25rem 0.55rem;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 700;
        margin-right: 0.4rem;
    }

    .footer {
        color: #6b7280;
        text-align: center;
        padding: 2rem;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    """
    <div class="hero">

        <h1>💰 Revenue Recovery AI</h1>

        <p>
        Find revenue your business may be leaving on the table,
        prioritize the highest-value opportunities, and turn
        analysis into measurable actions.
        </p>

    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# HELPERS
# ============================================================

def money(value):
    if value is None or pd.isna(value):
        return "$0"

    value = float(value)

    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"

    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f}K"

    return f"${value:,.0f}"


def clean_columns(df):
    df = df.copy()

    df.columns = [
        str(c)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
        for c in df.columns
    ]

    return df


def find_column(df, names):
    columns = list(df.columns)

    # Exact matches first
    for name in names:
        if name in columns:
            return name

    # Partial matches second
    for column in columns:
        for name in names:
            if name in column:
                return column

    return None


def safe_numeric(df, column):
    if not column:
        return None

    df[column] = pd.to_numeric(
        df[column],
        errors="coerce"
    ).fillna(0)

    return column


def create_demo_data():
    """
    Creates realistic-looking demo data.

    This is ONLY for testing the application.
    It is not real customer information.
    """

    random.seed(42)

    today = datetime.now()

    customers = [
        f"CUSTOMER-{i:04d}"
        for i in range(1, 151)
    ]

    customer_names = {
        customer: f"Business {i:03d}"
        for i, customer in enumerate(
            customers,
            start=1
        )
    }

    products = [
        "HVAC Service",
        "AC Installation",
        "Plumbing",
        "Electrical",
        "Maintenance",
        "Repair",
    ]

    statuses = [
        "won",
        "won",
        "won",
        "quote",
        "invoice",
    ]

    rows = []

    for i in range(900):

        customer = random.choice(
            customers
        )

        status = random.choice(
            statuses
        )

        days_ago = random.randint(
            1,
            420
        )

        date = today - timedelta(
            days=int(days_ago)
        )

        product = random.choice(
            products
        )

        amount = random.uniform(
            300,
            6500
        )

        cost = amount * random.uniform(
            0.35,
            0.82
        )

        discount = random.choice(
            [
                0,
                0,
                0,
                0.05,
                0.10,
                0.15,
                0.20
            ]
        )

        # Create realistic overdue invoices
        if status == "invoice":

            due_days = random.randint(
                -60,
                45
            )

        else:

            due_days = 0

        rows.append(
            {
                "date": date,
                "customer_id": customer,
                "customer_name": customer_names[customer],
                "product": product,
                "status": status,
                "amount": round(amount, 2),
                "cost": round(cost, 2),
                "discount": discount,
                "days_until_due": due_days,
            }
        )

    df = pd.DataFrame(rows)

    # Add deliberately recoverable opportunities.

    # Large stale quote
    df.loc[10, "status"] = "quote"
    df.loc[10, "amount"] = 8200
    df.loc[10, "date"] = today - timedelta(days=24)

    # Large overdue invoice
    df.loc[25, "status"] = "invoice"
    df.loc[25, "amount"] = 5400
    df.loc[25, "days_until_due"] = -31

    # Large inactive customer transaction
    df.loc[50, "status"] = "won"
    df.loc[50, "amount"] = 3900
    df.loc[50, "date"] = today - timedelta(days=390)

    # Very large discount
    df.loc[75, "status"] = "won"
    df.loc[75, "amount"] = 7000
    df.loc[75, "discount"] = 0.25

    # Low margin job
    df.loc[100, "status"] = "won"
    df.loc[100, "amount"] = 4500
    df.loc[100, "cost"] = 4300

    return df


def normalize_business_data(raw_df):
    """
    Attempts to convert a messy CSV into the fields
    our revenue-recovery engine understands.
    """

    df = clean_columns(raw_df)

    mapping = {
        "date": [
            "date",
            "order_date",
            "transaction_date",
            "created_at",
            "quote_date",
            "invoice_date",
        ],

        "customer_id": [
            "customer_id",
            "client_id",
            "account_id",
            "customer",
            "client",
        ],

        "customer_name": [
            "customer_name",
            "client_name",
            "account_name",
            "company",
            "business_name",
        ],

        "amount": [
            "amount",
            "revenue",
            "sales",
            "total",
            "value",
            "price",
            "invoice_amount",
            "quote_amount",
        ],

        "cost": [
            "cost",
            "cogs",
            "expense",
            "expenses",
        ],

        "status": [
            "status",
            "stage",
            "deal_stage",
            "invoice_status",
        ],

        "discount": [
            "discount",
            "discount_rate",
            "discount_percent",
        ],

        "product": [
            "product",
            "service",
            "product_name",
            "service_name",
            "category",
        ],

        "region": [
            "region",
            "territory",
            "location",
        ],

        "due_date": [
            "due_date",
            "payment_due",
        ],
    }

    detected = {}

    for standard_name, candidates in mapping.items():

        detected[
            standard_name
        ] = find_column(
            df,
            candidates
        )

    # Rename detected columns
    rename_map = {}

    for standard_name, actual_column in detected.items():

        if actual_column:
            rename_map[
                actual_column
            ] = standard_name

    df = df.rename(
        columns=rename_map
    )

    # Required conversions

    if "date" in df.columns:

        df["date"] = pd.to_datetime(
            df["date"],
            errors="coerce"
        )

    for column in [
        "amount",
        "cost",
        "discount",
    ]:

        if column in df.columns:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            ).fillna(0)

    if "discount" in df.columns:

        # Convert 15 -> 0.15
        if df["discount"].max() > 1:

            df["discount"] = (
                df["discount"] / 100
            )

    # Calculate missing cost if necessary
    if (
        "amount" in df.columns
        and "cost" not in df.columns
    ):

        df["cost"] = 0

    # Calculate margin
    if (
        "amount" in df.columns
        and "cost" in df.columns
    ):

        df["margin"] = (
            (
                df["amount"]
                - df["cost"]
            )
            / df["amount"].where(
                df["amount"] != 0
            )
        ).fillna(0)

    return df, detected


# ============================================================
# REVENUE OPPORTUNITY ENGINE
# ============================================================

def detect_opportunities(df):

    opportunities = []

    today = pd.Timestamp(
        datetime.now()
    ).normalize()

    # --------------------------------------------------------
    # 1. STALE QUOTES
    # --------------------------------------------------------

    if (
        "status" in df.columns
        and "date" in df.columns
        and "amount" in df.columns
    ):

        quote_mask = (
            df["status"]
            .astype(str)
            .str.lower()
            .str.contains(
                "quote|estimate|proposal",
                regex=True
            )
        )

        stale_quotes = df[
            quote_mask
            & (
                (
                    today
                    - df["date"]
                ).dt.days >= 7
            )
        ]

        for index, row in stale_quotes.iterrows():

            age = (
                today
                - row["date"]
            ).days

            amount = float(
                row["amount"]
            )

            probability = min(
                0.75,
                max(
                    0.20,
                    0.65
                    - (
                        max(age - 7, 0)
                        * 0.01
                    )
                )
            )

            opportunity = (
                amount
                * probability
            )

            customer = row.get(
                "customer_name",
                row.get(
                    "customer_id",
                    "Unknown"
                )
            )

            opportunities.append(
                {
                    "type": "Stale Quote",
                    "priority": (
                        "HIGH"
                        if opportunity >= 2500
                        else "MEDIUM"
                    ),
                    "customer": customer,
                    "amount": amount,
                    "estimated_opportunity": opportunity,
                    "reason": (
                        f"Quote is {age} days old "
                        "with no recorded conversion."
                    ),
                    "action": (
                        "Follow up on the quote "
                        "and identify the customer's "
                        "current decision status."
                    ),
                    "source_index": index,
                }
            )

    # --------------------------------------------------------
    # 2. OVERDUE INVOICES
    # --------------------------------------------------------

    if (
        "status" in df.columns
        and "amount" in df.columns
    ):

        invoice_mask = (
            df["status"]
            .astype(str)
            .str.lower()
            .str.contains(
                "invoice|overdue|unpaid",
                regex=True
            )
        )

        overdue = df[
            invoice_mask
        ].copy()

        if "due_date" in overdue.columns:

            overdue["due_date"] = pd.to_datetime(
                overdue["due_date"],
                errors="coerce"
            )

            overdue = overdue[
                overdue["due_date"]
                < today
            ]

        elif "days_until_due" in overdue.columns:

            overdue = overdue[
                overdue["days_until_due"] < 0
            ]

        else:

            # Conservative fallback:
            # invoice older than 30 days
            if "date" in overdue.columns:

                overdue = overdue[
                    (
                        today
                        - overdue["date"]
                    ).dt.days > 30
                ]

        for index, row in overdue.iterrows():

            amount = float(
                row["amount"]
            )

            customer = row.get(
                "customer_name",
                row.get(
                    "customer_id",
                    "Unknown"
                )
            )

            opportunities.append(
                {
                    "type": "Overdue Invoice",
                    "priority": (
                        "HIGH"
                        if amount >= 2000
                        else "MEDIUM"
                    ),
                    "customer": customer,
                    "amount": amount,
                    "estimated_opportunity": amount,
                    "reason": (
                        "Invoice appears to be "
                        "past its payment due date."
                    ),
                    "action": (
                        "Review invoice status and "
                        "send an approved payment reminder."
                    ),
                    "source_index": index,
                }
            )

    # --------------------------------------------------------
    # 3. DORMANT CUSTOMERS
    # --------------------------------------------------------

    if (
        "customer_id" in df.columns
        and "date" in df.columns
        and "amount" in df.columns
    ):

        customer_summary = (
            df.groupby(
                "customer_id"
            )
            .agg(
                last_date=("date", "max"),
                total_revenue=(
                    "amount",
                    "sum"
                ),
            )
            .reset_index()
        )

        customer_names = {}

        if "customer_name" in df.columns:

            customer_names = (
                df.dropna(
                    subset=["customer_id"]
                )
                .drop_duplicates(
                    "customer_id"
                )
                .set_index(
                    "customer_id"
                )["customer_name"]
                .to_dict()
            )

        for _, row in customer_summary.iterrows():

            if pd.isna(
                row["last_date"]
            ):
                continue

            days_inactive = (
                today
                - row["last_date"]
            ).days

            historical_value = float(
                row["total_revenue"]
            )

            if (
                days_inactive >= 180
                and historical_value >= 1000
            ):

                estimated_opportunity = (
                    historical_value
                    * 0.20
                )

                customer_id = row[
                    "customer_id"
                ]

                customer = customer_names.get(
                    customer_id,
                    customer_id
                )

                opportunities.append(
                    {
                        "type": "Dormant Customer",
                        "priority": (
                            "HIGH"
                            if historical_value >= 5000
                            else "MEDIUM"
                        ),
                        "customer": customer,
                        "amount": historical_value,
                        "estimated_opportunity":
                            estimated_opportunity,
                        "reason": (
                            f"Customer has been inactive "
                            f"for {days_inactive} days."
                        ),
                        "action": (
                            "Review the customer's history "
                            "and consider a personalized "
                            "win-back campaign."
                        ),
                        "source_index": None,
                    }
                )

    # --------------------------------------------------------
    # 4. EXCESSIVE DISCOUNTING
    # --------------------------------------------------------

    if (
        "discount" in df.columns
        and "amount" in df.columns
    ):

        discount_rows = df[
            df["discount"] >= 0.15
        ]

        for index, row in discount_rows.iterrows():

            discount = float(
                row["discount"]
            )

            amount = float(
                row["amount"]
            )

            estimated_leakage = (
                amount
                * discount
            )

            customer = row.get(
                "customer_name",
                row.get(
                    "customer_id",
                    "Unknown"
                )
            )

            opportunities.append(
                {
                    "type": "Excessive Discount",
                    "priority": (
                        "HIGH"
                        if discount >= 0.25
                        else "MEDIUM"
                    ),
                    "customer": customer,
                    "amount": amount,
                    "estimated_opportunity":
                        estimated_leakage,
                    "reason": (
                        f"Transaction received a "
                        f"{discount:.0%} discount."
                    ),
                    "action": (
                        "Review discount justification "
                        "and establish pricing guardrails."
                    ),
                    "source_index": index,
                }
            )

    # --------------------------------------------------------
    # 5. LOW-MARGIN TRANSACTIONS
    # --------------------------------------------------------

    if (
        "margin" in df.columns
        and "amount" in df.columns
    ):

        low_margin = df[
            df["margin"] < 0.10
        ]

        for index, row in low_margin.iterrows():

            amount = float(
                row["amount"]
            )

            margin = float(
                row["margin"]
            )

            # Potential improvement to 20% margin
            target_profit = (
                amount * 0.20
            )

            current_profit = (
                amount * margin
            )

            potential = max(
                0,
                target_profit
                - current_profit
            )

            if potential <= 0:
                continue

            customer = row.get(
                "customer_name",
                row.get(
                    "customer_id",
                    "Unknown"
                )
            )

            opportunities.append(
                {
                    "type": "Low Margin",
                    "priority": (
                        "HIGH"
                        if margin < 0
                        else "MEDIUM"
                    ),
                    "customer": customer,
                    "amount": amount,
                    "estimated_opportunity":
                        potential,
                    "reason": (
                        f"Transaction margin is "
                        f"{margin:.1%}."
                    ),
                    "action": (
                        "Review pricing, labor, "
                        "materials, and delivery costs."
                    ),
                    "source_index": index,
                }
            )

    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    priority_rank = {
        "HIGH": 0,
        "MEDIUM": 1,
        "LOW": 2,
    }

    opportunities = sorted(
        opportunities,
        key=lambda x: (
            priority_rank.get(
                x["priority"],
                9
            ),
            -x["estimated_opportunity"]
        )
    )

    return opportunities


# ============================================================
# AI ENGINE
# ============================================================

def get_ai_client():

    if OpenAI is None:
        return None

    api_key = os.getenv(
        "OPENAI_API_KEY"
    )

    if not api_key:
        return None

    return OpenAI(
        api_key=api_key
    )


def ai_analyze(question, df, opportunities):

    client = get_ai_client()

    if client is None:

        return (
            "AI is not connected yet.\n\n"
            "The rule-based revenue engine is still "
            "working. To enable AI analysis, set "
            "the OPENAI_API_KEY environment variable."
        )

    summary = {
        "rows": len(df),
        "columns": list(df.columns),
        "total_revenue": (
            float(df["amount"].sum())
            if "amount" in df.columns
            else 0
        ),
        "total_cost": (
            float(df["cost"].sum())
            if "cost" in df.columns
            else 0
        ),
        "opportunity_count": len(
            opportunities
        ),
        "estimated_recoverable_value": (
            sum(
                x["estimated_opportunity"]
                for x in opportunities
            )
        ),
        "top_opportunities":
            opportunities[:20],
    }

    prompt = f"""
You are the senior revenue-operations analyst
for a small or medium-sized business.

Your job is to help management find REAL,
evidence-based opportunities to improve revenue
and profitability.

Do not invent customers, transactions,
financial numbers, or facts.

Treat "estimated recoverable value" as an
estimate, NOT guaranteed revenue.

Separate:
1. Facts
2. Inferences
3. Recommendations

Business data summary:

{json.dumps(summary, default=str, indent=2)}

User question:

{question}

Respond using:

## Executive Answer

## Evidence

## Highest-Value Opportunity

## Recommended Actions

## Risks / Uncertainty

## Data We Need Next
"""

    try:

        response = client.responses.create(
            model="gpt-5.6-luna",
            input=prompt
        )

        return response.output_text

    except Exception as error:

        return (
            f"AI request failed: {error}"
        )


def generate_customer_message(opportunity):

    client = get_ai_client()

    if client is None:

        return (
            "AI messaging is unavailable. "
            "Connect OPENAI_API_KEY first."
        )

    prompt = f"""
Write a short, professional customer follow-up
based ONLY on the information below.

Do not claim that the customer owes money unless
the opportunity explicitly identifies an overdue
invoice.

Do not invent dates, prices, promises, or facts.

Opportunity type:
{opportunity["type"]}

Customer:
{opportunity["customer"]}

Amount:
{opportunity["amount"]}

Reason:
{opportunity["reason"]}

Recommended action:
{opportunity["action"]}

Create a polite business message that a human
employee can review before sending.

Do not include a subject line.
"""

    try:

        response = client.responses.create(
            model="gpt-5.6-luna",
            input=prompt
        )

        return response.output_text

    except Exception as error:

        return (
            f"Message generation failed: {error}"
        )


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header(
    "Revenue Recovery"
)

uploaded = st.sidebar.file_uploader(
    "Upload business CSV",
    type=["csv"]
)

if st.sidebar.button(
    "🚀 Load Demo Business",
    use_container_width=True
):

    st.session_state["raw_df"] = (
        create_demo_data()
    )

    st.session_state[
        "source"
    ] = "Demo Business"


if uploaded is not None:

    try:

        st.session_state["raw_df"] = (
            pd.read_csv(uploaded)
        )

        st.session_state[
            "source"
        ] = uploaded.name

    except Exception as error:

        st.sidebar.error(
            f"Could not read file: {error}"
        )


# ============================================================
# START SCREEN
# ============================================================

if "raw_df" not in st.session_state:

    st.info(
        "Upload a business CSV or click "
        "**Load Demo Business**."
    )

    st.markdown(
        """
        ### What this product is designed to find

        **💵 Stale quotes**

        Money sitting in proposals that may never
        have received a follow-up.

        **💳 Overdue invoices**

        Revenue that has already been earned but
        may not have been collected.

        **👥 Dormant customers**

        Previously valuable customers who have
        stopped buying.

        **🏷️ Excessive discounts**

        Revenue potentially being sacrificed
        through aggressive discounting.

        **📉 Low-margin work**

        Jobs where revenue looks good but
        profitability is weak.

        ### Start with the demo

        Click **Load Demo Business** in the sidebar.
        """
    )

    st.stop()


# ============================================================
# NORMALIZE DATA
# ============================================================

df, detected_columns = normalize_business_data(
    st.session_state["raw_df"]
)

opportunities = detect_opportunities(
    df
)


# ============================================================
# TOP METRICS
# ============================================================

total_revenue = (
    df["amount"].sum()
    if "amount" in df.columns
    else 0
)

total_cost = (
    df["cost"].sum()
    if "cost" in df.columns
    else 0
)

profit = (
    total_revenue
    - total_cost
)

margin = (
    profit / total_revenue
    if total_revenue
    else 0
)

estimated_opportunity = sum(
    x["estimated_opportunity"]
    for x in opportunities
)

high_priority = [
    x
    for x in opportunities
    if x["priority"] == "HIGH"
]

medium_priority = [
    x
    for x in opportunities
    if x["priority"] == "MEDIUM"
]


st.subheader(
    "Executive Revenue Recovery Dashboard"
)

metric_columns = st.columns(4)

with metric_columns[0]:

    st.markdown(
        f"""
        <div class="money-card">
            <div class="money-label">
                Total Revenue
            </div>

            <div class="money-number">
                {money(total_revenue)}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


with metric_columns[1]:

    st.markdown(
        f"""
        <div class="money-card">
            <div class="money-label">
                Estimated Opportunity
            </div>

            <div class="money-number">
                {money(estimated_opportunity)}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


with metric_columns[2]:

    st.markdown(
        f"""
        <div class="money-card">
            <div class="money-label">
                High-Priority Issues
            </div>

            <div class="money-number">
                {len(high_priority)}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


with metric_columns[3]:

    st.markdown(
        f"""
        <div class="money-card">
            <div class="money-label">
                Profit Margin
            </div>

            <div class="money-number">
                {margin:.1%}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


st.write("")


# ============================================================
# OPPORTUNITY PIPELINE
# ============================================================

st.subheader(
    "🎯 Revenue Recovery Pipeline"
)

pipeline_columns = st.columns(3)

with pipeline_columns[0]:

    st.metric(
        "High Priority",
        money(
            sum(
                x["estimated_opportunity"]
                for x in high_priority
            )
        ),
        f"{len(high_priority)} opportunities"
    )


with pipeline_columns[1]:

    st.metric(
        "Medium Priority",
        money(
            sum(
                x["estimated_opportunity"]
                for x in medium_priority
            )
        ),
        f"{len(medium_priority)} opportunities"
    )


with pipeline_columns[2]:

    st.metric(
        "Total Estimated",
        money(
            estimated_opportunity
        ),
        f"{len(opportunities)} opportunities"
    )


# ============================================================
# OPPORTUNITY TABLE
# ============================================================

st.subheader(
    "🚨 Highest-Value Opportunities"
)

if opportunities:

    opportunity_table = pd.DataFrame(
        [
            {
                "Priority":
                    x["priority"],

                "Opportunity":
                    x["type"],

                "Customer":
                    x["customer"],

                "Amount":
                    money(x["amount"]),

                "Estimated Opportunity":
                    money(
                        x[
                            "estimated_opportunity"
                        ]
                    ),

                "Reason":
                    x["reason"],
            }

            for x in opportunities[:50]
        ]
    )

    st.dataframe(
        opportunity_table,
        use_container_width=True,
        hide_index=True
    )

else:

    st.success(
        "No revenue opportunities were detected "
        "with the current rules."
    )


# ============================================================
# PRIORITIZED ACTION CENTER
# ============================================================

st.subheader(
    "⚡ Action Center"
)

if opportunities:

    for number, opportunity in enumerate(
        opportunities[:15],
        start=1
    ):

        priority_class = (
            opportunity["priority"]
            .lower()
        )

        with st.container():

            st.markdown(
                f"""
                <div class="opportunity {priority_class}">

                <h3>
                #{number} — {opportunity["type"]}
                </h3>

                <p>
                <strong>
                Customer:
                </strong>
                {opportunity["customer"]}
                </p>

                <p>
                <strong>
                Estimated opportunity:
                </strong>
                {money(
                    opportunity[
                        "estimated_opportunity"
                    ]
                )}
                </p>

                <p>
                <strong>
                Evidence:
                </strong>
                {opportunity["reason"]}
                </p>

                <p>
                <strong>
                Recommended action:
                </strong>
                {opportunity["action"]}
                </p>

                </div>
                """,
                unsafe_allow_html=True
            )

            action_columns = st.columns(
                [1, 1, 1]
            )

            with action_columns[0]:

                if st.button(
                    "🤖 Draft Customer Message",
                    key=f"draft_{number}"
                ):

                    with st.spinner(
                        "Generating draft..."
                    ):

                        message = (
                            generate_customer_message(
                                opportunity
                            )
                        )

                    st.text_area(
                        "Human-review draft",
                        value=message,
                        height=180,
                        key=f"message_{number}"
                    )

            with action_columns[1]:

                if st.button(
                    "📌 Mark Reviewed",
                    key=f"review_{number}"
                ):

                    st.success(
                        "Marked as reviewed."
                    )

            with action_columns[2]:

                if st.button(
                    "⏭️ Skip",
                    key=f"skip_{number}"
                ):

                    st.info(
                        "Opportunity skipped for this session."
                    )


# ============================================================
# VISUAL ANALYTICS
# ============================================================

st.subheader(
    "📊 Where the Opportunity Comes From"
)

if opportunities:

    type_df = (
        pd.DataFrame(
            opportunities
        )
        .groupby(
            "type"
        )["estimated_opportunity"]
        .sum()
        .reset_index()
        .sort_values(
            "estimated_opportunity",
            ascending=False
        )
    )

    fig = px.bar(
        type_df,
        x="type",
        y="estimated_opportunity",
        title="Estimated Opportunity by Issue Type"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )


# ============================================================
# REVENUE TREND
# ============================================================

if (
    "date" in df.columns
    and "amount" in df.columns
):

    st.subheader(
        "📈 Revenue Trend"
    )

    trend = (
        df.dropna(
            subset=["date"]
        )
        .groupby(
            pd.Grouper(
                key="date",
                freq="W"
            )
        )["amount"]
        .sum()
        .reset_index()
    )

    if len(trend) > 1:

        fig = px.line(
            trend,
            x="date",
            y="amount",
            markers=True,
            title="Weekly Revenue"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )


# ============================================================
# AI BUSINESS ANALYST
# ============================================================

st.subheader(
    "🧠 AI Revenue Analyst"
)

st.caption(
    "Ask questions about the detected revenue opportunities."
)

question = st.text_area(
    "Business question",
    placeholder=(
        "Example: Which three opportunities should "
        "the owner act on first, and why?"
    ),
    height=100
)

if st.button(
    "Analyze With AI",
    type="primary",
    use_container_width=True
):

    if not question.strip():

        st.warning(
            "Enter a question first."
        )

    else:

        with st.spinner(
            "AI is analyzing the business..."
        ):

            answer = ai_analyze(
                question,
                df,
                opportunities
            )

        st.markdown(
            answer
        )


# ============================================================
# AUTOMATIC EXECUTIVE BRIEF
# ============================================================

st.subheader(
    "📋 Executive Brief"
)

if st.button(
    "Generate 30-Day Action Plan",
    use_container_width=True
):

    question = """
Create a practical 30-day revenue recovery plan.

Rank the actions by expected financial impact.

For every major recommendation:
- explain the evidence
- explain why it matters
- estimate the opportunity when possible
- explain uncertainty
- identify what should be measured afterward

Do not invent information.
"""

    with st.spinner(
        "Building executive action plan..."
    ):

        plan = ai_analyze(
            question,
            df,
            opportunities
        )

    st.markdown(
        plan
    )


# ============================================================
# DATA DETECTION
# ============================================================

with st.expander(
    "🔍 Data Detection"
):

    st.write(
        "The system attempted to map your CSV "
        "into business fields automatically."
    )

    detection_table = pd.DataFrame(
        [
            {
                "Business Field": field,
                "Detected Column":
                    detected_columns.get(field)
            }

            for field
            in detected_columns
        ]
    )

    st.dataframe(
        detection_table,
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# RAW DATA
# ============================================================

with st.expander(
    "📁 Raw Business Data"
):

    st.dataframe(
        df.head(500),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# EXPORT
# ============================================================

st.subheader(
    "📄 Export Recovery Report"
)

report_lines = [
    "# Revenue Recovery AI Report",
    "",
    f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    "",
    "## Financial Summary",
    "",
    f"Total revenue: {money(total_revenue)}",
    f"Estimated profit: {money(profit)}",
    f"Profit margin: {margin:.1%}",
    f"Estimated opportunity: {money(estimated_opportunity)}",
    f"Detected opportunities: {len(opportunities)}",
    "",
    "## Highest-Priority Opportunities",
    "",
]

for opportunity in opportunities[:30]:

    report_lines.extend(
        [
            f"### {opportunity['type']}",
            "",
            f"Customer: {opportunity['customer']}",
            "",
            f"Priority: {opportunity['priority']}",
            "",
            (
                "Estimated opportunity: "
                f"{money(opportunity['estimated_opportunity'])}"
            ),
            "",
            f"Evidence: {opportunity['reason']}",
            "",
            f"Recommended action: {opportunity['action']}",
            "",
        ]
    )

report = "\n".join(
    report_lines
)

st.download_button(
    "⬇️ Download Recovery Report",
    data=report,
    file_name=(
        "revenue_recovery_report.md"
    ),
    mime="text/markdown",
    use_container_width=True
)


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.markdown(
    """
    <div class="footer">

    Revenue Recovery AI

    <br>

    <small>
    Estimates are decision-support outputs, not guaranteed revenue.
    Customer communications should be reviewed by a human before sending.
    </small>

    </div>
    """,
    unsafe_allow_html=True
)