# NAVER API HUB 사양 정리

출처
- [NAVER API HUB 개요 (API 가이드)](https://api.ncloud-docs.com/docs/naver-api-hub-overview)
- [NAVER API HUB 개요 (사용 가이드)](https://guide.ncloud-docs.com/docs/apihub-overview)
- [NAVER API HUB 이관 가이드](https://guide.ncloud-docs.com/docs/apihub-migration)

## 인증

| 항목 | 값 |
| --- | --- |
| Base URL | `https://naverapihub.apigw.ntruss.com` |
| 헤더 | `X-NCP-APIGW-API-KEY-ID: {Client ID}` |
| 헤더 | `X-NCP-APIGW-API-KEY: {Client Secret}` |
| 헤더(POST) | `Content-Type: application/json` — 검색어 트렌드·쇼핑인사이트 |

이관 시 변경점: `openapi.naver.com/v1/search/news.json` → `naverapihub.apigw.ntruss.com/search/v1/news`,
`X-Naver-Client-Id` → `X-NCP-APIGW-API-KEY-ID`, `X-Naver-Client-Secret` → `X-NCP-APIGW-API-KEY`.

## 검색 API (GET)

| 채널 | 경로 | display | start | sort |
| --- | --- | --- | --- | --- |
| 뉴스 | `/search/v1/news` | 1~100 (기본 10) | 1~1000 | `sim`, `date` |
| 블로그 | `/search/v1/blog` | 1~100 | 1~1000 | `sim`, `date` |
| 웹문서 | `/search/v1/webkr` | 1~100 | 1~1000 | — |
| 이미지 | `/search/v1/image` | 1~100 | 1~1000 | `sim`, `date` (+ `filter`: all/large/medium/small) |
| 지식iN | `/search/v1/kin` | 1~100 | 1~1000 | `sim`, `date`, `point` |
| 지역 | `/search/v1/local` | **1~5** (기본 1) | **1** | `random`, `comment` |
| 카페글 | `/search/v1/cafearticle` | 1~100 | 1~1000 | `sim`, `date` |
| 백과사전 | `/search/v1/encyc` | 1~100 | 1~1000 | — |

공통 요청 파라미터: `query`(필수, UTF-8 인코딩), `display`, `start`, `format`(json/xml, 기본 json).

공통 응답: `lastBuildDate`, `total`, `start`, `display`, `items[]`.
`items[].title` / `description` 은 검색어 일치 부분을 `<b>` 태그로 감싼다 → 대시보드에서 태그 제거 후 사용.

### 채널별 주요 응답 필드

| 채널 | 고유 필드 |
| --- | --- |
| 뉴스 | `originallink`, `pubDate` (RFC 1123) |
| 블로그 | `bloggername`, `bloggerlink`, `postdate` (YYYYMMDD) |
| 이미지 | `thumbnail`, `sizeheight`, `sizewidth` |
| 지역 | `category`, `telephone`(빈 값), `address`, `roadAddress`, `mapx`, `mapy` (WGS84) |
| 카페글 | `cafename`, `cafeurl` |
| 백과사전 | `thumbnail` |

→ 발행일이 있는 채널은 **뉴스·블로그뿐**이므로, 대시보드의 기간 필터도 이 두 채널에만 실제로 적용된다.

## 검색어 트렌드 (POST `/search-trend/v1/search`)

전체 URL: `https://naverapihub.apigw.ntruss.com/search-trend/v1/search`
경로 접두사가 하이픈이 들어간 `search-trend` 다. `datalab`/`searchtrend` 로 부르면 404(errorCode 300).

요청 본문

```json
{
  "startDate": "2025-06-01",
  "endDate": "2025-09-01",
  "timeUnit": "date",
  "keywordGroups": [
    { "groupName": "탕후루", "keywords": ["탕후루"] }
  ],
  "device": "mo",
  "ages": ["3", "4"],
  "gender": "f"
}
```

| 필드 | 값 |
| --- | --- |
| `timeUnit` | `date`(일간) / `week`(주간) / `month`(월간) |
| `keywordGroups` | 최대 5그룹, 그룹당 검색어 최대 20개 |
| `device` | 생략(전체) / `pc` / `mo` |
| `gender` | 생략(전체) / `m` / `f` |
| `ages` | `1`(0~12) `2`(13~18) `3`(19~24) `4`(25~29) `5`(30~34) `6`(35~39) `7`(40~44) `8`(45~49) `9`(50~54) `10`(55~59) `11`(60~) |

응답: `results[].title`, `results[].keywords`, `results[].data[].period`, `results[].data[].ratio`.
`ratio` 는 조회 기간 내 최대 검색량을 100으로 둔 **상대값**이며 절대 검색 횟수가 아니다.

## 호출 한도

| 항목 | 한도 |
| --- | --- |
| 네이버 검색 | 월 775,000건 |
| 데이터랩(검색어 트렌드 / 쇼핑인사이트) | 각 월 50,000건 |
| API Key | 50 RPS |
| 플랫폼 전체 | 검색 1,000 RPS / 데이터랩 500 RPS |

초과 시 `429 Too Many Requests`.
