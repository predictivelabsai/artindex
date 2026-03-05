import streamlit as st
import plotly.express as px
import pandas as pd
import numpy as np
from utils.db import fetch_lots

st.set_page_config(page_title="Kanvas.AI Art Index", layout="wide")
st.title("Kanvas.AI Art Index")

PROVIDERS = {"All": None, "Allee Galerii": "allee", "Haus": "haus"}
provider_label = st.sidebar.selectbox("Auction Provider", list(PROVIDERS.keys()))
provider = PROVIDERS[provider_label]

rows = fetch_lots(provider)

if not rows:
    st.warning("No data found. Run `python -m utils.db` to import CSV data.")
    st.stop()

df = pd.DataFrame(rows)
df = df[df["start_price"] > 0].copy()
df["year"] = df["year"].where(df["year"] > 1800)
df["decade"] = df["decade"].where(df["decade"] > 1800)
df["tech"] = df["tech"].fillna("Unknown")
df["category"] = df["category"].fillna("Unknown")
df["overbid_%"] = (df["end_price"] - df["start_price"]) / df["start_price"] * 100
df["art_work_age"] = df["auction_date"] - df["year"]

st.sidebar.metric("Total Lots", len(df))

# --- Treemap ---
st.header("Best selling artists — total sales by overbidding %")

df2 = df.groupby(["author", "tech", "category"]).agg(
    total_sales=("end_price", "sum"),
    overbid_pct=("overbid_%", "mean"),
).reset_index()
df2["overbid_pct"] = df2["overbid_pct"] * 100
df2 = df2.dropna(subset=["overbid_pct", "total_sales"])
df2 = df2[df2["total_sales"] > 0]
midpoint = np.average(df2["overbid_pct"], weights=df2["total_sales"]) if len(df2) > 0 else 0

fig = px.treemap(
    df2,
    path=["category", "tech", "author"],
    values="total_sales",
    color="overbid_pct",
    hover_data=["author"],
    color_continuous_scale="RdBu",
    color_continuous_midpoint=midpoint,
)
fig.update_layout(margin=dict(t=30, l=0, r=0, b=0))
st.plotly_chart(fig, use_container_width=True)

# --- Age scatter ---
st.header("Is older art more expensive? Age vs. price")

dfa = df.dropna(subset=["art_work_age", "end_price", "decade"])
fig = px.scatter(
    dfa, x="art_work_age", y="end_price", color="category",
    size="decade", hover_data=["author"],
)
fig.update_layout(
    xaxis_title="Artwork Age (years)",
    yaxis_title="End Price (EUR)",
    margin=dict(t=30, l=0, r=0, b=0),
)
st.plotly_chart(fig, use_container_width=True)

# --- Dimension scatter ---
st.header("Are larger works more expensive? Dimensions vs. price")

dfd = df.dropna(subset=["dimension", "end_price"])
dfd = dfd[dfd["dimension"] > 0]
fig = px.scatter(
    dfd, x="dimension", y="end_price", color="category",
    size="dimension", hover_data=["author"],
)
fig.update_layout(
    xaxis_title="Dimension",
    yaxis_title="End Price (EUR)",
    margin=dict(t=30, l=0, r=0, b=0),
)
st.plotly_chart(fig, use_container_width=True)

st.caption(f"Author: Julian Kaljuvee | Source: Art auction data | {len(df)} lots")
