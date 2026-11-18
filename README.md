# 조우형 포트폴리오 V2

현재 공개 버전과 비교하기 위한 독립 구현입니다. 브랜치: `codex/portfolio-v2-experience`. `master`에 병합하지 않습니다.

제작·레퍼런스 분석·수정 방법·검수 범위는 [소유자 안내서](docs/handbook.html)를 확인하세요. 원래 공개된 내용은 `source/`에 보관했고, 이 폴더는 웹 배포 대상에서 제외했습니다.

```powershell
py -m pip install -r requirements.txt
.\scripts\preview.ps1
py scripts/verify.py
```

로컬 미리보기: http://127.0.0.1:4174/ . 콘텐츠를 바꾼 뒤에는 `py build_v2.py`로 HTML을 다시 만들고 결과도 함께 커밋합니다. Cloudflare의 `python build_cloudflare.py`는 체크인한 정적 파일을 `dist/`에 모읍니다.

- 사례 원고: `content/projects.json`
- 한 페이지 템플릿: `templates/portfolio.html`, `scripts/profile_build.py`
- 화면 스타일: `css/profile.css`와 작업물 공통 스타일 `css/v2.css`
- 3D / 탐색 / 사운드: `js/decision-field.js`, `js/profile.js`, `js/sound.js`
- 자료 목록·원본 해시·검수 결과: `research/`
- 배경음악은 Flint의 **Code Runner**입니다. 제공된 MP3와 파일 정보는 `audio/`에 있습니다.

빌드 출력은 검색 수집을 막도록 `noindex`를 사용합니다. 미디어 파일은 Cloudflare의 파일별 25MiB 제한을 빌드에서 확인합니다.
