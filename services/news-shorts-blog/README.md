# 뉴스 쇼츠 → 네이버 블로그 에이전트

SBS 뉴스·MBC 뉴스·YTN의 공개 YouTube 피드를 기본 60초마다 확인하고, 해당 채널의 Shorts 목록에서도 확인한 **한국 시간 기준 당일 영상**을 네이버 블로그에 게시합니다. 기본 게시물은 보도 제목, 공개 시각, 출처와 원본 영상 링크를 담은 짧은 뉴스 안내문입니다. 영상 내용을 보지 않고 상세 기사나 사건의 배경을 만들어 내지 않으며, 전체 자막·기사·영상 파일을 복제하지 않습니다. 별도 유료 AI API 키는 필요하지 않습니다.

이번 설정의 기본 게시 대상은 `https://blog.naver.com/wdetector`, 블로그 카테고리는 **이슈**, 네이버 글 주제는 **사회·정치**입니다. 카테고리는 블로그 안에서 글을 모으는 분류이고, 주제는 네이버 발행 화면에서 선택하는 별도 분류입니다. 두 항목을 각각 확인해 게시합니다.

하루 최대 3개, 게시 간격 기본 5분입니다. 게시할 당일 쇼츠가 부족하거나 로그인·네트워크 문제가 있으면 3개보다 적게 게시될 수 있습니다. YouTube 피드와 Shorts 목록의 갱신 지연이 있어 업로드 즉시 감지하거나 최초 보도를 보장할 수는 없습니다. 컴퓨터가 켜져 있고 Windows에 로그인된 상태에서 에이전트가 실행 중이어야 합니다.

## Windows에서 처음 실행하기

이 클라우드에서는 `C:\Users\LG\Desktop\그로스빌런`에 직접 접근할 수 없습니다. 다음 작업은 그 폴더와 `pw` 파일이 있는 Windows PC에서 진행합니다. `news_agent` 폴더를 포함한 이 디렉터리 전체를 유지하세요.

1. Python 3.11 이상과 Google Chrome을 설치합니다.
2. `Setup.cmd`를 더블클릭합니다. 처음 설치할 때 위의 블로그·카테고리·주제가 기본으로 설정되므로 블로그 ID를 다시 입력할 필요가 없습니다. 비밀번호를 묻는 설치 단계는 없습니다. 기존 설정 파일이 있다면 보존하므로 아래 명령으로 지정한 항목을 갱신할 수 있습니다.

   PowerShell에서 옵션을 직접 지정하는 방법도 있습니다.

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -BlogId "wdetector" -Category "이슈" -Topic "사회·정치"
   ```

   다른 블로그를 사용하려면 실제 블로그 ID와 카테고리·주제를 지정합니다. 로그인 아이디와 블로그 ID가 다르면 블로그 주소의 ID를 입력합니다.

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -BlogId "내블로그ID" -Category "뉴스" -Topic "사회·정치"
   ```

   Chrome 대신 에이전트 전용 Chromium을 내려받으려면 `-BrowserChannel chromium`을 덧붙입니다. 설치는 의존성과 설정을 준비하며 게시를 시작하지 않습니다.

3. `Login.cmd`를 실행합니다. 표시된 브라우저에서 로그인, 캡챠 또는 추가 인증을 직접 완료합니다. 요청한 블로그의 편집기에 정상 진입했는지 확인합니다.
4. `Start.cmd`를 실행합니다. 이때부터 감시와 자동 게시가 시작됩니다. 창을 유지하세요. 종료하려면 해당 창에서 `Ctrl+C`를 누릅니다.

네이버 화면이 바뀌어 편집기나 발행 버튼을 확실히 식별하지 못하면 게시를 중단합니다. Windows에서 첫 로그인과 첫 실제 게시까지 확인해야 해당 계정의 운영 검증이 끝납니다. 클라우드 자동 테스트는 실제 계정 로그인이나 공개 게시 성공을 대신하지 않습니다.

## 한 번만 자동 게시하기

설치와 로그인 뒤 `Post-Once.cmd`를 더블클릭하면 채널을 한 번 확인하고, 게시 가능한 당일 쇼츠 **최대 1개**를 발행한 뒤 종료합니다. 창은 결과를 읽을 수 있도록 남아 있으며, 성공하면 확인된 게시물 주소를 표시합니다. 계속 감시하려면 `Start.cmd`를 사용합니다.

이미 `Start.cmd`나 `Login.cmd`가 실행 중이면 먼저 해당 창에서 `Ctrl+C`로 종료하세요. 같은 데이터와 브라우저 프로필을 사용하는 프로그램을 동시에 실행하지 않도록 잠금이 적용됩니다. 한 번 게시도 기존 하루 3개 한도·게시 간격·중복 방지·수동 인증·미확인 게시 보류 규칙을 그대로 따릅니다. 당일 후보가 없거나 한도에 도달했다면 게시하지 않고 종료합니다.

PowerShell에서 직접 실행할 수도 있습니다.

```powershell
& "$env:LOCALAPPDATA\GrowthvillainNewsAgent\.venv\Scripts\python.exe" -m news_agent once
```

종료 코드 `0`은 게시 확인 완료, `3`은 게시 가능한 후보가 없거나 한도·간격·수집 상태로 인해 게시하지 않음, `2`는 실행·인증·게시 실패 또는 게시 결과 확인 필요를 뜻합니다. 게시 여부는 출력된 주소와 `status` 명령으로 확인하세요. 이 클라우드에서는 PC의 새 `pw` 파일에 접근할 수 없어 실제 계정으로 한 번 게시하는 작업은 실행하지 못했습니다.

## Windows 화면 잠금과 절전

`Win+L`로 화면만 잠그면 로그인 세션과 이미 실행 중인 프로그램은 유지됩니다. 따라서 실행 중인 에이전트와 브라우저 자동화가 계속 동작할 수 있습니다. 다만 잠긴 Windows 화면에서의 실제 수집·발행은 아직 검증하지 않았으며, PC와 브라우저 상태에 따라 확인이 필요합니다.

캡챠나 추가 인증이 나타나면 수동 입력을 기다리므로 잠금을 풀고 브라우저에서 처리해야 합니다. 절전·최대 절전 중에는 작업이 진행되지 않고, 로그아웃·종료하면 실행 프로세스가 끝납니다. 화면 잠금과 절전은 다른 상태이므로 장시간 운영할 때 전원 설정을 직접 확인하세요. 설치 프로그램은 Windows 전원 설정을 변경하지 않습니다.

## 계정 파일과 수동 인증

기본 계정 파일 경로는 `C:\Users\LG\Desktop\그로스빌런\pw.txt`입니다. 해당 파일이 없으면 같은 위치의 확장자 없는 `pw`를 확인합니다. 메모장에 이미 작성해 둔 내용을 다음 형태 중 하나로 보관할 수 있습니다.

```text
아이디: 내네이버로그인아이디
비밀번호: 내비밀번호
```

또는 첫 줄은 아이디, 둘째 줄은 비밀번호인 두 줄 형식이나 `{"id":"...","password":"..."}` JSON을 사용할 수 있습니다. `id`, `username`, `네이버 아이디`, `pw`, `password`, `네이버 비밀번호` 등의 항목명도 지원합니다. UTF-8, BOM이 있는 UTF-16, CP949 파일을 읽습니다. 실제 비밀번호를 채팅으로 보내거나 저장소로 복사할 필요는 없습니다. 파일을 읽을 수 없으면 표시된 브라우저에서 직접 로그인할 수 있습니다.

에이전트는 계정 정보를 이용한 로그인 입력 후 인증이 필요하면 브라우저를 열어 둔 채 대기합니다. 캡챠를 자동으로 풀거나 인증을 우회하지 않습니다. 직접 인증한 뒤 요청한 블로그의 정상 편집기가 확인되면 재개합니다. 최종 발행을 누른 뒤 캡챠·추가 인증이 나타나도 수동 해결을 기다리며, 해결 후 게시 결과를 확인합니다. 발행 버튼을 자동으로 반복해서 누르지 않습니다. 대기 시간이 끝나거나 편집기 오류가 발생하면 발행을 보류하며 감시 작업은 별도 흐름으로 계속 진행합니다. 원인을 해결한 뒤 에이전트 창에서 `Ctrl+C`를 누르고 `Start.cmd`로 다시 실행합니다.

전용 브라우저 프로필에 로그인 세션을 유지합니다. 기존에 사용 중인 Chrome 프로필과 분리되어 있으며, 다른 창에서 로그인이 되어 있더라도 최초 인증이 필요할 수 있습니다. 로그인 중에는 같은 프로필을 사용하는 `Login.cmd`와 `Start.cmd`를 동시에 실행하지 마세요.

## 설정과 보관 위치

설정, 데이터베이스, 게시 이력, 전용 브라우저 프로필, Python 가상환경은 `%LOCALAPPDATA%\GrowthvillainNewsAgent`에 보관합니다. 저장소에 계정 정보나 세션을 쓰지 않습니다. 설정을 바꿀 때는 에이전트를 종료한 후 다음 파일을 편집하고 다시 실행합니다.

```powershell
notepad "$env:LOCALAPPDATA\GrowthvillainNewsAgent\config.json"
```

| 항목 | 기본값·의미 |
|---|---|
| `blog_id` | 기본 `wdetector`. 게시할 블로그 주소의 ID입니다. |
| `category` | 기본 `이슈`. 편집기에서 정확히 일치하는 블로그 카테고리를 선택합니다. `null`이면 편집기의 기본 카테고리를 사용합니다. |
| `topic` | 기본 `사회·정치`. 블로그 카테고리와 별도로 네이버 글 주제를 선택합니다. 지정한 분류를 확인할 수 없으면 발행을 보류합니다. |
| `credentials_file` | Windows의 로컬 `pw.txt` 경로. 비밀번호 값이 들어가는 필드는 아닙니다. |
| `browser_channel` | `chrome` 또는 `chromium`. Chromium 선택 시 설치 단계에서 브라우저를 내려받습니다. |
| `poll_seconds` | `60`. 최소 30초입니다. 외부 서비스 지연과 오류 시 대기로 실제 감지 시간이 달라질 수 있습니다. |
| `daily_limit` | `3`. 최대 3개입니다. 날짜는 한국 시간을 기준으로 합니다. |
| `min_publish_interval_seconds` | `300`. 게시 사이의 최소 간격입니다. |
| `channels` | 기본 SBS 뉴스 `@SBSnews8`, MBC 뉴스 `@MBCNEWS11`, YTN `@ytnnews24`. 이름과 공식 채널 핸들을 추가할 수 있습니다. |

전체 형식은 `config.example.json`을 참고하세요. `Install.ps1`을 다시 실행하면 기존 설정을 유지하며 명시적으로 지정한 `-BlogId`, `-Category`, `-Topic`, `-BrowserChannel`만 갱신합니다. 설정의 블로그 ID가 비어 있고 `-BlogId`도 지정하지 않은 경우에는 설치 창에서 ID를 입력받습니다. CLI의 `init`은 이미 있는 설정을 보존합니다. 사용자 지정 설정 파일은 `python -m news_agent --config "전체경로\config.json" run`처럼 하위 명령 앞에 지정합니다.

## 중복·실패 확인

영상 ID와 유사 제목으로 중복 후보를 걸러냅니다. 제목이 크게 다른 동일 사건까지 완벽하게 구별하는 의미 분석은 아닙니다. 영상을 감지했다고 곧바로 발행 완료로 기록하지 않고, 실제 발행 뒤 해당 게시물과 출처 링크를 확인합니다.

최종 발행을 요청한 직후 연결이 끊기면 실제로 올라갔는지 알 수 없습니다. 이런 경우 `uncertain` 상태로 남겨 추가 게시를 보류합니다. 재시작으로 제한이나 게시 이력을 초기화하지 않습니다. 한국 시간 날짜별 한도에는 확인된 게시와 결과가 불확실한 발행 요청을 함께 포함하며, 불확실한 건은 직접 확인하기 전까지 한도를 차지합니다.

자정을 지나 게시 완료가 확인되면 발행을 요청한 날과 완료를 확인한 날 양쪽의 한도에 보수적으로 반영합니다. 이 경우 새 날짜에 게시할 수 있는 개수가 줄어들 수 있습니다.

이 폴더의 PowerShell에서 상태를 확인합니다.

```powershell
$AgentPython = "$env:LOCALAPPDATA\GrowthvillainNewsAgent\.venv\Scripts\python.exe"
& $AgentPython -m news_agent status
```

불확실한 건은 네이버 블로그를 직접 열어 확인한 다음, 상태 출력에 있는 영상 ID를 사용해 처리합니다. 이미 올라갔으면 실제 게시물 주소를 기록합니다.

```powershell
& $AgentPython -m news_agent reconcile "영상ID" --url "https://blog.naver.com/내블로그ID/실제글번호"
```

게시되지 않은 것을 직접 확인했을 때만 다음 명령을 사용합니다.

```powershell
& $AgentPython -m news_agent reconcile "영상ID" --not-published
```

`reconcile`은 게시 이력을 정리합니다. 오류로 발행이 멈춰 있는 실행 창은 `Ctrl+C`로 종료한 후 `Start.cmd`로 다시 시작해야 게시가 재개됩니다. 원본이 어제 영상으로 넘어갔다면 오늘 새 게시 대상으로 사용하지 않습니다.

## Windows 로그인 시 자동 시작

수동 실행과 첫 게시를 확인한 뒤 원할 때 등록합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Autostart.ps1
```

현재 사용자로 로그인할 때 `GrowthvillainNewsShortsAgent` 예약 작업이 실행됩니다. 사용자가 브라우저 인증을 처리할 수 있도록 로그인된 대화형 세션에서 실행하며, 관리자 권한이나 Windows 암호를 저장하지 않습니다. 등록 직후 실행 중인 작업은 시작하지 않으므로 지금 실행하려면 `Start.cmd`를 여세요. 설치 폴더를 이동했다면 새 위치에서 자동 시작을 다시 등록합니다. PC 절전·종료·로그아웃 중에는 감시하지 못합니다.

자동 시작을 해제하려면:

```powershell
Unregister-ScheduledTask -TaskName "GrowthvillainNewsShortsAgent" -Confirm:$false
```

## 개발 검증

이 디렉터리에서 기존 단위 테스트를 실행합니다. 실제 YouTube 다운로드나 네이버 게시를 하지 않는 테스트입니다.

```powershell
& "$env:LOCALAPPDATA\GrowthvillainNewsAgent\.venv\Scripts\python.exe" -m unittest discover -s tests -v
```

브라우저에서 편집기·발행·수동 인증 대기 흐름을 확인하는 로컬 테스트도 포함되어 있습니다. 이 테스트는 네이버를 흉내 낸 테스트용 화면에서만 동작합니다. `NEWS_AGENT_TEST_BROWSER`에 Chrome 또는 Chromium 실행 파일의 전체 경로를 지정하면 함께 실행되고, 지정하지 않으면 해당 브라우저 테스트는 건너뜁니다.

```powershell
$env:NEWS_AGENT_TEST_BROWSER = "C:\Program Files\Google\Chrome\Application\chrome.exe"
& "$env:LOCALAPPDATA\GrowthvillainNewsAgent\.venv\Scripts\python.exe" -m unittest discover -s tests -v
Remove-Item Env:NEWS_AGENT_TEST_BROWSER
```

개발 중 Linux Chromium의 테스트용 화면을 포함해 73개 테스트를 통과했습니다. 브라우저 테스트에서는 `wdetector` 대상, `이슈` 카테고리, `사회·정치` 주제와 공개 설정을 발행 전에 확인했습니다. 1회 게시 테스트에서는 실행당 최대 1개, 반복 실행 시 하루 한도 유지, 채널 오류·인증 실패·발행 결과 불명 시 종료를 확인했습니다. Windows 설치 스크립트는 이 환경에 PowerShell이 없어 실제 실행하지 못했습니다. 실제 Windows·YouTube·네이버 계정을 통한 감지와 게시 성공은 별도 검증이 필요합니다.

공개 데이터 수집에는 YouTube RSS·채널 페이지 접근이, 로그인·게시에는 네이버 접근이 필요합니다. 계정 인증·채널 구조·편집기 구조 변경은 실제 PC에서 별도로 확인해야 합니다. 오류 메시지에 계정 파일 내용이나 세션 값을 붙여 넣지 말고, 상태와 실패 단계만 확인하세요.
