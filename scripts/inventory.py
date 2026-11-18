"""Inventory only public portfolio documents and their referenced public assets."""
from pathlib import Path
from urllib.parse import urljoin, urlsplit, unquote
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
import requests, json, hashlib

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://jowoohyung-portfolio.pages.dev/'
OUT = ROOT / 'research'
OUT.mkdir(exist_ok=True)
PAGES_ROOT = ROOT/'source' if (ROOT/'source/index.html').exists() else ROOT
pages = [PAGES_ROOT/'index.html', PAGES_ROOT/'work.html', PAGES_ROOT/'contents.html'] + sorted((PAGES_ROOT/'portfolio').glob('*.html'))
documents, media, links = [], {}, set()
for p in pages:
    rel = p.relative_to(PAGES_ROOT).as_posix()
    soup = BeautifulSoup(p.read_text(encoding='utf-8'), 'html.parser')
    documents.append({'path':rel,'public_url':BASE+rel,'title':soup.title.get_text(' ',strip=True),'headings':[h.get_text(' ',strip=True) for h in soup.select('h1,h2,h3,h4,h5')], 'text':soup.get_text(' ',strip=True)})
    for tag in soup.select('img[src],source[src],video[poster]'):
        key = 'poster' if tag.name=='video' else 'src'
        url = urljoin(BASE+rel,tag[key])
        entry = media.setdefault(url, {'url':url,'kind':'video' if tag.name=='source' else 'image','pages':[], 'description':tag.get('alt','')})
        if rel not in entry['pages']:entry['pages'].append(rel)
        parsed=urlsplit(url)
        if parsed.netloc==urlsplit(BASE).netloc:
            f=ROOT/unquote(parsed.path).lstrip('/')
            entry['local_file']=str(f.relative_to(ROOT))
            entry['available_in_checkout']=f.is_file()
            if f.is_file():entry['bytes']=f.stat().st_size;entry['sha256']=hashlib.sha256(f.read_bytes()).hexdigest()
        entry['usage']='concept art' if '/signal/' in url else 'existing public portfolio material'
    for a in soup.select('a[href]'):
        if a['href'].startswith('https://'):links.add(a['href'])

targets=[BASE+p.relative_to(PAGES_ROOT).as_posix() for p in pages]+list(media)+sorted(links)
def inspect(url):
    try:
        headers={'User-Agent':'Mozilla/5.0','Referer':BASE}
        response=requests.head(url,timeout=15,allow_redirects=True,headers=headers)
        if response.status_code in [403,405] and 'youtube' not in url and 'youtu.be' not in url:
            response=requests.get(url,timeout=15,stream=True,headers=headers)
        result={'url':url,'status':response.status_code,'content_type':response.headers.get('content-type'),'resolved_url':response.url}
        response.close()
        return result
    except Exception as e:return {'url':url,'error':type(e).__name__}
checks=list(ThreadPoolExecutor(8).map(inspect,dict.fromkeys(targets)))
data={'source':BASE,'documents':documents,'media':list(media.values()),'external_links':sorted(links),'checks':checks,'source_access':{'website_html':True,'public_media':True,'frontend_repository':'https://github.com/cho-woo/growthvillain','repository_checkout_available':True,'editable_design_and_campaign_export_originals':'not found in supplied website or repository; no Figma/PSD/AE/campaign-raw claim made'}}
(OUT/'content-inventory.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'documents':len(documents),'media':len(media),'external_links':len(links),'check_count':len(checks),'failed_checks':[c for c in checks if c.get('status',0)>=400 or c.get('error')]},ensure_ascii=False,indent=2))
