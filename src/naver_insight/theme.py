"""네이버 BI 기반 색상 팔레트와 Plotly 차트 스타일.

팔레트는 dataviz 검증 스크립트(validate_palette.js)로 light 모드에서 검증했다.
  Lightness band  PASS (7색 모두 L 0.43~0.77)
  Chroma floor    PASS (7색 모두 C >= 0.10)
  CVD separation  PASS (최악 인접쌍 #0D9488↔#E11D48 ΔE 10.2 deutan)
  Normal-vision   PASS (최악 인접쌍 ΔE 21.3)
  Contrast        WARN (#03C75A 2.19 등) → 모든 탭에 범례와 표를 함께 두어 해소
"""

from __future__ import annotations

# 네이버 BI 그린을 1번 슬롯에 고정한다. 순서는 절대 섞거나 순환시키지 않는다.
NAVER_GREEN = "#03C75A"

CATEGORICAL = [
    NAVER_GREEN,  # 네이버 그린
    "#1C64F2",  # 블루
    "#F76707",  # 오렌지
    "#9333EA",  # 퍼플
    "#CA8A04",  # 골드
    "#E11D48",  # 크림슨
    "#0D9488",  # 틸
]

# 크기(magnitude)용 단일 색상 램프 — 네이버 그린 한 가지 색의 명도 변화.
SEQUENTIAL = [
    [0.0, "#F2FCF6"],
    [0.2, "#C9F2DC"],
    [0.4, "#84DFAE"],
    [0.6, "#2FC978"],
    [0.8, "#04A548"],
    [1.0, "#016B30"],
]

# 표면·잉크 토큰. 텍스트는 절대 시리즈 색을 입지 않는다.
SURFACE = "#FFFFFF"
INK = "#111827"
INK_MUTED = "#6B7280"
GRID = "#EDF0F2"

FONT = "Pretendard, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif"


def style_fig(fig, height: int = 360, legend: bool = True):
    """모든 차트에 공통 레이아웃을 입힌다 — 옅은 그리드, 얌전한 축, 통일된 서체."""
    fig.update_layout(
        height=height,
        margin=dict(t=24, b=12, l=8, r=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=12, color=INK),
        showlegend=legend,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            title_text="",
            font=dict(color=INK_MUTED),
        ),
        hoverlabel=dict(
            bgcolor=SURFACE,
            bordercolor=GRID,
            font=dict(family=FONT, size=12, color=INK),
        ),
    )
    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        linecolor=GRID,
        tickfont=dict(color=INK_MUTED),
        title_font=dict(color=INK_MUTED, size=11),
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        linecolor="rgba(0,0,0,0)",
        tickfont=dict(color=INK_MUTED),
        title_font=dict(color=INK_MUTED, size=11),
    )
    return fig


def style_bars(fig, gap_ring: bool = True):
    """막대는 얇게, 데이터 끝은 둥글게, 인접 막대 사이에는 표면색 간격을 둔다."""
    fig.update_traces(
        marker_line_color=SURFACE if gap_ring else None,
        marker_line_width=2 if gap_ring else 0,
        selector=dict(type="bar"),
    )
    fig.update_layout(bargap=0.35, bargroupgap=0.12)
    return fig


def style_lines(fig):
    """선은 2px, 마커는 8px 이상."""
    fig.update_traces(
        line=dict(width=2),
        marker=dict(size=8, line=dict(width=2, color=SURFACE)),
        selector=dict(type="scatter"),
    )
    return fig
