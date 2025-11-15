# GG Chatbot

Gemma(Ollama) 기반 텔레그램 챗봇 MVP 레포입니다. 텍스트 입력을 받아 로컬에 띄운 Ollama Gemma 모델로 답변을 생성하고, 이를 텔레그램 사용자에게 전달합니다. 코드 구조와 인프라 아티팩트는 이후 GG 추천 챗봇으로 확장할 수 있도록 모듈 단위로 나누었습니다.

## 구성 요소
- `bot/`: 텔레그램 `Application` 초기화, 메시지 핸들러, GemmaClient 의존성 주입
- `config/`: `.env` → `Settings` 로딩 (추후 ConfigMap/Secrets 로 교체 가능)
- `infra/`: Python 이미지 기반 Dockerfile, 로컬 개발용 docker-compose
- `requirements.txt`: python-telegram-bot, httpx, python-dotenv 등 런타임 의존성 정의
- `Makefile`: 설치/실행/도커 명령 단축어

```
.
├── bot/
│   ├── bot.py
│   ├── gemma_client.py
│   ├── handlers.py
│   └── logger.py
├── config/
│   ├── __init__.py
│   └── settings.py
├── infra/
│   ├── Dockerfile
│   └── docker-compose.yml
├── requirements.txt
├── .env.example
├── Makefile
└── README.md
```

## 요구 사항
- Python 3.11 이상
- Telegram Bot API 토큰
- Ollama 가 설치되어 있고 Gemma 모델이 로컬에서 서빙 중 (`http://localhost:11434` 기본값)  
  또는 `docker compose` 로 `ollama/ollama` 컨테이너를 함께 실행

## 로컬 개발 환경 설정

```bash
# 1) 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1

# 2) 의존성 설치
make install  # 또는 pip install -r requirements.txt

# 3) 환경 변수 설정
cp .env.example .env
# .env 파일에 TELEGRAM_BOT_TOKEN, GEMMA_BASE_URL 등을 입력하세요.
```

## 로컬 실행 방법

1. Ollama 에서 Gemma 모델을 다운로드하고 백그라운드로 띄웁니다.
   ```bash
   ollama pull gemma:2b
   ollama serve   # 필요 시
   ```
2. `.env` 파일에 `TELEGRAM_BOT_TOKEN` 등을 정의합니다.
3. 텔레그램 봇 실행

```bash
make run
# 또는
python bot/bot.py
```

텔레그램에서 봇에게 메시지를 보내면 Gemma 가 응답을 생성해 전달합니다.

## Docker / Compose 실행

로컬에 Python 이 없어도 docker-compose 로 Ollama + Bot 을 동시에 띄울 수 있습니다.

```bash
cp .env.example .env                    # TELEGRAM_BOT_TOKEN 입력
docker compose -f infra/docker-compose.yml up --build
```

- `ollama` 서비스: 공식 `ollama/ollama` 이미지를 사용하며 11434 포트 노출
- `bot` 서비스: `infra/Dockerfile` 로 빌드한 이미지, `GEMMA_BASE_URL=http://ollama:11434`
- 종료 시 `docker compose -f infra/docker-compose.yml down -v` 로 볼륨 정리

컨테이너 이미지만 필요할 경우:

```bash
make docker-build
docker run --env-file .env --network host gg-chatbot
```

## 환경 변수
| 변수명 | 설명 | 기본값 |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | BotFather 에서 발급받은 텔레그램 봇 토큰 | (필수) |
| `GEMMA_BASE_URL` | Ollama Gemma API 엔드포인트 | `http://localhost:11434` |
| `GEMMA_MODEL` | 사용할 Gemma 모델 이름 | `gemma:2b` |
| `REQUEST_TIMEOUT` | Ollama API 호출 타임아웃(초) | `30` |

## Makefile 단축 명령어
| 명령어 | 설명 |
| --- | --- |
| `make install` | pip 업그레이드 및 필수 패키지 설치 |
| `make run` | 텔레그램 봇 실행 |
| `make lint` | `python -m compileall` 로 구문 오류 확인 |
| `make docker-build` | `infra/Dockerfile` 로 애플리케이션 이미지 빌드 |
| `make docker-up` | docker-compose 로 Ollama + Bot 실행 |
| `make docker-down` | docker-compose 스택 종료 및 볼륨 정리 |

## 다음 단계 로드맵
1. 에러 핸들링/로깅 고도화 및 관측성 확장
2. 최소 단위 테스트 및 CI 파이프라인 설계
3. 대화 컨텍스트 저장소(예: Redis) 연결 및 추천 서비스 확장

## Git Flow 제안
- `main`: 프로덕션 브랜치
- `develop`: 통합 개발 브랜치
- `feature/*`: 기능 단위 브랜치 (예: `feature/gemma-integration`)

각 작업 시 `feature/*` 브랜치에서 작업 후, 한국어 커밋 메시지와 함께 PR/merge 합니다.
