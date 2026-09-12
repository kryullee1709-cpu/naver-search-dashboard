"""화면 전반에서 재사용하는 렌더 도우미."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from naver_insight import stats
from naver_insight.theme import CATEGORICAL, SEQUENTIAL, style_bars, style_fig, style_lines

PALETTE = CATEGORICAL


def section(title: str, caption: str | None = None) -> None:
    st.markdown(f"##### {title}")
    if caption:
        st.caption(caption)


def show_table(df: pd.DataFrame, empty_msg: str = "표시할 데이터가 없습니다.") -> None:
    if df is None or df.empty:
        st.info(empty_msg)
        return
    st.dataframe(df, width='stretch')


def bar(df: pd.DataFrame, x: str, y: str, color: str | None = None, **kw):
    fig = px.bar(df, x=x, y=y, color=color, color_discrete_sequence=PALETTE, **kw)
    return style_bars(style_fig(fig, height=kw.pop("height", 340), legend=color is not None))


def hbar(df: pd.DataFrame, x: str, y: str, color: str | None = None, height: int = 420, **kw):
    fig = px.bar(
        df, x=x, y=y, color=color, orientation="h",
        color_discrete_sequence=PALETTE, **kw,
    )
    fig.update_yaxes(categoryorder="total ascending")
    return style_bars(style_fig(fig, height=height, legend=color is not None))


def line(df: pd.DataFrame, x: str, y: str, color: str | None = None, height: int = 340, **kw):
    fig = px.line(df, x=x, y=y, color=color, markers=True,
                  color_discrete_sequence=PALETTE, **kw)
    return style_lines(style_fig(fig, height=height, legend=color is not None))


def heatmap(matrix: pd.DataFrame, height: int = 340, text: str | bool = ".0f", **kw):
    fig = px.imshow(matrix, aspect="auto", color_continuous_scale=SEQUENTIAL,
                    text_auto=text, **kw)
    return style_fig(fig, height=height, legend=False)


def box(df: pd.DataFrame, x: str, y: str, color: str | None = None, height: int = 340, **kw):
    fig = px.box(df, x=x, y=y, color=color, color_discrete_sequence=PALETTE, **kw)
    return style_fig(fig, height=height, legend=color is not None)


def histogram(df: pd.DataFrame, x: str, color: str | None = None, height: int = 340, **kw):
    fig = px.histogram(df, x=x, color=color, barmode="overlay", opacity=0.75,
                       color_discrete_sequence=PALETTE, **kw)
    return style_fig(fig, height=height, legend=color is not None)


def scatter(df: pd.DataFrame, x: str, y: str, color: str | None = None,
            height: int = 380, **kw):
    fig = px.scatter(df, x=x, y=y, color=color, color_discrete_sequence=PALETTE,
                     opacity=0.75, **kw)
    fig.update_traces(marker=dict(size=9, line=dict(width=1, color="#FFFFFF")))
    return style_fig(fig, height=height, legend=color is not None)


def render_crosstab(result: stats.CrossTabResult, title: str) -> None:
    """교차표 + 카이제곱 검정 결과를 한 덩어리로 표시한다."""
    section(title)
    if result.table.empty:
        st.info(result.note)
        return
    st.dataframe(result.table, width='stretch')
    if result.chi2 is None:
        st.caption(result.note)
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("χ²", f"{result.chi2:,.2f}")
    c2.metric("자유도", f"{result.dof}")
    c3.metric("p-value", f"{result.p_value:.4f}")
    c4.metric("Cramér's V", f"{result.cramers_v}" if result.cramers_v is not None else "—")
    (st.success if result.significant else st.info)(result.note)
    with st.expander("기대빈도 표 보기"):
        st.dataframe(result.expected, width='stretch')


def download(df: pd.DataFrame, label: str, filename: str, key: str) -> None:
    if df is None or df.empty:
        return
    export = df.drop(columns=[c for c in ("raw",) if c in df.columns])
    st.download_button(
        label,
        data=export.to_csv(index=False).encode("utf-8-sig"),
        file_name=filename,
        mime="text/csv",
        key=key,
    )
