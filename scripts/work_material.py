from pathlib import Path
from bs4 import BeautifulSoup
import json

ROOT = Path(__file__).resolve().parents[1]
old = BeautifulSoup((ROOT/'source/work.html').read_text(encoding='utf-8'), 'html.parser')
evidence = json.loads((ROOT/'research/evidence-map.json').read_text(encoding='utf-8'))
media_map = {entry['source_url']: entry for entry in evidence}

def material(tag):
    if tag is None:return ''
    copy=BeautifulSoup(str(tag),'html.parser')
    for img in copy.select('img'):
        if img.get('src') in media_map:
            entry=media_map[img['src']];img['data-original']=img['src'];img['src']=entry['local_url']
        img['loading']='lazy';img['decoding']='async'
    for v in copy.select('video'):v['preload']='none';v['playsinline']='';v['controls']=''
    for hidden in copy.select('[hidden]'):hidden.decompose()
    return str(copy)

def case_media(f):
    key=f['id']
    if key in ['desillab','mogrami']:
        a=old.find(id='case-'+key)
        videos=material(a.select_one('.brand-creatives'))
        detail=material(a.select_one('.brand-detail-preview')) if key=='desillab' else ''
        more=material(a.select_one('.mogrami-ppl')) if key=='mogrami' else ''
        return f'<section class="case-section evidence"><div class="case-section-label mono">04 / ACTUAL WORK</div><h2>실제 집행한 광고 소재</h2><p class="section-intro">영상을 선택하면 재생됩니다. 프로젝트 영상에 소리가 있으면 배경음은 자동으로 작아집니다.</p>{videos}{more}'+(f'<h3 class="media-subhead">고추장버터 상세페이지</h3><p class="section-intro">이미지를 선택하면 원본 크기로 볼 수 있습니다.</p><div class="detail-material">{detail}</div>' if detail else '')+'</section>'
    if key=='binusoap':
        a=old.find(id='case-binusoap')
        before=material(a.select_one('.comparison-before .brand-detail-preview'))
        after=material(a.select_one('.comparison-after .brand-detail-preview'))
        chart=material(a.select_one('.brand-sales-chart'))
        return f'''<section class="case-section evidence"><div class="case-section-label mono">04 / BEFORE & AFTER</div><h2>상세페이지 전후 비교</h2><p class="section-intro">각 화면 안을 스크롤해 전체 페이지를 살펴보세요. 이미지를 선택하면 확대됩니다.</p><div class="compare-tools"><div class="compare-modes" role="group" aria-label="비교 화면 선택"><button type="button" data-compare="both" aria-pressed="true">나란히</button><button type="button" data-compare="before" aria-pressed="false">개선 전</button><button type="button" data-compare="after" aria-pressed="false">개선 후</button></div><label><input type="checkbox" class="compare-sync"> 함께 스크롤</label></div><div class="comparison" data-mode="both"><article class="compare-panel" data-side="before"><h3 id="jeongango-before-title">개선 전 <span class="mono">BEFORE</span></h3><div class="compare-viewport" tabindex="0" role="region" aria-label="개선 전 상세페이지 스크롤 영역">{before}</div></article><article class="compare-panel" data-side="after"><h3 id="jeongango-after-title">개선 후 <span class="mono">AFTER</span></h3><div class="compare-viewport" tabindex="0" role="region" aria-label="개선 후 상세페이지 스크롤 영역">{after}</div></article></div><div class="sales-evidence">{chart}</div></section>'''
    if key=='automation':
        image=old.select_one('#ai .studio-preview img')
        return f'<section class="case-section evidence"><div class="case-section-label mono">04 / ACTUAL SCREEN</div><h2>경쟁사 레퍼런스 수집·분류 화면</h2><p class="section-intro">기존 포트폴리오에 공개된 실제 작업 화면입니다. 선택하면 확대할 수 있습니다.</p><figure class="wide-evidence">{material(image)}<figcaption>기존 공개 포트폴리오 / 경쟁사 광고 레퍼런스 수집·분류 자동화</figcaption></figure><h3 class="media-subhead">공개된 자동화 업무 범주</h3>{material(old.select_one("#ai .ai-cases"))}</section>'
    if key=='operations':
        return '<section class="case-section"><div class="case-section-label mono">04 / OPERATING RECORD</div><h2>예산 판단부터 판매 전략까지</h2><div class="operation-record">'+''.join(material(old.find(id=x)) for x in ['career-profit','career-scaling','career-media','career-launch','career-analysis','career-review'])+'</div></section>'
    if key=='petbox':return '<section class="case-section"><div class="case-section-label mono">04 / RECORDED FIGURES</div><h2>광고비와 매출의 전후 변화</h2><div class="figure-matrix"><div><span>광고비</span><strong>440 → 220<small>만 원</small></strong></div><div><span>매출</span><strong>1,800 → 2,200<small>만 원</small></strong></div><div><span>금액 기준 ROAS</span><strong>409 → 1,000<small>%</small></strong></div></div></section>'
    if key=='optimust':return '<section class="case-section"><div class="case-section-label mono">04 / ORIGINAL RECORD</div><h2>공개된 성과와 실행 기록</h2><div class="source-material">'+material(old.select_one('.optimust-case'))+'</div></section>'
    return ''
