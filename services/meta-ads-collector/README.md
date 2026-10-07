# 개인용 광고 수집·자동화 모니터

공개 Meta 광고 소재와 네이버 쇼핑인사이트 순위 변화를 수집하고, [광고 레퍼런스 스튜디오](https://1jang2.netlify.app/tools/meta-ads/)에 게시합니다. 이 문서는 구현된 동작과 실행 방법을 설명합니다. 현재 프로세스가 실행 중인지는 PC 상태창의 실제 응답과 최근 성공 시각으로 확인해야 합니다.

## 실행과 ON/OFF

Python 3.11 이상이 필요합니다. 첫 설치는 이 폴더에서 실행합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\Launch-MetaAds.ps1 -Setup
```

수집기만 터미널에서 직접 실행할 때는 `Launch-MetaAds.ps1`을 사용합니다. 이 방식으로 띄운 서버는 해당 콘솔을 닫으면 종료됩니다. 백그라운드 허브와 화면 우측 상단 상태창은 다음으로 실행합니다. 설치된 개인 실행 환경과 상태창용 Python 3.12를 사용합니다.

```powershell
python .\launch_hub.py --widget
```

상태창은 Meta 광고, 네이버 급상승, 맛집 블로그, 뷰티 블로그의 ON/OFF, 실행·대기·오류 상태, 다음 일정과 남은 시간을 표시합니다. 5초마다 로컬 서버의 응답을 확인하며, 오래된 응답은 연결 끊김으로 표시합니다. 창을 닫아도 백그라운드 자동화는 유지됩니다. 상태창만 다시 열려면 `Launch-Status.ps1`을 실행합니다.

ON/OFF 설정은 저장되어 재실행 후에도 유지됩니다. OFF는 다음 자동 실행을 중지하는 설정입니다. 이미 진행 중인 블로그 작업은 강제 종료하지 않고 완료 후 대기합니다. PC가 켜져 있고 로그인되어 있으며 해당 프로그램이 동작해야 실행됩니다.

Windows 로그인 시 자동 시작 및 5분 간격의 서버 복구 확인을 등록하려면:

```powershell
powershell -ExecutionPolicy Bypass -File .\Install-AutomationHub.ps1
```

등록되는 작업은 `GrowthvillainAutomationHub`와 `GrowthvillainAutomationHubHealth`입니다. 사용자 권한으로 실행하며, 복구 확인은 종료된 서버만 다시 시작합니다. 저장된 OFF 설정을 ON으로 바꾸거나 발행을 강제하지 않습니다. 상태창을 닫았다고 5분마다 다시 열지도 않습니다. PC 종료·절전·로그아웃 동안의 실행을 보장하는 클라우드 서비스는 아닙니다.

## 수집 주기와 기간 표시

| 대상 | 기본 동작 |
|---|---|
| Meta 새 광고 | 등록한 검색어별 6시간 간격. 화면에서 6·12·24시간 등으로 변경 가능 |
| 기존 광고 게재 상태 | 매시간 오래 확인하지 않은 광고부터 최대 10개 조회 |
| 네이버 인기검색어 | 매시간 공개된 최신 일간 순위를 확인하고 7일 전 일간 순위와 비교 |
| 뷰티 블로그 | 첫 활성화 시 당일 수집, 이후 한국 시간 07:00 수집. 확인된 발행용 초안만 하루 최대 1회 발행 |
| 맛집 블로그 | 기존 맛집 스케줄러의 일정을 유지하며 상태·ON/OFF를 연결 |

광고가 60개라면 상태 확인은 정상 처리 기준 약 6시간에 한 바퀴입니다. 매시간 모든 광고를 확인하는 방식이 아니며, 차단·오류·PC 중단 시 더 오래 걸릴 수 있습니다. 새 수집과 상태 확인 작업은 겹치지 않게 순서대로 처리합니다.

광고 목록의 게재 상태는 마지막 성공한 확인 시점 기준입니다.

- 명시된 종료일이 있으면 시작일과 종료일을 포함해 `182일 게재 후 종료`처럼 표시합니다.
- 정확한 광고 ID를 조회했고 정상 응답에서 광고가 없음을 확인한 경우에는 `종료 감지일`을 저장하고 `182일 게재 후 종료 · 감지일 기준`처럼 표시합니다. 실제 종료일이 확인된 기록과 구분합니다.
- 로그인 요구, 보안 확인, 접근 제한, 네트워크 오류를 종료로 처리하지 않습니다. 검색 목록에서 광고가 안 보였다는 이유만으로도 종료로 처리하지 않습니다.
- 상태를 확인하지 못한 과거 자료는 `상태 미확인`으로 표시합니다. 시작일부터 수집일까지의 경과 일수는 실제 집행 기간과 다를 수 있습니다.

## 네이버 급상승 기록

기본 분야는 건강식품입니다. 인기검색어 상위 100개의 두 일간 순위를 비교하고, 10계단 이상 상승하거나 상위 20위에 새로 진입한 검색어를 후보로 기록합니다. `60위 → 7위 · 7일 비교`처럼 이전·현재 순위, 기준일, 비교 기간, 처음 관측한 시각을 누적 보관합니다. 상위 100위에 없었던 검색어는 `100위 밖`으로 표시하며 임의의 이전 순위를 만들지 않습니다.

이 자료는 네이버의 일간 검색 관심도 순위입니다. 매시간 조회하더라도 분 단위 실시간 순위나 정확히 며칠 만에 상승을 완료했는지를 알 수 있는 자료는 아닙니다. 공개 대시보드는 최신 후보와 누적 기록, 검색·내보내기 기능을 제공하며, 새 데이터는 게시 후 반영됩니다.

처음 발견한 검색어는 로컬 화면의 `브랜드 확인`에서 브랜드명과 공식 도메인 등을 등록합니다. 일반 상품명은 제외할 수 있습니다. 확인된 브랜드만 광고를 자동 수집하며 기본 상한은 하루 5개 브랜드, 브랜드당 광고 20개입니다. 동일 브랜드의 중복 요청과 최근 수집을 제한합니다. 도메인을 비우면 관련된 다른 광고주의 소재가 섞일 수 있습니다.

뷰티 발행은 맛집 작업과 최소 3시간 간격을 두고, 공통 잠금으로 동시에 네이버에 발행하지 않습니다. 원본 제품과 전성분의 일치가 확인되지 않은 참고용 초안은 발행하지 않습니다. Parse 공개상품 수집과 네이버 발행은 별도 프로세스로 실행하며, 발행 프로세스에는 `PARSE_*` 환경 변수를 전달하지 않습니다.

## D드라이브 저장과 공개 사이트

개인 광고 DB, 수집 원본, 이미지·영상, 순위 원본, 실행 로그는 설정한 D드라이브 폴더에 보관합니다. 사이트에서 조회할 공개 목록과 소재 사본은 웹사이트 프로젝트의 `tools/meta-ads/data/`와 `tools/meta-ads/media/`에 생성합니다. 따라서 D드라이브 원본 저장과 공개 사이트에서의 조회를 함께 지원하며, 사이트 사본만큼 웹 프로젝트가 있는 드라이브에도 공간이 필요합니다.

저장 위치 선택 순서는 `--data-dir`, `CRAWLER_DATA_DIR`, 개인 `settings.json`의 `dataDir`, 초기 기본 LocalAppData입니다. 이미 설정한 드라이브가 없으면 다른 드라이브로 자동 대체하지 않고 중단합니다. 이후 C드라이브로 옮길 때는 원본을 이동하고 저장 설정을 함께 변경해야 합니다. DB와 원본 폴더는 웹사이트 바깥에 있어야 합니다.

| 위치 | 내용 |
|---|---|
| `%LOCALAPPDATA%/JoWooHyung/MetaAds/settings.json` | 개인 저장 위치 설정 |
| `%LOCALAPPDATA%/JoWooHyung/MetaAds/runtime/` | 광고 수집용 Python 환경 |
| `%LOCALAPPDATA%/JoWooHyung/AutomationHub/` | 허브 제어·상태 응답·공통 발행 잠금·로그 |
| 설정한 D드라이브 데이터 폴더 | 광고 DB, `runs`, `media`, `trends`, 게시 상태 |
| `../../tools/meta-ads/data/catalog.json` | 공개 광고 목록 및 게재 상태 |
| `../../tools/meta-ads/data/trends.json` | 공개 순위 후보·누적 기록 |
| `../../tools/meta-ads/data/automation.json` | 시각이 명시된 자동화 상태 스냅샷 |
| `../../tools/meta-ads/media/` | 공개 사이트용 이미지·영상 사본 |

## 사이트 자동 게시

`autoPublishEnabled`가 켜져 있으면 공개 자료 변경을 모아서 기존 Git 로그인으로 `cho-woo/growthvillain`의 `master`에 커밋·푸시합니다. 게시 대상은 `tools/meta-ads/data`와 `tools/meta-ads/media`뿐입니다. 원본 DB, 네이버 쿠키·계정, API 키, 개인 설정·로그를 게시하지 않습니다. 수동 실행용 `Publish-Archive.cmd`도 유지합니다.

코드 변경이나 광고 보관함 밖의 미게시 커밋, 관련 없는 스테이징 파일, 원격 저장소의 새 변경이 있으면 게시를 중단합니다. 임의로 병합하거나 다른 작업을 포함해 푸시하지 않습니다. 실패 시 자료는 로컬에 유지되며 재시도 대기와 오류 상태를 기록합니다.

`publication.lastSuccessAt`과 화면의 `사이트 게시 전송`은 Git 전송 성공 시각입니다. Netlify의 연결 빌드가 성공해야 실제 공개 URL에 반영되며, 이 시각 자체가 Netlify 배포 완료를 확인한 것은 아닙니다. 공개 페이지는 저장된 상태 스냅샷과 게시 시각을 표시합니다. PC의 현재 ON/OFF를 실시간으로 확인하려면 로컬 상태창을 사용합니다. 공개 페이지는 60초마다 게시된 자료를 다시 확인합니다.

`server.py --export-only`는 공개 파일만 내보냅니다. 이 일회성 명령 자체는 Git 푸시나 배포를 실행하지 않습니다.

## 로컬 API와 접근 범위

기본 주소는 `http://127.0.0.1:4177/api/meta-ads`입니다.

- `GET /bootstrap`: 로컬 세션 토큰과 초기 상태
- `GET /status`, `/automations`, `/cards`, `/competitors`, `/jobs`, `/trends`
- `POST /automations/{meta-ads|naver-trends|food-blog|beauty-blog}`: `{ "enabled": true }`
- `POST /settings`: `{ "autoEnabled": true, "autoPublishEnabled": true }`
- `POST /competitors`, `PUT /competitors/{id}`, `DELETE /competitors/{id}`
- `POST /collect`, `POST /jobs/{id}/cancel`, `POST /export`, `POST /import`
- `POST /trends/settings`, `/trends/scan`, `/trends/brands`, `/trends/ignore`, `/trends/collect`

변경 요청은 로컬의 신뢰할 수 있는 출처에서 `X-Meta-Ads-Token` 헤더를 포함해야 합니다. 서버는 `127.0.0.1`에만 연결하고 Host/Origin을 검사합니다. 토큰은 서버 실행 시 새로 생성합니다. 공개 사이트에 토큰을 넣거나 공개 사이트에서 localhost로 호출하는 CORS 권한을 제공하지 않습니다. 공개 사이트의 관리 링크는 로컬 관리 페이지로 이동하는 링크입니다.

## 구성과 검증

`server.py`는 로컬 API·작업 큐, `crawler.py`와 `check_ad_status.py`는 광고 수집·상태 확인, `ad_lifecycle.py`는 게재 기간 판정, `catalog.py`는 공개 필드·소재 내보내기를 담당합니다. `trend_service.py`는 네이버 순위와 누적 기록을 관리합니다. `archive_publisher.py`는 공개 자료 게시, `automation_manager.py`와 `automation_bridge.py`는 블로그 제어·상태·잠금, `desktop_status.py`는 작은 상태창을 담당합니다.

```powershell
python -m unittest discover -p "test_*.py" -v
node --test ../../tools/meta-ads/tests/catalog.test.mjs
```

자동 테스트는 실제 광고 수집이나 블로그 발행을 수행하지 않습니다. 수집 사이트의 화면 변경, 로그인 요구, 접근 제한은 실제 실행에서 별도로 확인해야 합니다. 접근 제한이나 보안 확인이 나오면 중단하고 기존 자료를 유지합니다.
