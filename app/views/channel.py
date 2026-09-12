"""채널별 심층 EDA 화면.

공통 4종 그래프 + 5종 표를 모든 채널에 보장하고,
채널 고유 필드가 있는 경우 전용 분석을 더한다(합계 그래프·표 각 5개 이상).
파이차트는 쓰지 않는다.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from naver_insight import features, stats

from .common import (
    bar,
    box,
    download,
    hbar,
    heatmap,
    histogram,
    line,
    render_crosstab,
    scatter,
    section,
    show_table,
)

WEEKDAY_ORDER = features.WEEKDAYS


def render(df: pd.DataFrame, endpoint: str, label: str) -> None:
    """한 채널의 심층 EDA 페이지."""
    if df.empty:
        st.info(f"{label} 채널에 수집된 문서가 없습니다. 사이드바에서 채널을 켜고 수집해 주세요.")
        return

    work = features.add_common_features(df)
    if endpoint == "image":
        work = features.add_image_features(work)

    _headline(work, label)
    _common_graphs(work, endpoint, label)
    _channel_graphs(work, endpoint, label)
    _common_tables(work, endpoint, label)
    _channel_tables(work, endpoint, label)

    section("원문")
    cols = ["keyword", "rank", "title", "source", "published_at", "link"]
    show_table(work[[c for c in cols if c in work.columns]])
    download(work, "이 채널 CSV 다운로드", f"naver_{endpoint}.csv", key=f"dl_{endpoint}")


# ------------------------------------------------------------------ 요약 지표
def _headline(df: pd.DataFrame, label: str) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("수집 문서", f"{len(df):,}건")
    c2.metric("검색어", f"{df['keyword'].nunique()}개")
    c3.metric("고유 출처", f"{df['source'].nunique():,}개")
    c4.metric("링크 중복률", f"{stats.duplicate_rate(df)}%")
    st.caption(
        f"{label} 채널의 수집 표본 기준입니다. "
        "API가 보고하는 전체 검색 건수(total)는 채널마다 정확도가 달라 여기서는 표본만 셉니다."
    )


# ------------------------------------------------------------------ 공통 그래프
def _common_graphs(df: pd.DataFrame, endpoint: str, label: str) -> None:
    c1, c2 = st.columns(2)

    with c1:
        section("① 랭크 구간별 요약 길이 분포", "상위 노출 문서가 더 길거나 짧은지 봅니다.")
        st.plotly_chart(
            box(df, x="랭크구간", y="요약길이", color="keyword",
                labels={"랭크구간": "검색 랭크 구간", "요약길이": "요약 글자 수"}),
            width='stretch', key=f"{endpoint}_g1",
        )

    with c2:
        section("② 주요 출처 상위 15", "담론이 어디에서 생산되는지 봅니다.")
        top = (
            df[df["source"] != "(미상)"]
            .groupby(["source", "keyword"], as_index=False).size()
            .rename(columns={"size": "문서수"})
            .sort_values("문서수", ascending=False).head(15)
        )
        if top.empty:
            st.info("출처 정보가 없습니다.")
        else:
            st.plotly_chart(
                hbar(top, x="문서수", y="source", color="keyword",
                     labels={"source": "출처", "문서수": "문서 수"}),
                width='stretch', key=f"{endpoint}_g2",
            )

    c3, c4 = st.columns(2)

    with c3:
        section("③ 연관 명사 상위 20", "형태소 분석으로 명사만 추출했습니다.")
        nouns = features.noun_counts(df, limit=20)
        if nouns.empty:
            st.info("추출된 명사가 없습니다.")
        else:
            st.plotly_chart(
                hbar(nouns, x="빈도", y="명사", labels={"명사": "", "빈도": "빈도"}),
                width='stretch', key=f"{endpoint}_g3",
            )

    with c4:
        section("④ 검색어 × 랭크 구간 평균 요약 길이", "피봇테이블을 히트맵으로 본 것입니다.")
        pivot = stats.pivot_table(df, "keyword", "랭크구간", "요약길이", "mean", margins=False)
        if pivot.empty:
            st.info("피봇할 데이터가 없습니다.")
        else:
            st.plotly_chart(
                heatmap(pivot, labels=dict(x="랭크 구간", y="검색어", color="평균 글자 수")),
                width='stretch', key=f"{endpoint}_g4",
            )


# ------------------------------------------------------------- 채널 고유 그래프
def _channel_graphs(df: pd.DataFrame, endpoint: str, label: str) -> None:
    if endpoint in ("news", "blog"):
        _time_graphs(df, endpoint)
    elif endpoint == "image":
        _image_graphs(df, endpoint)
    elif endpoint == "webkr":
        _web_graphs(df, endpoint)
    elif endpoint == "kin":
        _kin_graphs(df, endpoint)
    elif endpoint == "cafearticle":
        _cafe_graphs(df, endpoint)


def _time_graphs(df: pd.DataFrame, endpoint: str) -> None:
    dated = df[df["published_at"].notna()]
    if dated.empty:
        st.info("발행일이 있는 문서가 없습니다.")
        return

    section("⑤ 발행량 추이", "이 채널만 발행일을 제공합니다.")
    freq_label = st.radio("집계 단위", ["일", "주", "월"], horizontal=True, key=f"{endpoint}_freq")
    freq = {"일": "D", "주": "W", "월": "ME"}[freq_label]
    ts = (
        dated.assign(구간=dated["published_at"].dt.to_period(freq).dt.start_time)
        .groupby(["구간", "keyword"], as_index=False).size()
        .rename(columns={"size": "문서수"})
    )
    st.plotly_chart(
        line(ts, x="구간", y="문서수", color="keyword",
             labels={"구간": "발행 시점", "문서수": "문서 수"}),
        width='stretch', key=f"{endpoint}_g5",
    )

    section("⑥ 요일 × 시간대 발행 히트맵", "언제 콘텐츠가 만들어지는지 봅니다.")
    matrix = (
        dated.pivot_table(index="요일", columns="시간대", values="title", aggfunc="count")
        .reindex(WEEKDAY_ORDER).fillna(0)
    )
    if matrix.empty:
        st.info("집계할 데이터가 없습니다.")
    else:
        st.plotly_chart(
            heatmap(matrix, labels=dict(x="시(0~23)", y="요일", color="문서 수")),
            width='stretch', key=f"{endpoint}_g6",
        )


def _image_graphs(df: pd.DataFrame, endpoint: str) -> None:
    sized = df[df["가로"].notna() & df["세로"].notna()]
    if sized.empty:
        st.info("크기 정보가 있는 이미지가 없습니다.")
        return

    section("⑤ 해상도 산점도", "이 채널은 유일하게 연속형 변수(가로·세로)를 제공합니다.")
    st.plotly_chart(
        scatter(sized, x="가로", y="세로", color="keyword",
                hover_data=["title"], labels={"가로": "가로(px)", "세로": "세로(px)"}),
        width='stretch', key=f"{endpoint}_g5",
    )

    c1, c2 = st.columns(2)
    with c1:
        section("⑥ 종횡비 분포", "1.0이면 정사각형입니다.")
        st.plotly_chart(
            histogram(sized[sized["종횡비"] < 4], x="종횡비", color="keyword", nbins=40,
                      labels={"종횡비": "가로/세로"}),
            width='stretch', key=f"{endpoint}_g6",
        )
    with c2:
        section("⑦ 검색어별 화소수 분포")
        st.plotly_chart(
            box(sized, x="keyword", y="화소수(만)", color="keyword",
                labels={"keyword": "검색어"}),
            width='stretch', key=f"{endpoint}_g7",
        )


def _web_graphs(df: pd.DataFrame, endpoint: str) -> None:
    work = df.copy()
    work["TLD"] = work["도메인"].apply(features.tld_of)

    c1, c2 = st.columns(2)
    with c1:
        section("⑤ 도메인 최상위 구간(TLD) 분포", "출처의 성격을 대략 나눕니다.")
        counts = (
            work[work["TLD"] != "(미상)"]
            .groupby(["TLD", "keyword"], as_index=False).size()
            .rename(columns={"size": "문서수"}).sort_values("문서수", ascending=False).head(15)
        )
        st.plotly_chart(
            bar(counts, x="TLD", y="문서수", color="keyword"),
            width='stretch', key=f"{endpoint}_g5",
        )
    with c2:
        section("⑥ 제목 길이 × 요약 길이", "날짜가 없는 채널이라 텍스트 구조로 성격을 봅니다.")
        st.plotly_chart(
            scatter(work, x="제목길이", y="요약길이", color="keyword", hover_data=["title"]),
            width='stretch', key=f"{endpoint}_g6",
        )


def _kin_graphs(df: pd.DataFrame, endpoint: str) -> None:
    work = df.copy()
    patterns = {
        "어떻게/방법": r"어떻게|방법|하는법|하나요",
        "무엇/뜻": r"무엇|뭐|뜻|의미|이란",
        "왜/이유": r"왜|이유|때문",
        "어디": r"어디|장소|위치",
        "추천/비교": r"추천|비교|차이|나은",
        "가격/비용": r"가격|얼마|비용|값",
    }
    text = work["text"].fillna("")
    rows = []
    for name, pat in patterns.items():
        hit = text.str.contains(pat, regex=True)
        for kw, part in work[hit].groupby("keyword"):
            rows.append({"질문유형": name, "keyword": kw, "문서수": len(part)})
    qtype = pd.DataFrame(rows)

    c1, c2 = st.columns(2)
    with c1:
        section("⑤ 질문 유형 분포", "제목·요약의 표현 패턴으로 분류했습니다.")
        if qtype.empty:
            st.info("분류된 질문이 없습니다.")
        else:
            st.plotly_chart(
                bar(qtype, x="질문유형", y="문서수", color="keyword"),
                width='stretch', key=f"{endpoint}_g5",
            )
    with c2:
        section("⑥ 질문 길이 분포")
        st.plotly_chart(
            histogram(work, x="요약길이", color="keyword", nbins=40,
                      labels={"요약길이": "요약 글자 수"}),
            width='stretch', key=f"{endpoint}_g6",
        )
    st.session_state[f"_{endpoint}_qtype"] = qtype


def _cafe_graphs(df: pd.DataFrame, endpoint: str) -> None:
    c1, c2 = st.columns(2)
    with c1:
        section("⑤ 카페별 문서 수 상위 15")
        counts = (
            df.groupby(["source", "keyword"], as_index=False).size()
            .rename(columns={"size": "문서수"}).sort_values("문서수", ascending=False).head(15)
        )
        st.plotly_chart(
            hbar(counts, x="문서수", y="source", color="keyword",
                 labels={"source": "카페"}),
            width='stretch', key=f"{endpoint}_g5",
        )
    with c2:
        section("⑥ 제목 길이 분포")
        st.plotly_chart(
            histogram(df, x="제목길이", color="keyword", nbins=30,
                      labels={"제목길이": "제목 글자 수"}),
            width='stretch', key=f"{endpoint}_g6",
        )


# -------------------------------------------------------------------- 공통 표
def _common_tables(df: pd.DataFrame, endpoint: str, label: str) -> None:
    st.divider()

    section("표 1 — 기술통계", "검색어별 텍스트 길이의 중심·산포·사분위입니다.")
    show_table(
        stats.describe_numeric(df, ["제목길이", "요약길이", "제목단어수"], by="keyword")
    )

    render_crosstab(
        stats.crosstab_with_chi2(df, "keyword", "source", top_n=8),
        "표 2 — 교차표: 검색어 × 출처 (카이제곱 독립성 검정)",
    )

    section("표 3 — 피봇테이블: 검색어 × 랭크 구간", "값은 평균 요약 길이입니다.")
    show_table(stats.pivot_table(df, "keyword", "랭크구간", "요약길이", "mean"))

    section("표 4 — 출처 집중도", "상위 5개 출처가 차지하는 비중입니다.")
    show_table(stats.concentration(df, "source", top_n=5))

    section("표 5 — 검색어별 문서 수와 고유 출처 수")
    summary = (
        df.groupby("keyword")
        .agg(
            문서수=("title", "count"),
            고유출처수=("source", "nunique"),
            평균제목길이=("제목길이", "mean"),
            평균요약길이=("요약길이", "mean"),
        )
        .round(1)
        .reset_index()
    )
    show_table(summary)


# --------------------------------------------------------------- 채널 고유 표
def _channel_tables(df: pd.DataFrame, endpoint: str, label: str) -> None:
    if endpoint in ("news", "blog"):
        dated = df[df["published_at"].notna()]
        if dated.empty:
            return
        section("표 6 — 요일별 발행량 교차표")
        table = pd.crosstab(dated["요일"], dated["keyword"], margins=True, margins_name="합계")
        show_table(table.reindex([*WEEKDAY_ORDER, "합계"]).dropna(how="all"))

        section("표 7 — 월별 피봇테이블", "값은 문서 수입니다.")
        show_table(
            stats.pivot_table(dated, "연월", "keyword", "title", aggfunc="count")
        )

    elif endpoint == "image":
        sized = df[df["가로"].notna()]
        if sized.empty:
            return
        section("표 6 — 이미지 크기 기술통계")
        show_table(stats.describe_numeric(sized, ["가로", "세로", "화소수(만)", "종횡비"],
                                          by="keyword"))
        render_crosstab(
            stats.crosstab_with_chi2(sized, "keyword", "방향", top_n=3),
            "표 7 — 교차표: 검색어 × 이미지 방향 (카이제곱)",
        )

    elif endpoint == "webkr":
        work = df.copy()
        work["TLD"] = work["도메인"].apply(features.tld_of)
        render_crosstab(
            stats.crosstab_with_chi2(work, "keyword", "TLD", top_n=8),
            "표 6 — 교차표: 검색어 × TLD (카이제곱)",
        )
        section("표 7 — 도메인별 문서 수 상위 20")
        show_table(
            work.groupby("도메인", as_index=False).size()
            .rename(columns={"size": "문서수"})
            .sort_values("문서수", ascending=False).head(20)
        )

    elif endpoint == "kin":
        qtype = st.session_state.get(f"_{endpoint}_qtype", pd.DataFrame())
        if not qtype.empty:
            section("표 6 — 질문 유형 × 검색어 피봇")
            show_table(
                qtype.pivot_table(index="질문유형", columns="keyword", values="문서수",
                                  aggfunc="sum", margins=True, margins_name="합계").fillna(0)
            )

    elif endpoint == "cafearticle":
        section("표 6 — 카페별 문서 수와 검색어 커버리지")
        show_table(
            df.groupby("source")
            .agg(문서수=("title", "count"), 검색어수=("keyword", "nunique"))
            .sort_values("문서수", ascending=False)
            .head(20)
            .reset_index()
        )


# --------------------------------------------------------- 경량 뷰 (지역·백과)
def render_local(df: pd.DataFrame) -> None:
    """지역은 API 상한이 5건이라 통계 대신 지도와 목록으로 보여준다."""
    st.warning(
        "지역 검색 API는 검색어당 **최대 5건**만 반환합니다(공식 문서). "
        "표본이 작아 분포·검정 대신 위치와 원문 중심으로 표시합니다."
    )
    if df.empty:
        st.info("수집된 지역 결과가 없습니다.")
        return

    work = features.add_local_features(df)
    geo = work[work["lat"].notna() & work["lon"].notna()]

    c1, c2 = st.columns(4)[:2]
    c1.metric("업체 수", f"{len(work)}곳")
    c2.metric("검색어", f"{work['keyword'].nunique()}개")

    if not geo.empty:
        section("위치", "mapx·mapy는 WGS84 좌표에 10⁷을 곱한 값이라 나눠서 표시합니다.")
        st.map(geo[["lat", "lon"]], size=60)

    section("업체 목록")
    show_table(work[["keyword", "title", "대분류", "분류", "주소", "link"]])

    section("시도 · 대분류 집계")
    c1, c2 = st.columns(2)
    with c1:
        show_table(work.groupby(["시도"], as_index=False).size()
                   .rename(columns={"size": "업체수"}))
    with c2:
        show_table(work.groupby(["대분류"], as_index=False).size()
                   .rename(columns={"size": "업체수"}))


def render_encyc(df: pd.DataFrame) -> None:
    """백과사전은 표본이 수십 건 수준이라 정의 원문 중심으로 보여준다."""
    st.warning(
        "백과사전은 검색어당 결과가 수십 건 수준으로 적습니다. "
        "분포 통계 대신 표제어와 정의 원문을 그대로 보여줍니다."
    )
    if df.empty:
        st.info("수집된 백과사전 결과가 없습니다.")
        return

    work = features.add_common_features(df)
    c1, c2 = st.columns(4)[:2]
    c1.metric("표제어 수", f"{len(work)}건")
    c2.metric("검색어", f"{work['keyword'].nunique()}개")

    for keyword, part in work.groupby("keyword"):
        section(f"{keyword} — 표제어 {len(part)}건")
        for _, row in part.head(10).iterrows():
            with st.container(border=True):
                st.markdown(f"**[{row['title']}]({row['link']})**")
                st.write(row["description"][:400] or "(설명 없음)")

    section("표제어 목록")
    show_table(work[["keyword", "rank", "title", "제목길이", "요약길이", "link"]])
