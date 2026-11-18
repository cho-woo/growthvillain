"""Check public file references, anchors, labels, duplicate IDs and preserved evidence."""
from pathlib import Path
from urllib.parse import urlsplit, unquote
from collections import Counter
from bs4 import BeautifulSoup
import json, hashlib

root=Path(__file__).resolve().parents[1];dist=root/'dist'
docs={p.resolve():BeautifulSoup(p.read_text(encoding='utf-8'),'html.parser') for p in dist.rglob('*.html')}
errors=[]
for p,soup in docs.items():
    name=p.relative_to(dist.resolve()).as_posix()
    ids=[x['id'] for x in soup.select('[id]')]
    for value,count in Counter(ids).items():
        if count>1:errors.append(f'{name}: duplicate id {value}')
    for image in soup.select('img'):
        if not image.has_attr('alt'):errors.append(f'{name}: image without alt')
    for element in soup.select('[src],a[href],video[poster],link[href]'):
        attr='poster' if element.name=='video' and element.has_attr('poster') else 'src' if element.has_attr('src') else 'href'
        value=element.get(attr,'');url=urlsplit(value)
        if not value or url.scheme or url.netloc:continue
        if url.path.startswith('//'):continue
        target=(dist/unquote(url.path).lstrip('/')) if url.path.startswith('/') else (p.parent/unquote(url.path)) if url.path else p
        if target.is_dir():target=target/'index.html'
        if not target.exists():errors.append(f'{name}: missing {value}');continue
        target_doc=docs.get(target.resolve())
        if url.fragment and target_doc and not target_doc.find(id=unquote(url.fragment)):errors.append(f'{name}: missing anchor {value}')
    for e in soup.select('[aria-labelledby],[aria-controls]'):
        for attr in ['aria-labelledby','aria-controls']:
            for value in e.get(attr,'').split():
                if not soup.find(id=value):errors.append(f'{name}: unresolved {attr} {value}')
    if soup.body and soup.body.get('data-page') in ['home','case','archive','library']:
        if len(soup.select('h1'))!=1:errors.append(f'{name}: expected one main heading')
for p in dist.rglob('*'):
    if p.is_file() and p.stat().st_size>=25*1024*1024:errors.append(f'Cloudflare file size exceeded: {p.relative_to(dist)}')
home = docs[(dist/'index.html').resolve()]
if len(home.select('main h1')) != 1:
    errors.append('Single document requires one primary heading')
rows = home.select('.case-sheet, .company')
cases = home.select('.case-sheet')
companies = home.select('.company')
films = home.select('#film-collection video')
if len(rows) != 41 or len(cases) != 7 or len(companies) != 34:
    errors.append('One-page portfolio is missing a project')
for link in home.select('a[href]'):
    parsed = urlsplit(link['href'])
    if not parsed.scheme and not parsed.netloc and parsed.path and not parsed.path.startswith('/img/'):
        errors.append('Internal navigation must stay in the document: ' + link['href'])
mapping = json.loads((root/'research/evidence-map.json').read_text(encoding='utf-8'))
images = {img['src'] for img in home.select('.comparison img[src]')}
if images != {row['local_url'] for row in mapping}:
    errors.append('Missing comparison evidence in the single document')
source = BeautifulSoup((root/'source/contents.html').read_text(encoding='utf-8'),'html.parser')
def video_refs(s):
    return {v['src'] for v in s.select('video[src], video source[src]')}
if len(films) != 16 or video_refs(source) != video_refs(home.select_one('#film-collection')):
    errors.append('Single-page video library mismatch')
for redirect in dist.glob('projects/*/index.html'):
    expected = '/#' + redirect.parent.name
    if not docs[redirect.resolve()].find('a', href=expected):
        errors.append('Legacy project URL missing target: ' + expected)
sound = json.loads((dist / 'audio/source.json').read_text(encoding='utf-8'))
track = dist / 'audio' / sound['file']
if not track.is_file() or hashlib.sha256(track.read_bytes()).hexdigest() != sound['sha256']:
    errors.append('Background music missing or different from the supplied file')
if f"/audio/{sound['file']}" not in (dist / 'js/sound.js').read_text(encoding='utf-8'):
    errors.append('Sound player does not point to the verified music file')
result={'public_html_pages':len(docs),'narrative_cases':len(cases),'data_cases':34,'archive_entries':len(rows),'comparison_originals':len(mapping),'video_library_clips':len(films),'sound':sound,'errors':errors}
(root/'research/static-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
raise SystemExit(bool(errors))
