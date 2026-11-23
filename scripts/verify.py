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
archive=docs[(dist/'archive.html').resolve()]
rows=archive.select('.archive-row')
if len(rows)!=42:errors.append(f'Archive count mismatch: {len(rows)}')
if sum(r.get('data-category')=='data' for r in rows)!=34:errors.append('Data archive count mismatch')
facts=json.loads((root/'content/projects.json').read_text(encoding='utf-8'))
if len(facts)!=8:errors.append('Narrative case count mismatch')
for button in archive.select('button[data-filter]'):
    group=button['data-filter']
    expected=len(rows) if group=='all' else sum(r.get('data-category')==group for r in rows)
    if button.span.get_text(strip=True)!=str(expected):errors.append(f'Archive filter count mismatch: {group}')
mapping=json.loads((root/'research/evidence-map.json').read_text(encoding='utf-8'))
for item in mapping:
    if not (dist/item['local_url'].lstrip('/')).is_file():errors.append('Comparison source missing: '+item['local_url'])
source=BeautifulSoup((root/'source/contents.html').read_text(encoding='utf-8'),'html.parser')
library=docs[(dist/'contents.html').resolve()]
def video_refs(s):return set(v.get('src') for v in s.select('video[src],source[src]'))
if not video_refs(source).issubset(video_refs(library)):errors.append('Original video library omitted a source')
sound = json.loads((dist / 'audio/source.json').read_text(encoding='utf-8'))
track = dist / 'audio' / sound['file']
if not track.is_file() or hashlib.sha256(track.read_bytes()).hexdigest() != sound['sha256']:
    errors.append('Background music missing or different from the supplied file')
if f"/audio/{sound['file']}" not in (dist / 'js/sound.js').read_text(encoding='utf-8'):
    errors.append('Sound player does not point to the verified music file')
result={'public_html_pages':len(docs),'narrative_cases':len(facts),'data_cases':34,'archive_entries':len(rows),'comparison_originals':len(mapping),'video_library_clips':len(library.select('video')),'sound':sound,'errors':errors}
(root/'research/static-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
raise SystemExit(bool(errors))
