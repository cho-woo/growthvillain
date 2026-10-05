# 개인용 Meta 광고 수집기

공개 Meta 광고 라이브러리에서 검색어별 광고 소재를 수집하고 개인 포트폴리오의 `/tools/meta-ads/`에서 검색합니다. 기존 수집기의 광고 추출 부분만 분리했습니다. 회사 서버·계정·AWS·ERP·고객 데이터는 사용하지 않습니다.

## Windows에서 실행

Python 3.11 이상이 필요합니다. 첫 실행은 이 폴더에서:

```powershell
powershell -ExecutionPolicy Bypass -File .\Launch-MetaAds.ps1 -Setup
```

다음 실행부터:

```powershell
powershell -ExecutionPolicy Bypass -File .\Launch-MetaAds.ps1
```

브라우저가 `http://127.0.0.1:4177/tools/meta-ads/`를 엽니다. 실행 창을 닫거나 Ctrl+C를 누르면 수집기가 종료됩니다. 자동 수집은 매 실행 시 꺼져 있으며, 화면에서 켠 뒤 앱이 실행 중인 동안만 동작합니다. Windows 예약 작업은 설치하지 않습니다. 실행 중인 작업이 있으면 다음 작업은 대기합니다. Meta가 로그인을 요구하거나 요청을 차단하면 실패로 표시하고 우회를 시도하지 않습니다. 검색 결과가 없거나 저장 가능한 소재가 없어도 성공으로 처리하지 않습니다.

Meta가 공개 페이지의 접근 방식이나 화면 구조를 바꾸면 수집이 실패할 수 있습니다. 이 도구는 Meta 광고 API의 공식 연동이 아니며, 저장된 과거 자료와 현재 수집 결과를 구분합니다. 별도의 유료 클라우드 서비스는 사용하지 않습니다.

## 파일 구조

| 위치 | 내용 |
|---|---|
| `server.py` | 로컬 웹/API, 큐, 선택적 주기 수집 |
| `crawler.py` | 공개 광고 페이지 수집, 차단 감지 |
| `catalog.py` | 공개 필드 허용 목록, 소재 복사·내보내기 |
| `test_collector.py` | 경로·요청 보호·실패 처리 검증 |
| `Launch-MetaAds.ps1` | Windows 시작 파일 |
| `Publish-Archive.cmd` / `Publish-Archive.ps1` | 확인한 광고 자료만 GitHub에 게시 |
| `%LOCALAPPDATA%/JoWooHyung/MetaAds/` | 개인 DB·수집 원본·로그·실행 환경 |
| `../../tools/meta-ads/data/catalog.json` | 공개할 광고 목록 |
| `../../tools/meta-ads/media/` | 목록에 사용된 광고 이미지·영상 |

개인 데이터 폴더는 웹사이트 폴더 밖에 있어야 합니다. `CRAWLER_DATA_DIR`와 `WEB_ROOT` 환경 변수 또는 `--data-dir`, `--web-root` 인수로 위치를 변경할 수 있습니다. 수집 원본과 DB는 Git에 포함하지 않습니다.

## 기존 공개 광고 가져오기

DB를 통째로 복사하지 말고 공개 광고 `cards.jsonl`과 그 파일이 참조하는 로컬 소재만 가져옵니다. 한 광고 ID는 한 번만 저장되며, 같은 ID를 다시 가져오면 최신 내용으로 갱신합니다. 다른 내부 정보는 허용 목록에서 제외합니다.

```powershell
python server.py --web-root 'C:\path\to\portfolio' --data-dir 'C:\path\to\private-meta-ads' --import-jsonl 'C:\path\to\run\cards.jsonl' --export-only
```

현재 저장 자료만 다시 내보내려면:

```powershell
python server.py --web-root 'C:\path\to\portfolio' --data-dir 'C:\path\to\private-meta-ads' --export-only
```

내보내기는 `tools/meta-ads/data`와 `tools/meta-ads/media`만 변경하며 Git 푸시나 Netlify 배포는 하지 않습니다. Netlify에서는 마지막으로 게시한 광고 보관함을 볼 수 있고, 개인 PC의 작업 시작 버튼은 로컬 앱에서만 작동합니다.

## 공개 사이트에 게시

수집 결과를 직접 확인한 다음 `Publish-Archive.cmd`를 더블클릭합니다. 이 파일은 **수동으로 실행했을 때만** `tools/meta-ads/data`와 `tools/meta-ads/media`의 변경을 커밋하고 GitHub의 `cho-woo/growthvillain` 저장소 `master`로 푸시합니다. 기존 Git 로그인 정보를 사용합니다. Netlify 연결 빌드가 성공하면 공개 페이지에 반영됩니다.

다른 파일이 이미 Git에 스테이징되어 있거나, 광고 보관함 외의 미게시 커밋이 있으면 게시를 중단합니다. 원격 저장소에 새 변경이 있으면 자동으로 합치지 않습니다. 수집 프로그램 자체는 이 게시 파일을 호출하지 않습니다. 배포 코드의 최초 게시는 별도로 완료해야 합니다.

## API

기본 경로: `/api/meta-ads`

- `GET /bootstrap`: 세션 토큰, 현재 상태, 수집 대상, 최근 작업
- `GET /status`, `/cards`, `/competitors`, `/jobs`
- `POST /competitors`, `PUT /competitors/{id}`, `DELETE /competitors/{id}`
- `POST /collect`: `{ "competitorId": "…", "limit": 20 }`
- `POST /jobs/{id}/cancel`
- `POST /settings`: `{ "autoEnabled": true }`
- `POST /export`: 공개 목록과 소재 내보내기
- `POST /import`: `{ "runId": "…" }`, 개인 데이터 폴더 안의 기존 실행만 허용

변경 요청은 같은 출처에서 `X-Meta-Ads-Token` 헤더를 포함해야 합니다. 서버는 `127.0.0.1`에만 연결하고 Host/Origin도 확인합니다. 토큰은 매 실행 시 재생성됩니다. 공개 사이트에서 로컬 수집기에 접근하는 CORS 권한은 제공하지 않습니다.

## 검증

```powershell
python -m unittest test_collector -v
```

자동 테스트는 네트워크 수집을 수행하지 않습니다. 실제 Meta 수집 성공 여부는 로컬 앱에서 별도로 확인해야 합니다.

### 2026-10-05 실제 실행 확인

- 기존 공개 광고 40개와 로컬 이미지·영상을 가져와 보관함으로 내보내는 기능은 확인했습니다.
- 설치된 Playwright와 Chromium의 실행 및 Meta 페이지 요청까지 진행했습니다.
- Meta 응답이 **HTTP 403**으로 차단되어 새 광고 수집은 완료하지 못했습니다. 현재 검증된 결과를 새 광고 자동 수집 성공으로 표시하지 않습니다.
- 접근 제한은 작업 목록에 `Meta가 수집 요청을 차단했습니다(접근 제한). 저장된 광고는 유지됩니다.`로 표시합니다. 차단 우회는 하지 않으며 기존 광고 자료는 유지합니다.
