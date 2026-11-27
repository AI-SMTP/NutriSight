# FastAPI 골격·모듈 계약·Fake·계약 테스트 패턴: Research Report
*Generated: 2026-11-27 | Sources: 14 | Adapters: [adapter-exa, adapter-firecrawl] | Failed: 없음*

## Executive Summary
애플리케이션형 FastAPI 백엔드는 `src/` 없이 `app/` 평면 구조와 `uv init --no-package`(빌드 백엔드 없음)로 충분하다는 것이 uv 공식 가이드와 메인테이너 답변의 입장이다 ([uv FastAPI 가이드](https://docs.astral.sh/uv/guides/integration/fastapi/), [uv #18371](https://github.com/astral-sh/uv/issues/18371)). 모듈 경계는 도메인 쪽이 `typing.Protocol`로 필요한 모양을 정의하고 어댑터가 이를 구현하는 포트·어댑터 방식이 Python에서 널리 쓰인다 ([Python SME Cookbook](https://python.codeguides.io/architecture-design/architecture-mental-model/), [mcp-auditor ADR](https://github.com/mkrtchian/mcp-auditor/blob/main/docs/adr/002-hexagonal-architecture.md)). Fake가 실제 구현과 어긋나지 않게 하려면 같은 테스트 묶음을 두 구현에 돌리는 계약 테스트를 쓴다 ([Jan Giacomelli](https://jangiacomelli.com/blog/testing-behavior-not-implementation-details-part-3/), [Gineste 예제](https://github.com/Sebastien-Gineste/stop-mocking-everything--the-3-tests-I-start-with-for-a-service)). 설정은 `pydantic-settings`의 `BaseSettings`로 환경변수를 검증해 읽는 것이 FastAPI 공식 방식이다 ([FastAPI Settings](https://fastapi.tiangolo.com/advanced/settings/)).

## 1. 프로젝트 골격 (uv · ruff · pytest)
- uv 공식 FastAPI 가이드는 기존 `app/` 구조에서 `uv init --no-package`로 평면·비패키지 프로젝트를 만들고 `uv add fastapi --extra standard`, `uv run fastapi dev`로 실행한다. `uv run`이 `uv.lock`과 가상환경을 자동으로 만든다 ([uv FastAPI 가이드](https://docs.astral.sh/uv/guides/integration/fastapi/)).
- `src/` 대 평면 구조는 상황에 따른 선택이며, 빌드 시스템을 쓰지 않으면 따를 필요가 없다는 메인테이너 답변이 있다. 질문자는 `tests/`에 `__init__.py`를 두어 빌드 백엔드 없이 `from app...` 임포트를 해결했다 ([uv #18371](https://github.com/astral-sh/uv/issues/18371)).
- FastAPI 공식 풀스택 템플릿도 `backend/app/` + `backend/pyproject.toml` 구조를 쓴다고 같은 이슈에서 인용된다 ([uv #18371](https://github.com/astral-sh/uv/issues/18371)). (단일 출처 인용, 직접 확인하지 않음)
- 개발 의존성은 PEP 735 `[dependency-groups]`로 두고 `uv.lock`을 커밋하는 방식이 uv 기본 관례로 소개된다 ([bitrise python-samples](https://github.com/bitrise-io/python-samples), [FastAPI Boilerplate](https://benavlabs.github.io/FastAPI-boilerplate/user-guide/development/)).

## 2. Protocol 기반 포트와 Fake
- 도메인이 구체 어댑터를 임포트하는 대신 필요한 모양을 `typing.Protocol`로 정의하고, 어댑터가 그 모양을 구현해 의존 방향을 뒤집는다 ([Python SME Cookbook](https://python.codeguides.io/architecture-design/architecture-mental-model/), [Omar Crosby](https://omarcrosby.com/posts/hexagonal-architecture-in-plain-language/)).
- LLM 호출을 `LLMPort` Protocol로 추상화하고 어댑터를 `adapters/`에 두는 ADR 사례가 있다. 이 프로젝트의 `IntakeEstimator`(VLM 어댑터)와 같은 구조다 ([mcp-auditor ADR](https://github.com/mkrtchian/mcp-auditor/blob/main/docs/adr/002-hexagonal-architecture.md)).
- 목(mock) 대신 포트 경계에 단순한 Fake를 두는 것이 권장된다. 상태를 메모리에 두는 Fake가 빠르고 결정적이다 ([dioxide](https://dioxide.readthedocs.io/en/stable/user%5Fguide/testing_with_fakes.html), [Skein](https://fallowlone.com/en/learn/architecture-patterns/04-hexagonal/03-testing-at-the-boundary/)).

## 3. 계약 테스트
- 같은 테스트를 구현마다 따로 쓰면 한쪽만 고쳐 어긋나기 쉽다. 추상 픽스처를 가진 계약 클래스(`TaskStoreContract`)를 만들고 구현별 하위 클래스가 픽스처만 바꾸는 방식이 제시된다 ([Jan Giacomelli](https://jangiacomelli.com/blog/testing-behavior-not-implementation-details-part-3/)).
- pytest는 픽스처 파라미터화(`@pytest.fixture(params=...)`)로 같은 테스트를 여러 구현에 돌릴 수 있다 ([pytest parametrize](https://docs.pytest.org/en/stable/how-to/parametrize.html), [Stack Overflow](https://stackoverflow.com/questions/26266481/pytest-reusable-tests-for-different-implementations-of-the-same-interface)).
- FastAPI 예제 저장소는 경계마다 계약 함수를 정의해 Fake(`tests/doubles/`)와 실제 어댑터에 모두 돌리고, `pytest -m contract` 마커로 층을 나눈다. 계약 테스트는 계약에 적힌 약속만 보장하며 동시성·트랜잭션·적지 않은 실패 모드는 보장하지 않는다고 명시한다 ([Gineste 예제](https://github.com/Sebastien-Gineste/stop-mocking-everything--the-3-tests-I-start-with-for-a-service)).
- 한 프로세스 안에 담당자가 다른 모듈이 여럿인 모듈러 모놀리스에서는 모듈 간 경계마다 얇은 계약 테스트를 두고, 이웃 모듈은 Fake로 대신하는 구성이 권장된다 ([OneEnv](https://blog.oneenv.io/articles/modular-monolith-testing-make-the-module-your-main-test-unit)).

## 4. 설정과 구현 전환
- FastAPI 공식 문서는 `pydantic-settings`의 `BaseSettings`로 환경변수를 타입 검증해 읽고, 설정을 별도 모듈(`config.py`)에 두며, 의존성(`Depends(get_settings)`)으로 주입해 테스트에서 바꿔 끼우는 방식을 안내한다 ([FastAPI Settings](https://fastapi.tiangolo.com/advanced/settings/), [FastAPI Discussion #11169](https://github.com/fastapi/fastapi/discussions/11169)).
- 설정을 모델로 두면 값의 검증·우선순위·기본값이 한곳에 모인다 ([FastAPI Patterns](https://fastapi-patterns.com/core-architecture-routing-patterns/configuration-management/)).

## 5. dataclass와 Pydantic의 역할 분담
- 외부에서 들어오는 신뢰할 수 없는 데이터(HTTP 요청·응답)는 Pydantic, 내부 도메인 값은 표준 dataclass를 쓰는 구분이 여러 출처에서 일치한다 ([Tech Tutorials 2026](https://tutorials.technology/tutorials/python-dataclasses-vs-pydantic-v2-2026.html), [pythonresources](https://pythonresources.com/guides/dataclasses-vs-pydantic-vs-attrs/)).

## Key Takeaways
- 백엔드는 `backend/app/` 평면 구조 + `uv init --no-package`로 시작해도 된다. 테스트 임포트는 `tests/__init__.py` 또는 pytest `pythonpath` 설정으로 해결한다 (추론: 둘 중 어느 쪽을 쓸지는 spec에서 정한다).
- 계약 파일은 frozen dataclass + `typing.Protocol`로 두고, HTTP 스키마(Pydantic)와 분리한다.
- 이 프로젝트의 Fake는 테스트 전용이 아니라 **실행 중 더미 구현**으로도 쓰이므로 `tests/doubles/`가 아니라 앱 패키지 안에 둬야 한다 (추론: 일반 사례와 다른 점).
- 계약 테스트는 추상 픽스처 계약 클래스 또는 파라미터화 픽스처로 Fake와 실제 구현에 같은 테스트를 돌린다. 병행 트랙은 자기 구현을 픽스처에 추가하기만 하면 된다.
- 계약 테스트가 보장하지 않는 것(지연, 외부 API 실패 양상 등)은 계약에 명시적으로 적어야 한다.
- 구현 전환은 `pydantic-settings` 설정값 + 팩토리 함수로 하고, 테스트에서는 의존성 오버라이드로 바꾼다.

## Sources
1. [Using uv with FastAPI](https://docs.astral.sh/uv/guides/integration/fastapi/) — uv 공식 FastAPI 통합 가이드
2. [uv #18371: app/ vs src/app](https://github.com/astral-sh/uv/issues/18371) — 애플리케이션형 백엔드의 레이아웃 선택
3. [bitrise-io/python-samples](https://github.com/bitrise-io/python-samples) — PEP 735 dependency-groups와 uv.lock 사용 예
4. [FastAPI Boilerplate: Development](https://benavlabs.github.io/FastAPI-boilerplate/user-guide/development/) — ruff·pytest 도구 구성
5. [Python SME Cookbook: Architecture Mental Model](https://python.codeguides.io/architecture-design/architecture-mental-model/) — Protocol로 의존 방향 뒤집기
6. [Omar Crosby: Hexagonal architecture](https://omarcrosby.com/posts/hexagonal-architecture-in-plain-language/) — Protocol 포트 예시
7. [mcp-auditor ADR 002](https://github.com/mkrtchian/mcp-auditor/blob/main/docs/adr/002-hexagonal-architecture.md) — LLMPort Protocol 사례
8. [dioxide: Testing with Fakes](https://dioxide.readthedocs.io/en/stable/user%5Fguide/testing_with_fakes.html) — 목 대신 Fake
9. [Skein: Testing at the boundary](https://fallowlone.com/en/learn/architecture-patterns/04-hexagonal/03-testing-at-the-boundary/) — 인메모리 Fake와 테스트 피라미드
10. [Jan Giacomelli: Testing behavior part 3](https://jangiacomelli.com/blog/testing-behavior-not-implementation-details-part-3/) — 계약 클래스 패턴
11. [Gineste: Stop mocking everything](https://github.com/Sebastien-Gineste/stop-mocking-everything--the-3-tests-I-start-with-for-a-service) — FastAPI 계약 테스트 예제와 한계
12. [pytest: parametrize](https://docs.pytest.org/en/stable/how-to/parametrize.html) — 픽스처 파라미터화
13. [OneEnv: Modular monolith testing](https://blog.oneenv.io/articles/modular-monolith-testing-make-the-module-your-main-test-unit) — 모듈 경계 계약 테스트
14. [FastAPI: Settings](https://fastapi.tiangolo.com/advanced/settings/) — pydantic-settings와 의존성 주입

## Methodology
Searched 6 queries (각 어댑터에 동일 질의). Adapters used: adapter-exa, adapter-firecrawl. Adapters failed: 없음.
Sub-questions investigated: (1) uv·ruff·pytest 기반 FastAPI 골격, (2) Protocol 포트·Fake·계약 테스트, (3) 설정 기반 구현 전환과 dataclass/Pydantic 경계. Sources analyzed: 6건 정독, 나머지는 검색 요약.
