"""종합 탭 — 채널을 가로지르는 비교."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from naver_insight import eda, features, stats

from .common import bar, download, heatmap, hbar, render_crosstab, section, show_table


def render(df: pd.DataFrame, opts: dict) -> None:
    if df.empty:
        st.warning("수집된 문서가 없습니다.")
        return

    _headline(df)
    _sov(df)
    _channel_distribution(df)
    _cross_keyword(df)
    _tables(df)
    download(df, "전체 수집 결과 CSV", "naver_all.csv", key="dl_all")


def _headline(df: pd.DataFrame) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("검색어", f"{df['keyword'].nunique()}개")
    c2.metric("수집 문서", f"{len(df):,}건")
    c3.metric("채널", f"{df['channel'].nunique()}개")
    c4.metric("링크 중복률", f"{stats.duplicate_rate(df)}%")


def _sov(df: pd.DataFrame) -> None:
    section(
        "채널별 노출 점유율 (SOV)",
        "채널마다 모집단 규모가 3~5자릿수 차이 나서 합산하지 않고 채널 안에서만 비율을 냅니다.",
    )
    sov = eda.share_of_voice(df)
    c1, c2 = st.columns([1.4, 1])
    with c1:
        st.plotly_chart(
            bar(sov, x="channel", y="점유율(%)", color="keyword", barmode="group",
                labels={"channel": "채널"}),
            width='stretch', key="ov_sov",
        )
    with c2:
        matrix = eda.sov_matrix(df)
        if matrix.empty:
            st.info("점유율을 계산할 데이터가 없습니다.")
        else:
            st.plotly_chart(
                heatmap(matrix, text=".1f",
                        labels=dict(x="검색어", y="채널", color="점유율(%)")),
                width='stretch', key="ov_sovmat",
            )
    st.caption(
        "전체검색건수(total)는 채널마다 정확도가 다릅니다 — 지역 채널은 total이 3이어도 "
        "실제 5건이 반환됩니다. 채널 간 절대 비교보다 채널 내 상대 비교로 읽어주세요."
    )


def _channel_distribution(df: pd.DataFrame) -> None:
    section("채널 × 검색어 수집량")
    summary = eda.channel_summary(df)
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            bar(summary, x="channel", y="전체검색건수", color="keyword", barmode="group",
                log_y=True, labels={"channel": "채널", "전체검색건수": "전체 검색 건수(로그)"}),
            width='stretch', key="ov_dist",
        )
    with c2:
        pivot = summary.pivot_table(index="channel", columns="keyword",
                                    values="수집건수", aggfunc="sum").fillna(0)
        if not pivot.empty:
            st.plotly_chart(
                heatmap(pivot, labels=dict(x="검색어", y="채널", color="수집 건수")),
                width='stretch', key="ov_distmat",
            )


def _cross_keyword(df: pd.DataFrame) -> None:
    """검색어끼리 비교하는 지표 — 연관어 겹침과 채널 간 문서 중복."""
    section(
        "검색어 간 연관어 겹침 (자카드)",
        "같은 맥락에서 언급되는 검색어일수록 1에 가깝습니다.",
    )
    token_sets = {
        str(kw): features.noun_set(part, limit=100)
        for kw, part in df.groupby("keyword")
    }
    overlap = stats.keyword_overlap(token_sets)
    c1, c2 = st.columns([1, 1.2])
    with c1:
        if overlap.empty:
            st.info("검색어가 2개 이상일 때 계산됩니다.")
        else:
            st.plotly_chart(
                heatmap(overlap.astype(float), text=".2f", height=320,
                        labels=dict(x="검색어", y="검색어", color="자카드")),
                width='stretch', key="ov_jaccard",
            )
    with c2:
        section("채널 간 중복 문서", "같은 링크가 여러 채널·검색어에 걸쳐 잡힌 경우입니다.")
        dup = stats.duplicate_report(df)
        if dup.empty:
            st.info("중복된 링크가 없습니다.")
        else:
            show_table(dup.head(20))


def _tables(df: pd.DataFrame) -> None:
    st.divider()
    work = features.add_common_features(df)

    section("표 1 — 채널별 기술통계")
    show_table(stats.describe_numeric(work, ["제목길이", "요약길이"], by="channel"))

    render_crosstab(
        stats.crosstab_with_chi2(work, "keyword", "channel", top_n=8),
        "표 2 — 교차표: 검색어 × 채널 (카이제곱 독립성 검정)",
    )

    section("표 3 — 피봇테이블: 채널 × 검색어", "값은 평균 요약 길이입니다.")
    show_table(stats.pivot_table(work, "channel", "keyword", "요약길이", "mean"))

    section("표 4 — 채널별 요약")
    show_table(eda.channel_summary(df))

    section("표 5 — 출처 집중도 (전체 채널)")
    show_table(stats.concentration(work, "source", top_n=5))
