"""Build the independent V2 experience from editable facts and original public evidence."""
from pathlib import Path
from bs4 import BeautifulSoup
from html import escape as E
import json, shutil

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'source'
SOURCE.mkdir(exist_ok=True)
if not (SOURCE/'work.html').exists():
    shutil.copy2(ROOT/'work.html',SOURCE/'work.html')
    shutil.copytree(ROOT/'portfolio',SOURCE/'portfolio',dirs_exist_ok=True)
if not (SOURCE/'contents.html').exists():
    shutil.copy2(ROOT/'contents.html',SOURCE/'contents.html')
facts=json.loads((ROOT/'content/projects.json').read_text(encoding='utf-8'))
old=BeautifulSoup((SOURCE/'work.html').read_text(encoding='utf-8'),'html.parser')
evidence_file=ROOT/'research/evidence-map.json'
evidence=json.loads(evidence_file.read_text(encoding='utf-8')) if evidence_file.exists() else []
media_map={m['source_url']:m for m in evidence}
projects_dir=ROOT/'projects';projects_dir.mkdir(exist_ok=True)

HEAD='''<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#070711"><meta name="robots" content="noindex,nofollow"><link rel="icon" href="/img/v2-mark.svg" type="image/svg+xml"><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800;900&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet"><link rel="stylesheet" href="/css/v2.css"><script type="module" src="/js/v2.js"></script>'''
HEADER='''<a class="skip" href="#main">본문으로 건너뛰기</a><header class="site-header"><a class="brand" href="/" aria-label="조우형 포트폴리오 홈"><span class="brand-symbol" aria-hidden="true">✳</span><span>JO WOO HYUNG<span class="violet">_</span></span></a><button class="menu-button" type="button" aria-expanded="false" aria-controls="navigation">메뉴 <span aria-hidden="true">＋</span></button><nav id="navigation" class="site-nav" aria-label="주요 메뉴"><a href="/#work">대표 작업</a><a href="/archive.html">전체 작업</a><a href="/#approach">운영 기준</a><a href="/#about">소개</a><a class="nav-contact" href="/#contact">연락처 ↗</a></nav><button class="sound-toggle" type="button" aria-pressed="false" aria-label="사운드 켜기"><span class="sound-bars" aria-hidden="true"><i></i><i></i><i></i><i></i></span><span data-sound-label>SOUND OFF</span></button><div class="read-progress" aria-hidden="true"><span></span></div></header>'''
FOOTER='''<footer class="contact section" id="contact"><div class="section-label"><span>06 / 연락처</span><span>다음 프로젝트에 관해 이야기해요.</span></div><a class="contact-heading" href="mailto:hi341096@gmail.com">함께 풀어볼<br>문제가 있나요<span>↗</span></a><div class="contact-links"><a href="mailto:hi341096@gmail.com">hi341096@gmail.com</a><a href="tel:01096567679">010-9656-7679</a><button class="email-copy" type="button">이메일 복사 <span aria-hidden="true">⧉</span></button><span class="copy-announcement sr-only" aria-live="polite"></span></div><div class="footer-end mono"><span>© 2026 조우형</span><a href="https://jowoohyung-portfolio.pages.dev/" target="_blank" rel="noopener">현재 공개 버전과 비교 ↗</a><a href="/#home">위로 ↑</a></div></footer>'''
OVERLAYS='''<dialog class="image-dialog" aria-label="작업 자료 확대 보기"><button class="dialog-close" type="button" aria-label="확대 화면 닫기">닫기 ✕</button><div class="dialog-scroll"><img alt=""></div><div class="dialog-caption"><p></p><a target="_blank" rel="noopener">원본 파일 열기 ↗</a></div></dialog><div class="page-curtain" aria-hidden="true"><span>JO WOO HYUNG_</span></div><div class="cursor-note mono" aria-hidden="true">OPEN ↗</div><div class="sound-status sr-only" role="status" aria-live="polite"></div>'''
def shell(title,body,page='home',description='조우형의 퍼포먼스 마케팅, 데이터 구축, 자동화 프로젝트와 운영 판단 기록.'):
    return f'<!doctype html><html lang="ko"><head>{HEAD}<title>{E(title)} — 조우형 포트폴리오 V2</title><meta name="description" content="{E(description)}"></head><body data-page="{page}">{HEADER}<main id="main" tabindex="-1">{body}{FOOTER}</main>{OVERLAYS}</body></html>'
def write(path,html):
    p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(html+'\n',encoding='utf-8')
def text(s):return E(s).replace('\n','<br>')
operation_headings = {
    'BUSINESS PROFITABILITY': '사업 수익성',
    'CREATIVE SCREENING & SCALING': '광고 소재 선별과 예산 증액',
    'META · GOOGLE · TIKTOK': '메타 · 구글 · 틱톡',
    'META · 01 / TEST': '메타 · 01 / 소재 테스트',
    'META · 02 / SCALE': '메타 · 02 / 예산 증액',
    'GOOGLE ADS': '구글 광고',
    'TIKTOK ADS': '틱톡 광고',
    'PRODUCT LAUNCH & GROWTH': '신제품 출시와 성장',
    'NEW PRODUCT CASE': '신제품 사례',
    'MONTHLY PERFORMANCE DIAGNOSIS': '월별 성과 분석',
    'AD REVIEW & TROUBLESHOOTING': '광고 심사와 문제 해결',
}

def material(tag):
    if tag is None:return ''
    copy=BeautifulSoup(str(tag),'html.parser')
    for heading in copy.select('.operations-chapter-heading p, .operations-kicker'):
        label = heading.get_text(strip=True)
        if label in operation_headings:
            heading.string = operation_headings[label]
    for img in copy.select('img'):
        if img.get('src') in media_map:
            entry=media_map[img['src']];img['data-original']=img['src'];img['src']=entry['local_url']
        img['loading']='lazy';img['decoding']='async'
    for v in copy.select('video'):v['preload']='none';v['playsinline']='';v['controls']=''
    for hidden in copy.select('[hidden]'):hidden.decompose()
    return str(copy)

def case_media(f):
    key=f['id']
    if key == 'aerunb':
        return (SOURCE / 'aerunb-case.html').read_text(encoding='utf-8')
    if key in ['desillab','mogrami']:
        a=old.find(id='case-'+key)
        videos=material(a.select_one('.brand-creatives'))
        detail=material(a.select_one('.brand-detail-preview')) if key=='desillab' else ''
        more=material(a.select_one('.mogrami-ppl')) if key=='mogrami' else ''
        return f'<section class="case-section evidence"><div class="case-section-label mono">04 / 광고 소재</div><h2>실제 집행한 광고 소재</h2><p class="section-intro">영상을 선택하면 재생됩니다. 프로젝트 영상에 소리가 있으면 배경음은 자동으로 작아집니다.</p>{videos}{more}'+(f'<h3 class="media-subhead">고추장버터 상세페이지</h3><p class="section-intro">이미지를 선택하면 원본 크기로 볼 수 있습니다.</p><div class="detail-material">{detail}</div>' if detail else '')+'</section>'
    if key=='binusoap':
        a=old.find(id='case-binusoap')
        before=material(a.select_one('.comparison-before .brand-detail-preview'))
        after=material(a.select_one('.comparison-after .brand-detail-preview'))
        chart=material(a.select_one('.brand-sales-chart'))
        return f'''<section class="case-section evidence"><div class="case-section-label mono">04 / 개선 전후</div><h2>상세페이지 전후 비교</h2><p class="section-intro">각 화면 안을 스크롤해 전체 페이지를 살펴보세요. 이미지를 선택하면 확대됩니다.</p><div class="compare-tools"><div class="compare-modes" role="group" aria-label="비교 화면 선택"><button type="button" data-compare="both" aria-pressed="true">나란히</button><button type="button" data-compare="before" aria-pressed="false">개선 전</button><button type="button" data-compare="after" aria-pressed="false">개선 후</button></div><label><input type="checkbox" class="compare-sync"> 함께 스크롤</label></div><div class="comparison" data-mode="both"><article class="compare-panel" data-side="before"><h3 id="jeongango-before-title">개선 전 <span class="mono">기존안</span></h3><div class="compare-viewport" tabindex="0" role="region" aria-label="개선 전 상세페이지 스크롤 영역">{before}</div></article><article class="compare-panel" data-side="after"><h3 id="jeongango-after-title">개선 후 <span class="mono">개편안</span></h3><div class="compare-viewport" tabindex="0" role="region" aria-label="개선 후 상세페이지 스크롤 영역">{after}</div></article></div><div class="sales-evidence">{chart}</div></section>'''
    if key=='automation':
        image=old.select_one('#ai .studio-preview img')
        return f'<section class="case-section evidence"><div class="case-section-label mono">04 / 작업 화면</div><h2>경쟁사 레퍼런스 수집·분류 화면</h2><p class="section-intro">기존 포트폴리오에 공개된 실제 작업 화면입니다. 선택하면 확대할 수 있습니다.</p><figure class="wide-evidence">{material(image)}<figcaption>기존 공개 포트폴리오 / 경쟁사 광고 레퍼런스 수집·분류 자동화</figcaption></figure><h3 class="media-subhead">공개된 자동화 업무 범주</h3>{material(old.select_one("#ai .ai-cases"))}</section>'
    if key=='operations':
        return '<section class="case-section"><div class="case-section-label mono">04 / 운영 기록</div><h2>예산 판단부터 판매 전략까지</h2><div class="operation-record">'+''.join(material(old.find(id=x)) for x in ['career-profit','career-scaling','career-media','career-launch','career-analysis','career-review'])+'</div></section>'
    if key=='petbox':return '<section class="case-section"><div class="case-section-label mono">04 / 성과 지표</div><h2>광고비와 매출의 전후 변화</h2><div class="figure-matrix"><div><span>광고비</span><strong>440 → 220<small>만 원</small></strong></div><div><span>매출</span><strong>1,800 → 2,200<small>만 원</small></strong></div><div><span>금액 기준 ROAS</span><strong>409 → 1,000<small>%</small></strong></div></div></section>'
    if key=='optimust':return '<section class="case-section"><div class="case-section-label mono">04 / 원본 자료</div><h2>공개된 성과와 실행 기록</h2><div class="source-material">'+material(old.select_one('.optimust-case'))+'</div></section>'
    return ''

for i,f in enumerate(facts):
    source_link = ''
    if f.get('source'):
        source_link = f'''<a class="underlink" href="https://jowoohyung-portfolio.pages.dev{f['source']}" target="_blank" rel="noopener">기존 공개 자료에서 확인하기 ↗</a>'''
    actions=''.join(f'<li><span class="mono">0{n+1}</span><p>{E(a)}</p></li>' for n,a in enumerate(f['actions']))
    body=f'''<article class="case-page" data-project="{f['id']}"><a class="back-link mono" href="/#work">← 대표 작업</a><header class="case-hero"><p class="eyebrow mono">{E(f['category'])} / {E(f['name'])}</p><h1 style="view-transition-name:title-{f['id']}">{text(f['title'])}</h1><p class="case-summary">{E(f['summary'])}</p><dl class="case-facts"><div><dt>프로젝트</dt><dd>{E(f['name'])}</dd></div><div><dt>기간·기준</dt><dd>{E(f['period'])}</dd></div><div><dt>담당 역할</dt><dd>{E(f['role'])}</dd></div></dl></header><div class="case-metric"><strong>{E(f['metric'])}</strong><p>{E(f['metric_label'])}</p><span class="mono">{E(f.get("metric_heading","주요 성과"))}</span></div><div class="case-editorial"><section class="case-section"><div class="case-section-label mono">01 / 과제</div><h2>배경과 과제</h2><p>{E(f['problem'])}</p></section><section class="case-section"><div class="case-section-label mono">02 / 판단 기준</div><h2>무엇을 기준으로 판단했나</h2><p>{E(f['decision'])}</p></section><section class="case-section"><div class="case-section-label mono">03 / 실행 과정</div><h2>직접 실행한 일</h2><ol class="action-list">{actions}</ol></section>{case_media(f)}<section class="case-section case-result"><div class="case-section-label mono">05 / 결과</div><h2>확인된 결과와 해석</h2><p>{E(f['results'])}</p><aside class="result-context"><h3>수치를 읽는 기준</h3><p>{E(f['interpretation'])}</p></aside>{source_link}</section></div><nav class="case-next" aria-label="다음 프로젝트"><span class="mono">다음 프로젝트</span><a href="/projects/{facts[(i+1)%len(facts)]['id']}/">{E(facts[(i+1)%len(facts)]['name'])} <span>↗</span></a></nav></article>'''
    write(f'projects/{f["id"]}/index.html',shell(f['name'],body,'case',f['summary']))

companies=[]
for p in sorted((SOURCE/'portfolio').glob('*.html')):
    soup=BeautifulSoup(p.read_text(encoding='utf-8'),'html.parser')
    name=soup.h1.get_text(' ',strip=True)
    summary=soup.select_one('.dsum').get_text(' ',strip=True)
    logo=soup.select_one('.dlogo img')
    companies.append({'name':name,'summary':summary,'url':'/portfolio/'+p.name,'logo':logo.get('src') if logo else ''})
    blocks=soup.select('.dblock')
    text_blocks=''.join(material(b) for b in blocks)
    shots=soup.select('.shot')
    for shot in shots:
        if not shot.find_parent(class_='dblock'):text_blocks+=material(shot)
    body=f'''<article class="case-page data-case"><a class="back-link mono" href="/archive.html?category=data">← 데이터 구축 사례</a><header class="case-hero"><p class="eyebrow mono">데이터 수집과 분석</p><h1>{E(name)}</h1><p class="case-summary">{E(summary)}</p><dl class="case-facts"><div><dt>범위</dt><dd>원본에 공개된 해당 기업 구축 사례</dd></div><div><dt>수행 시점</dt><dd>개별 프로젝트 기간 미기재</dd></div><div><dt>기록</dt><dd>요청 배경 · 실행 내용 · 실제 화면</dd></div></dl></header><div class="case-editorial source-material evidence">{text_blocks}</div><div class="case-source"><a class="underlink" href="https://jowoohyung-portfolio.pages.dev/portfolio/{p.name}" target="_blank" rel="noopener">기존 공개 사례 ↗</a></div><nav class="case-next"><span class="mono">전체 데이터 구축 사례</span><a href="/archive.html?category=data">34개 기업 구축 사례 <span>↗</span></a></nav></article>'''
    if logo:
        body=body.replace('<h1>',f'<div class="case-client-logo">{material(logo)}</div><h1>',1)
    if '2023 캠페인' in soup.get_text(' ',strip=True):
        body=body.replace('개별 프로젝트 기간 미기재','2023 캠페인 페이지 포함 · 정확한 수행일 미기재',1)
    website=soup.select_one('.dlink')
    if website:
        website.string='기존 프로젝트의 참고 사이트 ↗'
        body=body.replace('<div class="case-editorial source-material evidence">',f'<div class="case-source company-source">{material(website)}</div><div class="case-editorial source-material evidence">',1)
    write('portfolio/'+p.name,shell(name+' 데이터 구축',body,'case',summary))

by_id = {project['id']: project for project in facts}
selected=[by_id['aerunb'],by_id['desillab'],by_id['binusoap'],by_id['mogrami'],{'id':'ncsoft','name':'NC소프트','category':'데이터 구축','title':'4개 언어의 클릭과 스크롤을\n분석할 수 있는 데이터로.','role':'GA4 · GTM · Looker Studio','metric':'4개 언어','metric_label':'공식 사이트 사용자 행동 데이터','cover':'/img/NC_1.jpg','url':'/portfolio/01.html'},by_id['automation']]
def row(f,i):
    url=f.get('url','/projects/'+f['id']+'/')
    is_concept = f.get('concept_cover')
    preview_label = f.get('cover_label', '분위기용 콘셉트 이미지' if is_concept else '실제 공개 작업 자료')
    caption = 'AI CONCEPT / 실제 결과물은 상세에서 확인' if is_concept else preview_label
    concept = f'<span class="concept-label mono">{E(caption)}</span>'
    return f'''<a class="work-row reveal" href="{url}" data-kind="{f['id']}" style="--row-index:{i}"><span class="work-number mono">0{i+1}</span><div class="work-row-copy"><span class="work-category mono">{E(f['category'])}</span><h3 style="view-transition-name:title-{f['id']}">{E(f['name'])}</h3><p>{text(f['title'])}</p><span class="work-role">담당 / {E(f['role'])}</span></div><div class="work-row-result"><strong>{E(f['metric'])}</strong><span>{E(f['metric_label'])}</span></div><span class="work-arrow" aria-hidden="true">↗</span><div class="row-preview"><img src="{f['cover']}" alt="{E(f['name'])} {E(preview_label)}" loading="lazy" width="700" height="550">{concept}</div></a>'''
rows=''.join(row(f,i) for i,f in enumerate(selected))
careers=''.join(f'<div class="career-row"><span class="mono">{a}</span><div><h3>{b}</h3><p>{c}</p></div></div>' for a,b,c in [('현재','에런비','광고 운영 자동화 · 자사몰 구매 행동 분석 · 콘텐츠 운영'),('2025.11–2026.10.07','바스케이션','마케팅팀장 · 브랜드별 광고 총괄과 팀 운영'),('2025','뉴메드엘앤비','쇼핑몰 오픈 · GA4·GTM · 업무 자동화'),('2022–2025','가치탐험단','프리랜서 · 기업 데이터 수집·시각화'),('2022–2023','브랜드리팩터링','옵티머스트 풀퍼널 마케팅'),('2021–2022','펫박스','네이버 검색광고 운영')])
home=f'''<section class="hero-track" id="home"><div class="hero-scene"><div class="scene-fallback" aria-hidden="true"><div class="fallback-knot">✳</div></div><canvas id="decision-field" aria-hidden="true"></canvas><div class="scene-grid" aria-hidden="true"></div><div class="hero-topline mono"><span>PERFORMANCE MARKETING · DATA · AUTOMATION</span><span>SEOUL / <time id="seoul-clock">KST</time></span></div><div class="scene-coordinate mono" aria-hidden="true"><span>DECISION FIELD_</span><span>OBSERVE / TEST / DECIDE</span><span class="scene-state">01 — CLOSE VIEW</span></div><div class="hero-copy"><p class="hero-name">조우형<span class="name-dot">.</span></p><div class="hero-statement"><p class="eyebrow mono">마케팅 팀장 포트폴리오</p><h1>광고비를 늘리기 전에,<br>팔릴 조건을 봅니다.</h1><p class="hero-role">광고 콘텐츠, 자사몰, 데이터, 자동화.<br>매출과 공헌이익, 공급 여건을 함께 살핀 마케터입니다.</p><a class="arrow-link" href="#work">실제로 바꾼 일 보기 <span>↘</span></a></div></div><div class="hero-baseline mono"><span>01 / 광고비를 늘리기 전의 판단</span><span>SCROLL TO CHANGE PERSPECTIVE ↓</span></div><div class="sound-invitation"><span>소리와 함께 둘러볼까요?</span><button type="button" data-sound-start>사운드 켜기 ↗</button><button type="button" data-sound-dismiss>무음으로 보기</button></div><button class="motion-toggle mono" type="button" aria-pressed="false">MOTION ON Ⅱ</button></div></section><section class="intro section"><div class="section-label"><span>01 / 일을 바라보는 관점</span><span>숫자가 좋아진 다음에도, 질문은 남습니다.</span></div><div class="intro-layout"><h2 class="section-title reveal">매출을 키우는 일과<br>계속 팔 수 있는 일.</h2><div class="body-copy reveal"><p>광고의 초기 반응이 좋을 때는 예산을 빠르게 늘렸습니다. 그다음에는 공헌이익과 재고, 출고 대응이 이를 뒷받침하는지 확인했습니다.</p><p>신제품의 일매출이 늘어난 뒤에도 재구매와 LTV가 충분한지 다시 봤습니다. 광고를 더 집행하는 것과 판매 전략을 바꾸는 것 사이에서 판단해 온 경험입니다.</p><a class="underlink" href="/projects/operations/">당시의 운영 기준 읽기 ↗</a></div></div><div class="scope-strip"><div><span class="mono">광고와 커머스</span><strong>5개</strong><p>브랜드 동시 운영 경험</p></div><div><span class="mono">데이터 구축</span><strong>34개사</strong><p>기업 데이터 구축 사례</p></div><div><span class="mono">업무 자동화</span><strong>15종</strong><p>공개된 업무 자동화 수</p></div></div></section><section class="selected section" id="work"><div class="section-label"><span>02 / 대표 작업</span><span>문제 · 판단 · 실행 · 확인된 결과</span></div><div class="work-heading"><h2 class="section-title reveal">광고·구매·데이터.<br>직접 바꾼 일들<span class="violet">_</span></h2><p>실제 역할과 자료,<br>각 수치를 읽는 기준까지 담았습니다.</p></div><div class="work-rows">{rows}</div><div class="section-end"><span class="mono">대표 작업 {len(selected)}건</span><a class="underlink" href="/archive.html">전체 작업 아카이브 ↗</a></div></section><section class="data-section section" id="data"><div class="section-label"><span>03 / 데이터와 자동화</span><span>GA4 · GTM · LOOKER STUDIO · AI</span></div><div class="data-title"><h2 class="section-title reveal">수집된 숫자를<br>판단할 수 있는 상태로.</h2><p>사이트마다 구조와 질문이 달랐습니다.<br>수집 설계, 정합성 검증, 시각화와 해석을<br>각 기업의 상황에 맞게 진행했습니다.</p></div><div class="data-feature"><a href="/portfolio/01.html" class="data-screen evidence-link"><img src="/img/NC_1.jpg" alt="NC소프트 프로젝트의 실제 보고서 작업 화면" width="1400" height="900" loading="lazy"><span class="mono">NC소프트 작업 화면 ↗</span></a><div class="data-feature-copy"><span class="eyebrow mono">34개 기업의 데이터 구축 사례</span><h3>같은 도구를 써도,<br>설계는 달라집니다.</h3><p>NC소프트에서는 4개 언어 사이트의 클릭·스크롤 수집과 국가별 보고서를 만들었습니다. 정관장에서는 배너·프로모션·카테고리 전 구간의 전자상거래 수집 환경을 구축했습니다.</p><a class="underlink" href="/archive.html?category=data">기업별 구축 사례 탐색 ↗</a><a class="underlink" href="/projects/automation/">업무 자동화와 실제 화면 ↗</a></div></div><div class="client-names">{''.join(f'<a href="{c["url"]}">{E(c["name"])} <span>↗</span></a>' for c in companies[:7])}<a href="/archive.html?category=data">전체 34개사 <span>↗</span></a></div></section><section class="approach section" id="approach"><div class="section-label"><span>04 / 운영 기준</span><span>실제 운영 기록에서 가져온 기준입니다.</span></div><div class="approach-layout"><div><h2 class="section-title reveal">테스트는 빠르게.<br>증액은 근거 있게.</h2><p class="approach-note">아래 수치는 당시 사용한 예시입니다.<br>객단가·마진·시장 CPM에 맞춰 탄력적으로 적용했습니다.</p><a class="underlink" href="/projects/operations/">전체 운영 판단과 판매 전략 ↗</a></div><div class="principles"><details open><summary><span class="mono">01</span>초기 소재는 어떻게 걸렀나<span>＋</span></summary><div><p>CPC 1,200원 이하, CPM 15,000원 이하를 초기 선별에 활용했습니다. 최종 증액은 매출·ROAS·공헌이익을 확인한 뒤 결정했습니다.</p><a href="/projects/operations/#career-scaling">당시 증액 기준 ↗</a></div></details><details><summary><span class="mono">02</span>광고 다음의 구매 과정을 봤나<span>＋</span></summary><div><p>옵티머스트에서는 고령 고객이 구매 옵션을 선택할 때 이탈하는 것을 확인했습니다. 옵션별로 상품을 분리하는 개선을 진행했습니다.</p><a href="/projects/optimust/">구매 옵션과 데이터 개선 ↗</a></div></details><details><summary><span class="mono">03</span>매출이 늘어난 뒤에는 무엇을 봤나<span>＋</span></summary><div><p>신제품의 일매출이 늘어난 뒤 재구매율과 LTV를 다시 판단했습니다. CRM 이후에도 한계가 있다고 보고 국내 판매 축소와 해외 판매 중심 전환을 결정했습니다.</p><a href="/projects/operations/#career-launch">제품 성장 이후의 판단 ↗</a></div></details><details><summary><span class="mono">04</span>팀은 어떤 기준으로 움직였나<span>＋</span></summary><div><p>브랜드별 매출 목표와 KPI, 업무 우선순위를 관리했습니다. 보고 체계와 업무 매뉴얼을 정리하고 반복 수집·보고를 자동화했습니다.</p><a href="/projects/operations/">광고 총괄과 팀 운영 ↗</a></div></details></div></div></section><section class="about section" id="about"><div class="section-label"><span>05 / 조우형 소개</span><span>기획하고, 실행하고, 결과를 다시 읽습니다.</span></div><div class="about-layout"><div><p class="about-name reveal">조우형<span class="violet">_</span></p><p class="about-english mono">PERFORMANCE MARKETING LEAD</p><div class="body-copy"><p>현재 에런비에서 광고 소재별 성과와 자사몰 구매 행동을 분석하고, 팀의 광고·콘텐츠 운영을 자동화하고 있습니다. 바스케이션에서는 여러 브랜드의 광고를 총괄하고 팀의 목표와 업무 우선순위를 관리했습니다.</p><p>팀으로 매출 두 배라는 목표를 달성한 경험이 있습니다. 최종 ROAS는 목표 270%에 못 미친 263%였습니다. 성과와 아쉬운 지점을 함께 기록하고, 다음 판단의 기준으로 삼습니다.</p></div></div><div class="career-list">{careers}<p class="career-footnote">프리랜서 프로젝트는 재직 기간과 일부 겹칩니다.<br>경력과 수치는 기존 공개 포트폴리오를 기준으로 편집했습니다.</p></div></div></section>'''
write('index.html',shell('운영과 판단, 조우형',home))

archive_rows=[]
automation_count = sum(f.get("archive_category") == "automation" for f in facts)
marketing_count = len(facts) - automation_count
for f in facts:
    cat = f.get('archive_category', 'marketing')
    search_text = ' '.join([f['name'], f['category'], *f.get('search_terms', [])])
    archive_rows.append(f'<a class="archive-row" href="/projects/{f["id"]}/" data-category="{cat}" data-search="{E(search_text)}"><span class="mono">{E(f["category"])}</span><div><h2>{E(f["name"])}</h2><p>{E(f["summary"])}</p></div><span aria-hidden="true">↗</span></a>')
for c in companies:
    archive_rows.append(f'<a class="archive-row" href="{c["url"]}" data-category="data" data-search="{E(c["name"]+" GA4 GTM 데이터 Looker Studio")}"><span class="mono">데이터 분석</span><div><h2>{E(c["name"])}</h2><p>{E(c["summary"])}</p></div><span aria-hidden="true">↗</span></a>')
archive=f'''<article class="archive-page section"><div class="section-label"><span>전체 작업</span><span>마케팅 / 데이터 / 자동화</span></div><h1 class="section-title">실행의 기록<span class="violet">_</span></h1><p class="archive-intro">광고 콘텐츠와 운영 판단 {marketing_count}개, 업무 자동화 {automation_count}개, 기업 데이터 구축 {len(companies)}개.<br>각 사례의 배경과 실제 자료를 살펴보세요.</p><div class="archive-controls"><div role="group" aria-label="작업 분야"><button type="button" data-filter="all" aria-pressed="true">전체 <span>{len(archive_rows)}</span></button><button type="button" data-filter="marketing" aria-pressed="false">마케팅 <span>{marketing_count}</span></button><button type="button" data-filter="data" aria-pressed="false">데이터 <span>{len(companies)}</span></button><button type="button" data-filter="automation" aria-pressed="false">자동화 <span>{automation_count}</span></button></div><label class="search-label"><span class="sr-only">프로젝트 검색</span><input type="search" id="project-search" placeholder="기업명·작업 검색" autocomplete="off"><span aria-hidden="true">⌕</span></label></div><p id="archive-count" class="mono" role="status" aria-live="polite">{len(archive_rows)}개의 작업</p><div class="archive-list">{''.join(archive_rows)}</div><p class="no-results" hidden>검색 결과가 없습니다. 다른 기업명이나 작업으로 찾아보세요.</p></article>'''
write('archive.html',shell('전체 작업 아카이브',archive,'archive'))
video_source=BeautifulSoup((SOURCE/'contents.html').read_text(encoding='utf-8'),'html.parser')
video_cards=[]
for i,v in enumerate(video_source.select('video')):
    v['controls']='';v['playsinline']='';v['preload']='none'
    v['aria-label']=f'기존 공개 광고 영상 {i+1:02d}'
    video_cards.append(f'<figure class="brand-creative">{v}<figcaption>공개 영상 {i+1:02d}<span>역할·성과 기준은 해당 프로젝트에서 확인해 주세요.</span></figcaption></figure>')
video_page='<article class="archive-page section"><div class="section-label"><span>공개 광고 영상</span><a href="/archive.html">작업 아카이브 ↗</a></div><h1 class="section-title">실제 광고 콘텐츠<span class="violet">_</span></h1><p class="archive-intro">기존 영상 모음에 공개된 '+str(len(video_cards))+'개의 원본 영상입니다.<br>재생할 영상을 선택해 주세요. 동시에 여러 영상이 재생되지 않도록 조절합니다.</p><div class="brand-creatives video-library">'+''.join(video_cards)+'</div></article>'
write('contents.html',shell('공개 광고 영상 모음',video_page,'library'))
# The full video library remains reachable, including clips outside the five featured cases.
archive_path=ROOT/'archive.html'
archive_html=archive_path.read_text(encoding='utf-8').replace('<div class="archive-controls">','<a class="underlink library-link" href="/contents.html">공개 광고 영상 '+str(len(video_cards))+'개 모아보기 ↗</a><div class="archive-controls">',1)
archive_path.write_text(archive_html,encoding='utf-8')
legacy={'planning':'/#work','viral':'/projects/mogrami/','data':'/archive.html?category=data','performance':'/projects/operations/','commerce':'/projects/binusoap/','leadership':'/#about','career':'/#about','contact':'/#contact','portfolio':'/archive.html'}
for name,target in legacy.items():
    write(name+'.html',f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="0;url={E(target)}"><title>조우형 포트폴리오 V2</title></head><body><a href="{E(target)}">포트폴리오로 이동하기</a></body></html>')
work_redirect='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>조우형 포트폴리오 V2</title><script>const routes={'#ai':'/projects/automation/','#planning':'/#work','#case-desillab':'/projects/desillab/','#case-binusoap':'/projects/binusoap/','#case-mogrami':'/projects/mogrami/','#data':'/archive.html?category=data','#career':'/#about','#petbox':'/projects/petbox/','#optimust-title':'/projects/optimust/'};location.replace(routes[location.hash]||'/archive.html');</script></head><body><a href="/archive.html">전체 작업 아카이브로 이동하기</a></body></html>'''
write('work.html',work_redirect)
write('404.html',shell('페이지를 찾을 수 없습니다','<section class="archive-page section"><p class="eyebrow mono">404 / 페이지를 찾을 수 없습니다</p><h1 class="section-title">찾는 페이지가 없습니다.</h1><p class="archive-intro">아래에서 전체 작업을 살펴보세요.</p><a class="underlink" href="/archive.html">전체 작업 아카이브 ↗</a></section>','404'))
(ROOT/'research/companies.json').write_text(json.dumps(companies,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'Built V2 home, {len(facts)} narrative case studies, {len(companies)} data details and searchable archive.')

if __name__=='__main__':pass
