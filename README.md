# 🔎 네이버 마켓 인사이트 EDA 대시보드

[NAVER API HUB](https://api.ncloud-docs.com/docs/naver-api-hub-overview) 공식 문서를 기준으로
검색어별 **뉴스 · 블로그 · 웹문서 · 이미지 · 지식iN · 지역 · 카페글 · 백과사전** 검색 결과와
**검색어 트렌드(데이터랩)** 를 수집해 기초 EDA를 보여주는 Streamlit 대시보드입니다.

## 1. 준비

### 가상환경 (uv)

```bash
uv venv --python 3.12
uv pip install -r requirements.txt      # 또는: uv pip install -e .
```

### 인증 정보 (.env)

```bash
cp config/.env.example .env
```

`.env` 를 열어 네이버 클라우드 플랫폼에서 발급받은 키를 채웁니다.

```dotenv
NAVER_AUTH_MODE=hub
NAVER_CLIENT_ID=발급받은_Client_ID
NAVER_CLIENT_SECRET=발급받은_Client_Secret
```

| 모드 | 요청 헤더 | 기본 엔드포인트 |
| --- | --- | --- |
| `hub` (기본) | `X-NCP-APIGW-API-KEY-ID` / `X-NCP-APIGW-API-KEY` | `https://naverapihub.apigw.ntruss.com` |
| `legacy` | `X-Naver-Client-Id` / `X-Naver-Client-Secret` | `https://openapi.naver.com` |

기존 네이버 개발자센터 키를 쓰려면 `NAVER_AUTH_MODE=legacy` 로 바꾸고
`NAVER_LEGACY_CLIENT_ID` / `NAVER_LEGACY_CLIENT_SECRET` 을 채우면 됩니다.

## 2. 실행

```bash
uv run streamlit run app/main.py
```

브라우저에서 http://localhost:8501 접속.

### Streamlit Community Cloud 배포

`.env` 는 저장소에 올라가지 않으므로(`.gitignore` 제외) 배포본은 인증 정보를
**Secrets** 로 받는다. 이 설정을 하지 않으면 앱이 "인증 정보가 없습니다" 안내만
띄운다.

1. share.streamlit.io 에서 이 저장소를 연결하고 **Main file path** 를
   `app/main.py` 로 지정한다.
2. 앱 화면 우측 상단 **⋮ → Settings → Secrets** 를 연다.
3. [`config/secrets.toml.example`](config/secrets.toml.example) 내용을 붙여넣고
   실제 키로 바꾼 뒤 저장한다.

```toml
NAVER_AUTH_MODE = "hub"
NAVER_CLIENT_ID = "발급받은_Client_ID"
NAVER_CLIENT_SECRET = "발급받은_Client_Secret"
```

저장하면 앱이 자동으로 재시작된다. 로컬에 `.env` 가 있으면 `.env` 가 우선하므로
기존 로컬 실행 방식은 그대로 쓰면 된다.

> 네이버 클라우드 플랫폼 API 키는 요청 수에 따라 과금될 수 있다. 공개 배포 시
> 접근 범위를 확인할 것.

## 3. 사용법

1. 사이드바 **① 검색어** 에 쉼표로 구분해 입력 — 예: `탕후루, 마라탕, 두바이초콜릿`
2. **② 기간** 선택 — 검색어 트렌드 조회 구간이자 뉴스·블로그 결과 필터 구간
3. **③ 수집 채널** 체크, **④ 수집 옵션** 으로 문서 수·정렬 지정
4. **⑤ 검색어 트렌드** 에서 구간 단위·기기·성별·연령대 지정
5. **🔍 수집 실행**

### 탭 구성

| 탭 | 내용 |
| --- | --- |
| 개요 | 검색어 수·수집 문서 수·전체 검색 건수, 검색어별 노출 점유율(SOV) |
| 채널 분포 | 채널 × 검색어 검색량 막대·히트맵 |
| 발행량 추이 | 뉴스·블로그 발행일 기준 일/주/월 시계열 |
| 검색어 트렌드 | 데이터랩 상대 검색량 추이, 기초 통계, 전·후반 변화율, 분포 |
| 연관어·출처 | 제목·요약 토큰 빈도, 주요 도메인·블로거·카페 |
| 원문 | 필터링 가능한 원문 테이블 + CSV 다운로드 |

## 4. 폴더 구조

```
naver-search-dashboard/
├── app/                    # Streamlit 진입점
│   └── main.py
├── src/naver_insight/      # 라이브러리 코드
│   ├── settings.py         # .env 로딩 + 엔드포인트 명세
│   ├── client.py           # API 호출 (검색 / 트렌드)
│   ├── collector.py        # 다중 검색어·채널 수집 오케스트레이션
│   └── eda.py              # 정규화 및 기초 통계
├── config/.env.example     # 환경변수 템플릿
├── assets/styles/          # 대시보드 CSS
├── data/cache/             # 수집 스냅샷 저장 위치
├── docs/                   # API 사양 정리
└── scripts/                # 실행 스크립트
```

### 문서

- [`docs/api-reference.md`](docs/api-reference.md) — 네이버 API 사양 정리
- [`docs/dashboard-playbook.md`](docs/dashboard-playbook.md) — EDA부터 배포까지의
  제작 순서와 규칙. 다음 프로젝트를 같은 방식으로 만들 때의 기준 문서.

## 5. 공식 문서 기준 제약

- 검색 API: `display` 1~100, `start` 1~1000 — **지역(local)은 `display` 최대 5, `start` 1**
- 검색어 트렌드: `POST /search-trend/v1/search` — 한 요청당 **최대 5개 그룹**, 그룹당 **검색어 20개**
- 호출 한도: 네이버 검색 월 775,000건 / 데이터랩 각 월 50,000건, API Key당 50 RPS
- 발행일(`pubDate`, `postdate`)은 **뉴스·블로그만** 제공 → 기간 필터도 이 두 채널에만 실제 적용

자세한 사양은 [docs/api-reference.md](docs/api-reference.md) 참고.
