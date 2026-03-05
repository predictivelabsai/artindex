from fasthtml.common import *
import plotly.express as px
import pandas as pd
import numpy as np
import json
from utils.db import fetch_lots

app, rt = fast_app(
    hdrs=[
        Script(src="https://cdn.plot.ly/plotly-2.35.2.min.js"),
    ],
    pico=True,
)

def plotly_div(fig, div_id="chart"):
    """Convert a Plotly figure to an HTML div with inline JS."""
    fig_json = json.dumps(fig.to_dict(), default=str)
    return Div(
        Div(id=div_id, style="width:100%;min-height:600px;"),
        Script(f"Plotly.newPlot('{div_id}', {fig_json}.data, {fig_json}.layout, {{responsive:true}});"),
    )

def build_df(provider=None):
    rows = fetch_lots(provider)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df.columns = ["date", "author", "start_price", "end_price", "year", "decade", "tech", "category", "dimension", "auction_provider"]
    # Clean data
    df = df[df["start_price"] > 0].copy()
    df["year"] = df["year"].where(df["year"] > 1800)
    df["decade"] = df["decade"].where(df["decade"] > 1800)
    df["tech"] = df["tech"].fillna("Unknown")
    df["category"] = df["category"].fillna("Unknown")
    df["overbid_%"] = (df["end_price"] - df["start_price"]) / df["start_price"] * 100
    df["art_work_age"] = df["date"] - df["year"]
    return df

def make_treemap(df):
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
    return fig

def make_age_scatter(df):
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
    return fig

def make_dim_scatter(df):
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
    return fig

PROVIDERS = [("all", "All Providers"), ("allee", "Allee Galerii"), ("haus", "Haus")]

@rt("/")
def get(provider: str = "all"):
    prov = None if provider == "all" else provider
    df = build_df(prov)

    nav_links = [
        A(label, href=f"/?provider={key}",
          cls="contrast" if key != provider else "",
          style="margin-right:1rem;font-weight:" + ("bold" if key == provider else "normal"))
        for key, label in PROVIDERS
    ]

    if df.empty:
        return Title("Kanvas.AI Art Index"), Main(
            H1("Kanvas.AI Art Index"),
            Nav(*nav_links),
            P("No data found. Run: python db.py"),
            cls="container",
        )

    return Title("Kanvas.AI Art Index"), Main(
        H1("Kanvas.AI Art Index"),
        Nav(*nav_links),
        Section(
            H3("Best selling artists — total sales by overbidding %"),
            plotly_div(make_treemap(df), "treemap"),
        ),
        Section(
            H3("Is older art more expensive? Age vs. price"),
            plotly_div(make_age_scatter(df), "age_scatter"),
        ),
        Section(
            H3("Are larger works more expensive? Dimensions vs. price"),
            plotly_div(make_dim_scatter(df), "dim_scatter"),
        ),
        Footer(
            P("Author: Julian Kaljuvee"),
            P(f"Source: Art auction data • {len(df)} lots"),
        ),
        cls="container",
    )

serve()
