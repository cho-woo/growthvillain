from pathlib import Path
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from urllib.parse import urlsplit
import requests, hashlib, json, io

root=Path(__file__).resolve().parents[1]
originals=root.parent/'.workspace-local'/'portfolio-v2-originals'
originals.mkdir(parents=True,exist_ok=True)
public=root/'img'/'evidence'/'binusoap'
public.mkdir(parents=True,exist_ok=True)
soup=BeautifulSoup((root/'source/work.html').read_text(encoding='utf-8'),'html.parser')
urls=list(dict.fromkeys(im['src'] for im in soup.select('#case-binusoap img[src]')))
def fetch(url):
    uid=hashlib.sha256(url.encode()).hexdigest()[:16]
    ext=Path(urlsplit(url).path).suffix.lower()
    original=originals/(uid+ext)
    if not original.exists():
        res=requests.get(url,headers={'Referer':'https://jowoohyung-portfolio.pages.dev/','User-Agent':'Mozilla/5.0'},timeout=40)
        res.raise_for_status()
        original.write_bytes(res.content)
    im=Image.open(original)
    animated=getattr(im,'is_animated',False)
    if animated and original.stat().st_size<25*1024*1024:
        target=public/(uid+'.gif');target.write_bytes(original.read_bytes())
    else:
        target=public/(uid+'.webp');im=im.convert('RGB');im.thumbnail((1100,12000));im.save(target,'WEBP',quality=88,method=4)
    return {'source_url':url,'local_url':'/'+target.relative_to(root).as_posix(),'original_file':original.name,'original_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'bytes':target.stat().st_size,'width':im.width,'height':im.height,'animated':animated,'status':200,'reference_page':'https://jowoohyung-portfolio.pages.dev/work.html#case-binusoap'}
results=list(ThreadPoolExecutor(6).map(fetch,urls))
(root/'research'/'evidence-map.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
inventory=root/'research'/'content-inventory.json'
data=json.loads(inventory.read_text(encoding='utf-8'))
for check in data['checks']:
    if check['url'] in urls:check['status']=200;check['verification']='GET with public portfolio Referer; original downloaded and hashed';check.pop('error',None)
inventory.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Collected',len(results),'original comparison assets;',sum(x['bytes'] for x in results)//1024//1024,'MiB public media.')
