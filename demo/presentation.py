"""Small, escaped presentation components shared by dashboard pages."""

from html import escape
import math
import streamlit as st
from demo.charts import short_number

ICONS = {
    "money": '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M3 9h18"/><path d="M7 15h3"/>',
    "users": '<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6M18 15a5 5 0 0 1 3 5"/>',
    "chart": '<path d="M4 20V10M10 20V4M16 20v-8M22 20H2"/>',
    "check": '<rect x="3" y="3" width="18" height="18" rx="4"/><path d="m7 12 3 3 7-7"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "book": '<path d="M3 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-3H3zm18 0h-6a3 3 0 0 0-3 3v14a4 4 0 0 1 4-3h5z"/>',
}


def icon(name):
    return (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        + ICONS.get(name, ICONS["chart"])
        + "</svg>"
    )


def ratio(numerator, denominator):
    numerator, denominator = float(numerator), float(denominator)
    if not math.isfinite(numerator) or not math.isfinite(denominator) or denominator <= 0:
        return None
    return 100 * numerator / denominator


def csv_bytes(frame):
    """Preserve numeric values while neutralizing spreadsheet formulas in source text."""

    def safe(value):
        if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
            return "'" + value
        return value

    return frame.map(safe).to_csv(index=False).encode("utf-8-sig")


def percent(value):
    return "—" if value is None or not math.isfinite(value) else f"{value:.1f}" + "%"


def change(current, previous, points=False):
    if previous is None:
        return None
    result = (
        current - previous if points else (100 * (current / previous - 1) if previous else None)
    )
    if result is None or not math.isfinite(result):
        return None
    return ("+" if result > 0 else "") + f"{result:.1f}" + (" pp" if points else "%")


def metrics(items):
    cards = []
    for item in items:
        delta = item.get("delta")
        note = item.get("note", "Selected period")
        badge = '<span class="delta">' + escape(delta) + "</span>" if delta else ""
        cards.append(
            '<div class="metric-card"><div class="metric-top"><span class="metric-label">'
            + escape(item["label"])
            + '</span><span class="metric-icon">'
            + icon(item.get("icon", "chart"))
            + "</span></div>"
            + '<div class="metric-value">'
            + escape(str(item["value"]))
            + '</div><div class="metric-bottom">'
            + badge
            + "<span>"
            + escape(note)
            + "</span></div></div>"
        )
    st.markdown('<div class="metrics-grid">' + "".join(cards) + "</div>", unsafe_allow_html=True)


def card_title(title, subtitle=None, tag=None):
    st.markdown(
        '<div class="card-title"><h3>'
        + escape(title)
        + "</h3>"
        + ('<span class="card-tag">' + escape(tag) + "</span>" if tag else "")
        + "</div>"
        + ('<div class="card-subtitle">' + escape(subtitle) + "</div>" if subtitle else ""),
        unsafe_allow_html=True,
    )


def empty(message="There are no observations in the selected scope."):
    st.markdown(
        '<div class="empty-state"><b>No observations to display</b>' + escape(message) + "</div>",
        unsafe_allow_html=True,
    )


def progress(stages):
    largest = max([float(value) for _, value in stages] + [1])
    rows = []
    for label, value in stages:
        rows.append(
            '<div class="progress-row"><span class="progress-label">'
            + escape(label)
            + '</span><div class="progress-track"><div class="progress-fill" style="width:'
            + str(100 * value / largest)
            + '%"></div></div><span class="progress-value">'
            + escape(short_number(value))
            + "</span></div>"
        )
    st.markdown("".join(rows), unsafe_allow_html=True)
