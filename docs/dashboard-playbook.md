# 대시보드 제작 플레이북 — EDA에서 배포까지

`naver-search-dashboard` 를 만들면서 확정한 작업 순서와 규칙을 다음 프로젝트에
그대로 재사용하기 위해 정리한 문서다. 스택은 **uv + marimo(EDA) + Streamlit(대시보드)
+ GitHub + Streamlit Community Cloud(배포)** 로 고정한다.

각 단계마다 "무엇을" 뿐 아니라 "왜 그렇게" 를 함께 적었다. 규칙을 깨야 할 때
무엇을 포기하는지 알고 깨기 위해서다.

---

## 0. 전체 흐름

```
데이터 확보 → EDA(노트북) → 라이브러리화(src/) → 대시보드(app/) → 배포(Cloud)
    수집 코드      탐색·검증       재사용 가능 모듈     화면 조립      공개
```

핵심 원칙 하나: **노트북은 버리는 것, 모듈은 남기는 것.**
EDA에서 얻은 결론은 노트북에 남기고, 결론을 만든 *코드* 는 `src/` 로 승격시킨다.
대시보드는 노트북을 복붙하는 게 아니라 승격된 모듈을 호출한다.

| 단계 | 산출물 | 소요 비중 |
|---|---|---|
| 0. 골격 | `pyproject.toml`, `requirements.txt`, 폴더 | 5% |
| 1. EDA | `notebooks/*.py`, 검증된 가설 | 35% |
| 2. 라이브러리화 | `src/<pkg>/*.py` | 25% |
| 3. 대시보드 | `app/main.py`, `app/views/*` | 25% |
| 4. 배포 | Secrets, Cloud 설정 | 10% |

---

## 1단계: 프로젝트 골격 (uv)

### 환경

```bash
uv venv --python 3.12
uv pip install -r requirements.txt
```

파이썬 버전은 **3.12로 고정** 한다. Streamlit Community Cloud가 고를 수 있는
버전과 맞춰야 하고, C 확장 패키지(`kiwipiepy`, `scipy` 등)는 버전별 휠이 없으면
배포 단계에서 설치가 통째로 실패한다. 로컬에서는 되는데 배포에서 깨지는 사고의
절반이 여기서 나온다.

### 의존성을 두 군데 쓰는 이유

| 파일 | 쓰는 주체 | 역할 |
|---|---|---|
| `pyproject.toml` | 로컬 개발, `uv pip install -e .` | 패키지 메타데이터 + `src` 레이아웃 선언 |
| `requirements.txt` | **Streamlit Cloud** | Cloud는 이 파일만 읽는다 |

Cloud는 `pyproject.toml` 을 보지 않으므로 **의존성을 추가하면 반드시 양쪽 모두**
갱신한다. 한쪽만 고치면 로컬은 멀쩡하고 배포만 죽는다.

### 폴더 구조

```
<project>/
├── notebooks/              # marimo EDA 노트북 (.py)
├── app/                    # Streamlit 진입점
│   ├── main.py             # 사이드바 + 라우팅 + 상태 관리만
│   └── views/              # 탭/섹션별 렌더링 함수
├── src/<package>/          # 재사용 라이브러리 (화면 코드 없음)
│   ├── settings.py         # 설정·인증·상수
│   ├── client.py           # 외부 API 호출
│   ├── collector.py        # 수집 오케스트레이션 + 스냅샷
│   ├── eda.py              # 정규화·기초 통계
│   ├── features.py         # 파생 변수(형태소, 키워드 등)
│   ├── stats.py            # 검정·상관 등 통계
│   └── theme.py            # 그래프 스타일 일관성
├── config/.env.example          # 로컬 환경변수 템플릿
├── config/secrets.toml.example  # 배포용 Secrets 템플릿
├── assets/styles/          # CSS
├── data/cache/             # 수집 스냅샷 (.gitkeep만 커밋)
├── docs/                   # API 사양·설계 메모
└── scripts/                # 실행 스크립트
```

**`src/` 안에는 `import streamlit` 이 없어야 한다.** 이 경계가 무너지면 노트북에서
모듈을 못 쓰고, 테스트도 못 하고, 나중에 CLI나 배치로 재사용할 수도 없다.
(예외: `settings.py` 가 배포용 Secrets를 읽을 때만 함수 안에서 지연 import 한다.
3단계 참고.)

### 초기 커밋 전에 `.gitignore` 부터

```gitignore
.venv/
.env
__pycache__/
*.py[cod]
.streamlit/secrets.toml
data/cache/*
!data/cache/.gitkeep
*.egg-info/
```

`.env` 와 `.streamlit/secrets.toml` 을 **첫 커밋 전에** 넣어야 한다. 한 번 커밋된
키는 이후 커밋에서 지워도 히스토리에 남으므로, 그때는 키 재발급 외에 방법이 없다.

---

## 2단계: EDA (marimo)

### 왜 marimo인가

- 노트북이 **순수 `.py` 파일** 로 저장된다 → git diff가 읽히고, 리뷰와 병합이 된다.
  (`.ipynb` 는 JSON에 출력까지 섞여 diff가 사실상 불가능하다.)
- **반응형 실행** — 셀을 고치면 의존하는 셀이 자동으로 다시 돈다. 실행 순서가
  꼬여서 생기는 "노트북에서는 됐는데" 부류의 거짓 결론이 줄어든다.
- 같은 파일을 `marimo run` 으로 앱처럼 띄울 수 있어, EDA와 시연 사이 간극이 작다.

```bash
uv pip install marimo
uv run marimo edit notebooks/01_explore.py                          # 편집
uv run marimo run  notebooks/01_explore.py                          # 앱처럼 실행
uv run marimo export html notebooks/01_explore.py -o docs/eda.html  # 공유용
```

> 이 저장소는 EDA를 Streamlit 안에서 직접 돌렸고 marimo는 쓰지 않았다. 위 명령은
> 다음 프로젝트에 적용할 안이며, 도입할 때 첫 실행으로 한 번 확인할 것.

### 노트북에서 할 일 / 하지 말 일

| 할 일 | 하지 말 일 |
|---|---|
| 분포·결측·이상치 눈으로 확인 | 최종 시각화 스타일 다듬기 |
| 가설 세우고 통계로 검정 | 예쁜 레이아웃 만들기 |
| API 응답 스키마 파악 | 재사용할 함수를 노트북 안에만 두기 |
| **대시보드에 넣을 지표 확정** | 노트북을 그대로 대시보드로 만들기 |

EDA의 진짜 산출물은 그래프가 아니라 **"대시보드에 무엇을 올릴지에 대한 결정"**
이다. 이 단계를 끝낼 때 다음 세 가지가 문장으로 적혀 있어야 한다.

1. 이 대시보드가 답하는 질문 3~5개
2. 각 질문에 대응하는 지표와 시각화 형태
3. 그 지표를 만들려면 어떤 수집·가공이 필요한가

### 승격 규칙

노트북에서 **두 번 이상 쓴 코드는 즉시 `src/` 로 옮긴다.** 옮긴 뒤 노트북은
`from <package> import ...` 로 다시 부른다. 이걸 미루면 마지막에 노트북과
대시보드가 서로 다른 계산을 하고 있는 상태로 끝난다.

---

## 3단계: 라이브러리화 (`src/`)

### 모듈 경계

| 모듈 | 책임 | 넣지 말 것 |
|---|---|---|
| `settings.py` | 인증 정보, 엔드포인트 명세, 상수 | 로직 |
| `client.py` | HTTP 호출, 에러 변환, 재시도 | 데이터 가공 |
| `collector.py` | 여러 호출 묶기, 스냅샷 저장/로드 | 화면 |
| `eda.py` | 응답 → DataFrame 정규화, 기초 통계 | API 지식 |
| `features.py` | 파생 변수 | 시각화 |
| `stats.py` | 검정·상관 | 시각화 |
| `theme.py` | 색·폰트·축 스타일 | 데이터 |

`client` 가 가공하지 않고 `eda` 가 API를 모르는 것이 핵심이다. 그래야 API가
바뀌면 `client` 만, 지표가 바뀌면 `eda` 만 고치면 된다.

무거운 선택적 의존성은 **실패해도 앱이 죽지 않게** 감싼다. 형태소 분석기처럼
설치가 까다로운 패키지는 대체 경로를 둔다.

```python
@functools.lru_cache(maxsize=1)
def _kiwi():
    try:
        from kiwipiepy import Kiwi
        return Kiwi()
    except Exception:      # 설치 실패 시 정규식 토큰화로 자동 강등
        return None
```

### 설정은 로컬과 배포 두 경로를 모두 지원한다

이번 프로젝트에서 가장 크게 시간을 쓴 지점이다. `.env` 는 `.gitignore` 로
제외되므로 **배포본에는 존재하지 않는다.** `.env` 만 읽는 코드는 로컬에서만
동작한다. 처음부터 두 경로를 다 지원해야 한다.

```python
ENV_KEYS = ("API_CLIENT_ID", "API_CLIENT_SECRET", ...)

def load_secrets() -> None:
    """Streamlit Secrets 를 환경 변수로 반영 (배포 경로)."""
    try:
        import streamlit as st       # src 는 streamlit 에 의존하지 않으므로 지연 import
    except ModuleNotFoundError:
        return
    try:
        secrets = st.secrets         # secrets.toml 이 없으면 접근 자체가 예외
    except Exception:
        return
    for key in ENV_KEYS:
        ...                          # 있으면 os.environ 에 반영

def load_env() -> None:
    """Secrets → config/.env → 루트 .env 순으로 덮어쓴다."""
    load_secrets()
    for candidate in (PROJECT_ROOT / "config" / ".env", PROJECT_ROOT / ".env"):
        ...
```

우선순위는 **Secrets → `.env`** 로, 뒤가 이긴다. 로컬에 `.env` 가 있으면 그게
최종이라 개발 경험이 바뀌지 않고, 배포 환경에는 `.env` 가 없으니 Secrets가
그대로 쓰인다.

### 값이 없을 때 "왜 없는지" 를 화면에서 알려준다

"인증 정보가 없습니다" 만 띄우면 미저장인지, 키 이름 오타인지, 템플릿 문구를
그대로 붙여넣었는지 구분할 수 없다. 진단 함수를 하나 두고 경고 아래 접이식
패널로 보여준다. **비밀값 자체는 절대 출력하지 않고 길이와 상태만** 보여준다.

```python
def diagnose() -> dict:
    """Secrets 최상위 키 목록 / 감지된 .env 파일 /
    키별 상태: 없음 | 예시 문구 그대로 | 설정됨(N자)"""
```

---

## 4단계: 대시보드 (Streamlit)

### 진입점 구조

```python
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "app"))

from <package> import eda
from views import overview as overview_view
```

`src` 를 `sys.path` 에 넣으면 Cloud에서 패키지를 설치하지 않아도 import가 된다.
(Cloud는 `requirements.txt` 만 설치하고 프로젝트 자체는 설치하지 않는다.)

### `main.py` 와 `views/` 의 분담

- `main.py`: 사이드바 입력, 수집 실행, `st.session_state` 관리, 탭 라우팅
- `views/*.py`: 받은 DataFrame을 그리기만. **수집·API 호출 금지**

`main.py` 가 400줄을 넘기 시작하면 뷰를 쪼갠다. 뷰가 데이터를 직접 가져오기
시작하면 같은 데이터를 두 번 수집하게 되고 캐시가 무력화된다.

### 상태와 캐시

```python
@st.cache_data(show_spinner=False, ttl=1800)
def _cached_collect(keywords: tuple, endpoints: tuple, ...):
    ...
```

- `@st.cache_data` 인자는 **해시 가능해야** 한다 → `list` 대신 `tuple`,
  `dict` 대신 `tuple(sorted(d.items()))` 로 넘긴다.
- 외부 API 호출에는 `ttl` 을 반드시 준다. 무한 캐시는 "새로고침해도 안 바뀜" 의 원인.
- 수집 결과는 `st.session_state` 에 넣는다. 위젯을 건드릴 때마다 스크립트가
  처음부터 다시 도는데, 세션에 없으면 매번 다시 수집한다.
- 수집 결과를 `data/cache/` 에 **스냅샷** 으로 저장해 두면 API 없이도 화면을
  띄울 수 있다. 시연·발표 때 네트워크나 쿼터 사고를 막아준다.

### 시각화 일관성

색·폰트·축 스타일은 `theme.py` 에 모아 `style_fig(fig)` 한 번으로 적용한다.
그래프마다 색을 직접 지정하면 20개쯤에서 반드시 어긋난다.

```python
PRIMARY = "#03C75A"
CATEGORICAL = [...]     # 범주형 팔레트
SEQUENTIAL = [...]      # 연속형 팔레트

def style_fig(fig, height=360, legend=True): ...
```

`.streamlit/config.toml` 에 테마를 고정해 앱 전체 톤을 맞춘다. 라이트/다크를
모두 지원하려면 두 배로 검증해야 하므로, 기간이 짧으면 한쪽에만 커밋한다.

```toml
[theme]
base = "light"
primaryColor = "#03C75A"
backgroundColor = "#FFFFFF"
```

---

## 5단계: GitHub

```bash
git init
git add .gitignore              # 항상 먼저
git add .
git commit -m "feat: 초기 구현"
git remote add origin https://github.com/<user>/<repo>.git
git push -u origin main
```

커밋 전 확인:

- [ ] `git status` 에 `.env` / `secrets.toml` 이 **안 보이는가**
- [ ] `config/.env.example` 에 실제 키가 아니라 플레이스홀더만 있는가
- [ ] `git config user.name` / `user.email` 이 설정돼 있는가
      (없으면 첫 커밋에서 `Author identity unknown` 으로 막힌다)

---

## 6단계: Streamlit Community Cloud 배포

### 배포 폼

| 항목 | 값 |
|---|---|
| Repository | `<user>/<repo>` |
| Branch | `main` |
| Main file path | `app/main.py` |
| App URL | 읽기 쉬운 이름으로 변경 권장 |

### Advanced settings — 배포 누르기 전에 연다

1. **Python version**: `3.12` (로컬과 동일하게)
2. **Secrets**: TOML 형식으로 붙여넣기. 배포 후에 넣으면 재시작을 한 번 더 기다린다.

```toml
API_AUTH_MODE = "hub"
API_CLIENT_ID = "실제_ID"
API_CLIENT_SECRET = "실제_SECRET"
```

- 섹션 헤더 없이 최상위 키, 값은 큰따옴표
- 템플릿의 `여기에_...` 를 **반드시 실제 값으로** 교체
- 반영까지 1분 정도 걸린다

### 배포 후 함정: 모듈 캐시

**저장소를 push해도 이미 import된 모듈은 갱신되지 않는다.** 런타임은 엔트리포인트
스크립트만 다시 실행하고, `src/` 의 모듈은 `sys.modules` 에 있는 옛 버전을 계속
쓴다. 그래서 `src/` 에 함수를 새로 추가하고 `app/main.py` 에서 import하면
**앱 전체가 `ImportError` 로 죽는다.**

대응 두 가지:

1. **Manage app → ⋮ → Reboot app** — 프로세스를 새로 띄워 캐시를 비운다. 근본 해결.
2. 부가 기능은 방어적으로 import해서 앱이 통째로 죽지 않게 한다.

```python
try:
    from <package>.settings import diagnose
except ImportError:      # 런타임에 옛 모듈이 캐시된 경우
    diagnose = None
```

`src/` 에 **새 이름을 추가한 커밋을 배포할 때는 습관적으로 Reboot** 한다.

### 공개 범위와 비용

API 키를 Secrets에 넣고 앱을 공개하면 **누구나 내 키로 API를 호출** 하게 된다.
과금되는 API라면 앱 접근 권한을 제한하거나 배포용 키를 따로 발급한다.
스크린샷에 키가 찍힌 채로 공유했다면 재발급이 답이다.

---

## 배포 전 최종 체크리스트

**저장소**
- [ ] `.env`, `secrets.toml` 이 커밋되지 않았다
- [ ] `requirements.txt` 가 `pyproject.toml` 의존성과 일치한다
- [ ] `data/cache/` 는 `.gitkeep` 만 올라갔다

**코드**
- [ ] 인증 정보를 Secrets와 `.env` 양쪽에서 읽는다
- [ ] 인증 실패 시 원인을 구분할 수 있는 안내가 있다
- [ ] `src/` 에 `import streamlit` 이 (지연 import 외에) 없다
- [ ] 외부 호출에 `ttl` 있는 캐시가 걸려 있다
- [ ] 수집 실패·빈 결과일 때 화면이 깨지지 않는다

**배포**
- [ ] Python 버전이 로컬과 같다
- [ ] Secrets를 저장하고 1분 기다렸다
- [ ] 새 모듈 이름을 추가했다면 Reboot 했다
- [ ] 공개 범위와 API 과금을 확인했다

---

## 이번 프로젝트에서 실제로 겪은 함정

| 증상 | 원인 | 대응 |
|---|---|---|
| `Author identity unknown` | git user 미설정 | `git config --local user.name` / `user.email` |
| 배포본만 "인증 정보 없음" | `.env` 는 배포되지 않음 | Secrets 경로 추가 |
| Secrets 넣었는데 그대로 | 템플릿 문구를 그대로 붙여넣음 | 진단 패널로 상태 구분 |
| 갑자기 `ImportError` | 런타임의 옛 모듈 캐시 | Reboot + 방어적 import |
| (예상) 설치 단계 실패 | C 확장 패키지 휠 부재 | Python 3.12 고정 |

---

## 다음 프로젝트 시작 순서 요약

```bash
uv venv --python 3.12
uv pip install streamlit pandas plotly python-dotenv marimo
mkdir -p notebooks app/views src/<pkg> config assets/styles data/cache docs scripts
# .gitignore 를 먼저 작성한 뒤
git init && git add .gitignore && git add . && git commit -m "chore: 프로젝트 골격"
uv run marimo edit notebooks/01_explore.py      # EDA 시작
```
