"""Render a single readable document with native disclosures and stable fragment URLs."""
from html import escape
from pathlib import Path
import json
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from scripts.work_material import case_media, material

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source'
PROJECTS = json.loads((ROOT / 'content/projects.json').read_text(encoding='utf-8'))
GLOSSARY = {
    'GA4': '구글 애널리틱스 4', 'GTM': '구글 태그 관리자', 'UA': '이전 버전 분석 도구',
    'ROAS': '광고비 대비 매출', 'CPC': '클릭당 비용', 'CPM': '천 회 노출당 비용',
    'LTV': '고객 생애 가치', 'A/B': '비교', 'PPL': '간접광고', 'ABO': '광고세트 예산',
    'CBO': '캠페인 예산', 'CRM': '고객 관계 관리', 'CS': '고객 응대', 'RS': '수익 배분',
    'OFF': '중단', 'CTR': '클릭률', 'CVR': '전환율', 'AI': '인공지능', 'USP': '차별점',
    'AARRR': '고객 여정 단계', 'UTM': '유입 경로 식별값', 'iframe': '내부 삽입 문서',
    'Looker Studio': '루커 스튜디오', 'KPI': '핵심 성과 지표', 'GA': '구글 애널리틱스',
    'META · 01 / TEST': '메타 소재 테스트', 'META · 02 / SCALE': '메타 예산 확대',
    'GOOGLE ADS': '구글 광고', 'TIKTOK ADS': '틱톡 광고', 'Google Ads': '구글 광고',
    'TikTok': '틱톡', 'Meta': '메타', 'NC PLAY NOVEL': '엔씨 플레이 노블',
    'NC MONSTER': '엔씨 몬스터', 'NC FICTION PLAY': '엔씨 픽션 플레이',
    'NC소프트': '엔씨소프트', 'LG전자': '엘지전자', 'ICBANQ': '아이씨뱅큐',
    'LNC': '엘엔씨', 'CANADA GOOSE': '캐나다구스', 'RUMTTON': '럼튼',
    'DESSERTCO': '디저트코', 'BAROWEB': '바로웹', 'VPK': '브이피케이',
    'SAMSUNG': '삼성글로벌네트웍스', '셋팅': '설정', '런칭': '출시',
}
TOKENS = re.compile('|'.join(re.escape(k) for k in sorted(GLOSSARY, key=len, reverse=True)))
def ko(value):
    translated = TOKENS.sub(lambda m: GLOSSARY[m[0]], value)
    for old, new in (
        ('광고비 대비 매출는','광고비 대비 매출은'), ('광고비 대비 매출를','광고비 대비 매출을'),
        ('클릭당 비용가','클릭당 비용이'), ('고객 관계 관리을','고객 관계 관리를'),
        ('내부 삽입 문서으로','내부 삽입 문서로'), ('차별점가','차별점이'), ('출시과','출시와'),
        ('개별 수행 기간 미기재','개별 수행 시점 미기재'),
        ('소재 미러링','소재 재활용'), ('사용자 퍼널','사용자 행동 단계'),
    ):
        translated = translated.replace(old,new)
    return translated

def esc(value):
    return escape(ko(value))

def prepare(fragment):
    soup = BeautifulSoup(fragment, 'html.parser')
    for node in soup.select('.case-section-label, .compare-panel h3 .mono'):
        node.decompose()
    for node in list(soup.find_all(string=True)):
        if node.parent and node.parent.name not in ('script', 'style'):
            if re.fullmatch(r'[A-Z &·]+', node.strip()) and len(node.strip()) > 5 and node.strip() not in GLOSSARY:
                node.replace_with('')
            else:
                node.replace_with(ko(str(node)))
    for tag in soup.select('[alt], [aria-label]'):
        for attr in ('alt', 'aria-label'):
            if tag.has_attr(attr):
                tag[attr] = ko(tag[attr])
    for video in soup.select('video'):
        video.attrs.update(preload='none', playsinline='', controls='')
    for img in soup.select('img'):
        img['loading'] = 'lazy'
        if not img.find_parent('a'):
            link = soup.new_tag('a', href=img['src'])
            link['class'] = 'enlarge'
            link['aria-label'] = (img.get('alt') or '작업 이미지') + ' 확대'
            img.wrap(link)
    return str(soup)

# Headlines describe a concrete decision. Results keep the source's comparison period.
TITLES = {
    'desillab': '고추장버터를 어떻게 먹는지부터 보여줬습니다.',
    'binusoap': '정안고의 상세페이지를 바꾸고 월별 매출을 확인했습니다.',
    'mogrami': '광고 소재와 채널 협업의 성과를 따로 측정했습니다.',
    'operations': '매출과 공헌이익을 보고 다섯 브랜드의 예산을 조정했습니다.',
    'automation': '광고 수집과 매출 보고를 자동화했습니다.',
    'petbox': '검색광고비를 절반으로 줄이면서 매출을 높였습니다.',
    'optimust': '고령 고객이 어려워한 구매 옵션을 나눴습니다.',
}
ORDER = ('desillab', 'binusoap', 'mogrami', 'operations', 'automation', 'petbox', 'optimust')
NAMES = {'operations':'바스케이션', 'binusoap':'천비누솝', 'optimust':'옵티머스트'}
RESULTS = {
    'desillab':'출시 직후 일매출 600만 원',
    'binusoap':'5월 대비 8월 매출 95% 이상 증가',
    'mogrami':'이수근 채널 협업의 광고비 대비 매출 288%',
    'operations':'신제품 출시 3개월 후 일매출 약 1,000만 원',
    'automation':'광고·커머스 반복 업무 15종 자동화',
    'petbox':'광고비 440만 → 220만 원 · 매출 1,800만 → 2,200만 원',
    'optimust':'매출 데이터 오차율 30% → 5%',
}
# Normalized bars compare like units within each recorded series.
MINI_CHARTS = {
    'operations': ('신제품 일매출', [('2주', '400만 원', 40), ('1개월', '700만 원', 70), ('3개월', '1,000만 원', 100)]),
    'petbox': ('검색광고비', [('개선 전', '440만 원', 100), ('개선 후', '220만 원', 50)]),
    'optimust': ('매출 데이터 오차율', [('개선 전', '30%', 100), ('개선 후', '5%', 16.7)]),
}

def mini_chart(key):
    caption, bars = MINI_CHARTS[key]
    rows = ''.join(f'<div><span>{label}</span><i style="--length:{length}%"></i><b>{value}</b></div>' for label,value,length in bars)
    return f'<div class="mini-chart"><strong>{caption}</strong>{rows}</div>'

def case(f):
    key = f['id']
    actions = ''.join(f'<li>{esc(a)}</li>' for a in f['actions'])
    cover = f.get('cover') if key in ('desillab','binusoap','mogrami','automation') else None
    artwork = (f'<img src="{cover}" loading="lazy" alt="{esc(f["name"])} 작업 이미지">' if cover else
               mini_chart(key))
    return f'''<article class="case-sheet" id="{key}"><div class="case-face">
    <figure class="case-thumb">{artwork}</figure><div class="case-head">
    <p class="case-name">{esc(f['name'])}</p><h3>{TITLES[key]}</h3>
    <p class="case-role">담당 · {esc(f['role'])} <span>·</span> {esc(f['period'])}</p>
    <p class="case-outcome">{RESULTS[key]}</p></div></div>
    <details class="case-more"><summary>판단 과정과 작업물 <span class="plus" aria-hidden="true"></span></summary>
    <div class="case-body"><div class="case-prose"><h4>과제</h4><p>{esc(f['problem'])}</p>
    <h4>판단 기준</h4><p>{esc(f['decision'])}</p><h4>직접 한 일</h4><ul>{actions}</ul></div>
    {prepare(case_media(f))}
    <div class="case-prose interpretation"><h4>결과를 읽는 기준</h4><p>{esc(f['results'])}</p><p>{esc(f['interpretation'])}</p></div>
    </div></details></article>'''

def companies():
    entries = []
    common = None
    routes = {}
    for p in sorted((SOURCE/'portfolio').glob('*.html')):
        s = BeautifulSoup(p.read_text(encoding='utf-8'), 'html.parser')
        name = s.h1.get_text(' ',strip=True)
        intro = s.select_one('.dsum').get_text(' ',strip=True)
        blocks = []
        for node in s.select('.dblock,.shot'):
            if node.find_parent(class_='dblock'):
                continue
            heading = node.select_one('.dh')
            if heading and heading.get_text(strip=True)=='공통 작업 범위':
                if common is None:
                    heading.decompose()
                    common = prepare(material(node))
                continue
            blocks.append(material(node))
        website = s.select_one('a.dlink')
        origin = ''
        if website and urlsplit(website.get('href','')).scheme in ('http','https'):
            origin = f'<a class="text-link" href="{escape(website["href"])}" target="_blank" rel="noopener">기업 참고 사이트 ↗</a>'
        logo = s.select_one('.dlogo img')
        mark = f'<img loading="lazy" src="{escape(logo["src"])}" alt="">' if logo else ''
        target = 'company-'+p.stem
        routes['portfolio/'+p.name] = target
        entries.append(f'''<details class="company" id="{target}" data-search="{escape(name+' '+ko(name)+' '+intro+' '+ko(intro),quote=True)}">
        <summary>{mark}<span><b>{esc(name)}</b><span>{esc(intro)}</span></span><i class="plus" aria-hidden="true"></i></summary>
        <div class="company-body source-material evidence">{prepare(''.join(blocks))}{origin}</div></details>''')
    shared = f'<details class="common"><summary>기업별 구축에 공통으로 적용한 일 <i class="plus"></i></summary><div class="source-material">{common}</div></details>'
    return ''.join(entries), shared, routes

CAREERS = [
    ('2025.11–2026.10.07','바스케이션','마케팅팀장 · 브랜드별 광고 총괄과 팀 운영'),
    ('2025','뉴메드엘앤비','쇼핑몰 개설, 데이터 수집 환경 구축, 업무 자동화'),
    ('2022–2025','가치탐험단','프리랜서 · 기업별 측정 설계, 데이터 검증과 시각화'),
    ('2022–2023','브랜드리팩터링','옵티머스트 광고와 구매 과정 개선'),
    ('2021–2022','펫박스','네이버 검색광고 운영'),
]

def redirect(path, target):
    to = '/#' + target
    script = 'location.replace('+json.dumps(to)+');'
    if path in ('work.html','archive.html') or path.startswith('projects/'):
        # Keep previously shared project, section and search links usable.
        script = f"""const known={json.dumps(OLD_HASHES)}; const hash=location.hash.slice(1);
        const q=new URLSearchParams(location.search);
        const valid={json.dumps(DEEP_IDS)};
        const id=known[hash]|| (valid.includes(hash)?hash:'') ||(q.get('category')==='data'||q.has('q')?'data':'{target}');
        const query=q.get('q');location.replace('/'+(query?'?q='+encodeURIComponent(query):'')+'#'+encodeURIComponent(id));"""
    out = f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>조우형 포트폴리오</title><script>{script}</script><noscript><meta http-equiv="refresh" content="0;url={to}"></noscript><a href="{to}">해당 내용으로 이동</a></html>'
    (ROOT/path).write_text(out+'\n',encoding='utf-8')

OLD_HASHES = {'ai':'automation','career':'about','case-desillab':'desillab','case-binusoap':'binusoap','case-mogrami':'mogrami','career-ad-operations':'operations','optimust-title':'optimust','planning':'work'}
DEEP_IDS = []

def build():
    listing, shared, routes = companies()
    by_key = {f['id']:f for f in PROJECTS}
    films = BeautifulSoup((SOURCE/'contents.html').read_text(encoding='utf-8'),'html.parser')
    videos = []
    for i,v in enumerate(films.select('video'),1):
        v['aria-label'] = f'광고 영상 {i}'
        videos.append(f'<figure>{prepare(str(v))}<figcaption>광고 영상 {i}</figcaption></figure>')
    fields = {
        'CASE_INDEX': ''.join(f'<a href="#{k}">{esc(NAMES.get(k,by_key[k]["name"]))}</a>' for k in ORDER),
        'CASES': ''.join(case(by_key[k]) for k in ORDER),
        'COMMON': shared, 'COMPANIES': listing, 'VIDEOS': ''.join(videos),
        'CAREERS': ''.join(f'<div><time>{a}</time><section><h3>{b}</h3><p>{c}</p></section></div>' for a,b,c in CAREERS),
    }
    page = (ROOT/'templates/portfolio.html').read_text(encoding='utf-8')
    for key,value in fields.items():
        page = page.replace('{{'+key+'}}',value)
    (ROOT/'index.html').write_text(page,encoding='utf-8')
    DEEP_IDS[:] = [el['id'] for el in BeautifulSoup(page,'html.parser').select('[id]')]
    routes.update({f'projects/{k}/index.html':k for k in ORDER})
    routes.update({k+'.html':v for k,v in {
        'planning':'work','viral':'mogrami','data':'data','performance':'operations','commerce':'binusoap',
        'leadership':'about','career':'about','contact':'contact','portfolio':'data','archive':'work',
        'work':'work','contents':'film-collection'}.items()})
    for path,target in routes.items():
        redirect(path,target)
    (ROOT/'404.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>페이지를 찾을 수 없습니다</title><h1>페이지를 찾을 수 없습니다.</h1><a href="/">조우형 포트폴리오 보기</a></html>',encoding='utf-8')
    print('Built one portfolio with 7 marketing and automation cases, 34 companies and 16 videos.')
