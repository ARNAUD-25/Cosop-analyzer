import pandas as pd
import plotly.graph_objects as go
import streamlit as st

PALETTE = [
    "#2d6a4f", "#52b788", "#95d5b2", "#b7e4c7",
    "#f4a261", "#e76f51", "#264653", "#a8dadc",
]

LAYOUT = dict(
    font_family="sans-serif",
    font_color="#1a1a1a",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(t=40, b=20, l=10, r=10),
)


def chart_by_category(partners: list[dict]):
    """Donut chart: Category distribution"""
    if not partners:
        st.info("No data to display.")
        return

    df = pd.DataFrame(partners)
    counts = df["category"].value_counts().reset_index()
    counts.columns = ["Category", "Count"]

    fig = go.Figure(go.Pie(
        labels=counts["Category"],
        values=counts["Count"],
        hole=0.52,
        marker=dict(
            colors=PALETTE[:len(counts)],
            line=dict(color="#ffffff", width=2),
        ),
        textinfo="label+percent",
        textfont_size=12,
        hovertemplate="<b>%{label}</b><br>%{value} partners (%{percent})<extra></extra>",
    ))

    fig.add_annotation(
        text=f"<b>{len(partners)}</b><br>partners",
        x=0.5, y=0.5,
        font=dict(size=16, color="#1a1a1a"),
        showarrow=False,
    )

    fig.update_layout(
        title=dict(text="Partners by Category", font_size=14, x=0, xanchor="left"),
        showlegend=True,
        legend=dict(font_size=11, bgcolor="rgba(0,0,0,0)"),
        height=360,
        **LAYOUT,
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def chart_by_mentions(partners: list[dict]):
    """Horizontal bar chart"""
    if not partners:
        st.info("No data to display.")
        return

    df = pd.DataFrame(partners)
    top = (
        df[df["mention_count"] > 0]
        .nlargest(len(df), "mention_count")[["name", "category", "mention_count"]]
        .sort_values("mention_count", ascending=True)
        .reset_index(drop=True)
    )

    categories = top["category"].unique().tolist()
    color_map = {cat: PALETTE[i % len(PALETTE)] for i, cat in enumerate(categories)}

    fig = go.Figure()
    for cat in categories:
        subset = top[top["category"] == cat]
        short_names = subset["name"].apply(lambda n: n if len(n) <= 40 else n[:38] + "...")
        fig.add_trace(go.Bar(
            x=subset["mention_count"],
            y=short_names,
            orientation="h",
            name=cat,
            marker=dict(color=color_map[cat], line=dict(width=0)),
            hovertemplate="<b>%{y}</b><br>%{x} mentions<extra></extra>",
        ))

    fig.update_layout(
        title=dict(text="Partner Mentions in the PDF", font_size=14, x=0, xanchor="left"),
        barmode="group",
        yaxis=dict(tickfont=dict(size=11), gridcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor="#e8e8e8", title="Mentions", tickfont=dict(size=11)),
        legend=dict(font_size=11, bgcolor="rgba(0,0,0,0)"),
        height=max(320, len(top) * 25),
        **LAYOUT,
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

