"""Consistent interactive figures for the learning warehouse portal."""

import pandas as pd
import math
import plotly.graph_objects as go

BLUE = "#4F63D9"
INK = "#18253D"
MUTED = "#617089"
CATEGORY_COLORS = dict(
    Data=BLUE, Programming="#C89A38", Business="#DB794B", Design="#8C9651", Language="#C47799"
)
METHOD_LABELS = dict(bank_transfer="Bank transfer", card="Card", wallet="Wallet")


def tick_indices(length):
    if length == 0:
        return []
    if length == 1:
        return [0]
    count = min(length, 4)
    return [round(index * (length - 1) / (count - 1)) for index in range(count)]


def short_number(value, digits=1):
    number = float(value)
    if not math.isfinite(number):
        return "—"
    for divisor, suffix in [(1e9, "B"), (1e6, "M"), (1e3, "K")]:
        if abs(number) >= divisor:
            return f"{number / divisor:,.{digits}f}" + " " + suffix
    return f"{number:,.0f}"


def base(height=300):
    figure = go.Figure()
    figure.update_layout(
        template="plotly_white",
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, Arial, sans-serif", size=12, color=MUTED),
        margin=dict(l=8, r=24, t=22, b=12),
        hoverlabel=dict(bgcolor=INK, font=dict(color="white", size=13), bordercolor=INK),
        legend=dict(orientation="h", y=1.16, x=0, font=dict(size=12, color=INK)),
        hovermode="closest",
        bargap=0.36,
    )
    figure.update_xaxes(showgrid=False, zeroline=False, showline=False, automargin=True)
    figure.update_yaxes(gridcolor="#EDF0F5", zeroline=False, showline=False, automargin=True)
    return figure


def revenue_chart(frame, grain="Month"):
    if frame.empty:
        return base(310)
    rows = frame.copy()
    rows["month"] = pd.to_datetime(rows["month"])
    rows = rows.sort_values("month").reset_index(drop=True)
    if grain == "Quarter":
        rows["month"] = rows["month"].dt.to_period("Q").dt.start_time
        rows = rows.groupby("month", as_index=False)[["net_vnd", "gross_vnd"]].sum()
    figure = base(310)
    unit = 1e9 if rows.gross_vnd.max() >= 1e9 else 1e6
    suffix = "B VND" if unit == 1e9 else "M VND"
    labels = (
        rows.month.dt.strftime("%b %Y")
        if grain == "Month"
        else rows.month.map(lambda d: f"Q{d.quarter}/{d.year}")
    )
    for column, name, color, dash in [
        ("gross_vnd", "Original value", "#A7B2CA", "dot"),
        ("net_vnd", "Net revenue", BLUE, "solid"),
    ]:
        figure.add_trace(
            go.Scatter(
                x=rows.month,
                y=rows[column] / unit,
                name=name,
                mode="lines+markers",
                line=dict(color=color, width=2.6, dash=dash),
                marker=dict(size=5, color=color),
                fill="tozeroy" if column == "net_vnd" else None,
                fillcolor="rgba(79,99,217,.065)" if column == "net_vnd" else None,
                customdata=list(
                    zip(labels, rows[column].map(lambda n: short_number(n, 2) + " VND"))
                ),
                hovertemplate="<b>%{customdata[0]}</b><br>"
                + name
                + ": %{customdata[1]}<extra></extra>",
            )
        )
    # Calendar-spaced labels, including both endpoints. Missing observations stay missing.
    indices = tick_indices(len(rows))
    figure.update_xaxes(
        tickmode="array", tickvals=rows.month.iloc[indices], ticktext=labels.iloc[indices]
    )
    figure.update_yaxes(rangemode="tozero", ticksuffix=" " + suffix, nticks=5)
    figure.update_layout(hovermode="x unified", legend=dict(y=1.2))
    return figure


def ranked_chart(frame, value, label, kind="money", height=None, color=BLUE):
    if frame.empty:
        return base(height or 255)
    rows = frame.copy()
    figure = base(height or max(255, len(rows) * 29 + 45))
    labels = rows[label].astype(str)
    values = rows[value].astype(float)
    if kind == "money":
        divisor = 1e9 if values.max() >= 1e9 else 1e6
        plotted = values / divisor
        suffix = " B VND" if divisor == 1e9 else " M VND"
        text = [f"{n:.2f}" + suffix for n in plotted]
        lower = min(float(plotted.min()) * 1.25, 0)
        limit = max(float(plotted.max()) * 1.32, 0.01)
    elif kind == "percent":
        plotted, suffix, lower, limit = values, "%", 0, 100
        text = [f"{n:.1f}" + "%" for n in values]
    else:
        plotted, suffix = values, ""
        lower = min(float(values.min()) * 1.25, 0)
        limit = max(float(values.max()) * 1.28, 1)
        text = [short_number(n) for n in values]
    short = labels.map(lambda name: name if len(name) <= 26 else name[:24] + "…")
    positions = [str(index) for index in range(len(rows))]
    figure.add_trace(
        go.Bar(
            x=plotted,
            y=positions,
            orientation="h",
            marker=dict(color=color, line_width=0),
            text=text,
            textposition="outside",
            textfont=dict(size=12, color=INK),
            cliponaxis=False,
            customdata=list(zip(labels, text)),
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>",
        )
    )
    figure.update_yaxes(
        type="category",
        autorange="reversed",
        showgrid=False,
        tickfont=dict(color=INK, size=12),
        tickmode="array",
        tickvals=positions,
        ticktext=short,
    )
    figure.update_xaxes(
        range=[lower, limit], showgrid=True, gridcolor="#EDF0F5", nticks=4, ticksuffix=suffix
    )
    figure.update_layout(
        showlegend=False, margin=dict(l=8, r=72 if kind == "percent" else 34, t=8, b=8)
    )
    return figure


def enrollment_chart(frame):
    if frame.empty:
        return base(255)
    rows = frame.copy()
    rows["month"] = pd.to_datetime(rows["month"])
    figure = base(255)
    figure.add_trace(
        go.Bar(
            x=rows.month,
            y=rows.enrollments,
            name="Enrollments",
            marker_color=BLUE,
            customdata=rows.month.dt.strftime("%b %Y"),
            hovertemplate="<b>%{customdata}</b><br>Enrollments: %{y:,.0f}<extra></extra>",
        )
    )
    indices = tick_indices(len(rows))
    figure.update_xaxes(
        tickmode="array",
        tickvals=rows.month.iloc[indices],
        ticktext=rows.month.iloc[indices].dt.strftime("%b %Y"),
    )
    figure.update_yaxes(rangemode="tozero", nticks=4)
    return figure


def payment_mix(frame):
    labels = frame.method_name.map(lambda name: METHOD_LABELS.get(name, name))
    figure = base(255)
    colors = {"bank_transfer": BLUE, "card": "#B3BFEF", "wallet": "#DAA447"}
    figure.add_trace(
        go.Pie(
            labels=labels,
            values=frame.payments,
            hole=0.76,
            sort=False,
            marker=dict(
                colors=[colors.get(name, "#8693A9") for name in frame.method_name],
                line=dict(color="white", width=3),
            ),
            textinfo="none",
            hovertemplate="<b>%{label}</b><br>%{value:,.0f} payments · %{percent}<extra></extra>",
        )
    )
    figure.update_layout(
        showlegend=True,
        legend=dict(orientation="h", y=-0.02, x=0.5, xanchor="center", font=dict(size=11)),
        annotations=[
            dict(
                text="<b>"
                + short_number(frame.payments.sum())
                + '</b><br><span style="font-size:11px;color:#7D899D">payments</span>',
                x=0.5,
                y=0.52,
                showarrow=False,
                font=dict(size=24, color=INK),
            )
        ],
        margin=dict(l=4, r=4, t=4, b=32),
    )
    return figure


def revenue_bridge(frame):
    gross, discount, refund, net = (
        int(frame[column].sum())
        for column in ["gross_vnd", "discount_vnd", "refund_vnd", "net_vnd"]
    )
    unit = 1e9 if gross >= 1e9 else 1e6
    figure = base(280)
    figure.add_trace(
        go.Waterfall(
            x=["Original value", "Discounts", "Refunds", "Net revenue"],
            y=[gross / unit, -discount / unit, -refund / unit, 0],
            measure=["absolute", "relative", "relative", "total"],
            text=[short_number(n, 2) + " VND" for n in [gross, -discount, -refund, net]],
            textposition="outside",
            textfont=dict(color=INK, size=11),
            connector=dict(line=dict(color="#CBD3E1", width=1)),
            increasing=dict(marker=dict(color="#D4A243")),
            decreasing=dict(marker=dict(color="#A0AED8")),
            totals=dict(marker=dict(color=BLUE)),
            hovertemplate="%{x}: %{text}<extra></extra>",
        )
    )
    figure.update_yaxes(
        ticksuffix=" B VND" if unit == 1e9 else " M VND", rangemode="tozero", nticks=4
    )
    figure.update_layout(showlegend=False)
    return figure
