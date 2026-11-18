import {createDecisionField} from './decision-field.js';
import {createSound} from './sound.js';

const root=document.documentElement;
root.classList.add('js');
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
const sound=createSound();
let scene=null,reveals=null,sectionObserver=null,motion=true,scrollFrame=0,lastFocus=null,activeTransition=null;
const header=document.querySelector('.site-header'),menu=document.querySelector('.menu-button'),nav=document.querySelector('.site-nav');
const dialog=document.querySelector('.image-dialog');
const cache=new Map(),scrollPositions=new Map();
let currentKey=history.state?.v2key||crypto.randomUUID(),currentRoute=location.pathname+location.search,routeSequence=0;
const initialScrollY=history.state?.scrollY||0;
history.replaceState({...history.state,v2key:currentKey},'');
if('scrollRestoration' in history)history.scrollRestoration='manual';

function closeMenu(){menu.setAttribute('aria-expanded','false');nav.classList.remove('open');}
function refreshMotion(){const enabled=motion&&!reduced.matches;root.classList.toggle('motion-off',!enabled);scene?.setMotion(enabled);document.querySelectorAll('.motion-toggle').forEach(b=>{b.setAttribute('aria-pressed',String(!enabled));b.setAttribute('aria-label',enabled?'모션 일시 정지':'모션 재생');b.textContent=enabled?'MOTION ON Ⅱ':'MOTION OFF ▷';});}
function scrollUI(){scrollFrame=0;const max=root.scrollHeight-innerHeight,y=scrollY;header.classList.toggle('scrolled',y>25);header.querySelector('.read-progress span').style.transform=`scaleX(${max>0?Math.min(1,y/max):0})`;const hero=document.querySelector('.hero-track');if(hero){const range=hero.offsetHeight-innerHeight,p=range>0?Math.max(0,Math.min(1,(y-hero.offsetTop)/range)):0;hero.style.setProperty('--scene-progress',p);scene?.setProgress(p);const label=hero.querySelector('.scene-state');if(label)label.textContent=p<.33?'01 — CLOSE VIEW':p<.7?'02 — A WIDER CONTEXT':'03 — INTO THE WORK';}scrollPositions.set(currentKey,y);}
window.addEventListener('scroll',()=>{if(!scrollFrame)scrollFrame=requestAnimationFrame(scrollUI);},{passive:true});
window.addEventListener('resize',()=>{if(innerWidth>600)closeMenu();if(!scrollFrame)scrollFrame=requestAnimationFrame(scrollUI);},{passive:true});
reduced.addEventListener('change',refreshMotion);

function setupArchive(){
  const input=document.getElementById('project-search');if(!input)return;
  const buttons=[...document.querySelectorAll('[data-filter]')],rows=[...document.querySelectorAll('.archive-row')],url=new URL(location.href);
  let filter=['marketing','data','automation'].includes(url.searchParams.get('category'))?url.searchParams.get('category'):'all';
  input.value=url.searchParams.get('q')||'';
  function apply(updateURL=true){const q=input.value.trim().toLocaleLowerCase();let count=0;rows.forEach(row=>{const show=(filter==='all'||row.dataset.category===filter)&&row.dataset.search.toLocaleLowerCase().includes(q);row.hidden=!show;if(show)count++;});buttons.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.filter===filter)));document.getElementById('archive-count').textContent=`${count}개의 작업`;document.querySelector('.no-results').hidden=count!==0;if(updateURL){const u=new URL(location.href);filter==='all'?u.searchParams.delete('category'):u.searchParams.set('category',filter);q?u.searchParams.set('q',input.value.trim()):u.searchParams.delete('q');history.replaceState({...history.state},'',u);currentRoute=u.pathname+u.search;}}
  buttons.forEach(b=>b.addEventListener('click',()=>{filter=b.dataset.filter;apply();sound.effect();}));input.addEventListener('input',()=>apply());apply(false);
}
function setupComparison(){
  const comparison=document.querySelector('.comparison');if(!comparison)return;
  document.querySelectorAll('[data-compare]').forEach(button=>button.addEventListener('click',()=>{comparison.dataset.mode=button.dataset.compare;document.querySelectorAll('[data-compare]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));sound.effect();}));
  const viewports=[...comparison.querySelectorAll('.compare-viewport')],sync=document.querySelector('.compare-sync');let locking=false;
  viewports.forEach((viewport,index)=>viewport.addEventListener('scroll',()=>{if(locking||!sync.checked)return;const max=viewport.scrollHeight-viewport.clientHeight,other=viewports[1-index];if(max<=0)return;locking=true;other.scrollTop=(viewport.scrollTop/max)*(other.scrollHeight-other.clientHeight);setTimeout(()=>locking=false,75);},{passive:true}));
}
function failedImage(image){if(!image.isConnected)return;const box=document.createElement('p');box.className='media-error';box.append(document.createTextNode('이 작업 이미지를 불러오지 못했습니다. '));const a=document.createElement('a');a.href=image.dataset.original||image.currentSrc||image.src;a.target='_blank';a.rel='noopener';a.textContent='원본 주소에서 확인 ↗';box.append(a);(image.closest('.zoom-image')||image).replaceWith(box);}
function setupEvidence(){
  document.querySelectorAll('.evidence img').forEach(image=>{
    if(!image.closest('a,button')){const button=document.createElement('button');button.type='button';button.className='zoom-image';button.setAttribute('aria-label',`${image.alt||'작업 자료'} 확대 보기`);image.before(button);button.append(image);}
    image.addEventListener('error',()=>failedImage(image),{once:true});if(image.complete&&!image.naturalWidth)failedImage(image);
  });
  document.querySelectorAll('video').forEach(v=>v.addEventListener('error',()=>{if(v.nextElementSibling?.classList.contains('media-error'))return;const p=document.createElement('p');p.className='media-error';p.textContent='영상을 불러오지 못했습니다. 아래 원본 영상 파일을 확인해 주세요. ';const a=document.createElement('a');a.href=v.querySelector('source')?.src||v.currentSrc;a.textContent='영상 파일 열기 ↗';a.target='_blank';a.rel='noopener';p.append(a);v.after(p);},{once:true}));
}
function openImage(button){const image=button.querySelector('img');if(!image)return;lastFocus=button;const large=dialog.querySelector('img');large.src=image.currentSrc||image.src;large.alt=image.alt||'작업 자료';dialog.querySelector('.dialog-caption p').textContent=large.alt;const original=dialog.querySelector('.dialog-caption a');original.href=image.currentSrc||image.src;original.textContent='원본 크기 파일 열기 ↗';dialog.showModal();dialog.querySelector('.dialog-scroll').scrollTop=0;sound.effect();}
dialog.querySelector('.dialog-close').addEventListener('click',()=>dialog.close());
dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close();});
dialog.addEventListener('close',()=>{if(lastFocus?.isConnected)lastFocus.focus({preventScroll:true});});

function setupReveals(){
  reveals?.disconnect();sectionObserver?.disconnect();
  if(!('IntersectionObserver' in window))return;
  root.classList.add('reveals-ready');
  reveals=new IntersectionObserver(entries=>entries.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in-view');reveals.unobserve(e.target);} }),{threshold:.06,rootMargin:'0px 0px -18px 0px'});
  document.querySelectorAll('.reveal').forEach(el=>reveals.observe(el));
  sectionObserver=new IntersectionObserver(entries=>entries.forEach(e=>{if(e.isIntersecting)nav.querySelectorAll('a').forEach(a=>{if(a.hash===`#${e.target.id}`)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');});}),{rootMargin:'-20% 0px -55% 0px'});
  document.querySelectorAll('section[id],footer[id]').forEach(el=>sectionObserver.observe(el));
}
function initPage(){
  try{scene=createDecisionField(document.getElementById('decision-field'),{reduced:reduced.matches});}catch{scene=null;}
  setupReveals();setupEvidence();setupArchive();setupComparison();sound.refresh();refreshMotion();scrollUI();
  if(document.body.dataset.page==='archive')nav.querySelector('a[href="/archive.html"]')?.setAttribute('aria-current','page');
}
function savePosition(){scrollPositions.set(currentKey,scrollY);history.replaceState({...history.state,v2key:currentKey,scrollY},'');}
window.addEventListener('pagehide',savePosition);
function goHash(hash,instant=false){const id=decodeURIComponent(hash.slice(1));const el=id?document.getElementById(id):null;if(el)el.scrollIntoView({behavior:instant||reduced.matches?'instant':'smooth',block:'start'});else window.scrollTo({top:0,behavior:'instant'});}
async function navigate(url,{pop=false,state=null}={}){
  const sequence=++routeSequence;
  if(!pop)savePosition();else scrollPositions.set(currentKey,scrollY);
  const restoreY=pop?(scrollPositions.get(state?.v2key)??state?.scrollY??0):0;
  closeMenu();document.querySelector('.cursor-note')?.classList.remove('active');if(dialog.open)dialog.close();sound.effect('route');root.classList.add('navigating');document.getElementById('main').setAttribute('aria-busy','true');
  try{
    const path=url.pathname+url.search;let html=cache.get(path);
    if(!html){const response=await fetch(url.href,{headers:{'X-Portfolio-Navigation':'1'}});if(!response.ok)throw Error('navigation');html=await response.text();cache.set(path,html);}
    if(sequence!==routeSequence)return;
    const next=new DOMParser().parseFromString(html,'text/html'),main=next.querySelector('#main');if(!main)throw Error('document');
    const update=()=>{
      if(sequence!==routeSequence)return;
      document.querySelectorAll('video').forEach(v=>v.pause());scene?.dispose();scene=null;reveals?.disconnect();sectionObserver?.disconnect();
      document.getElementById('main').replaceWith(document.importNode(main,true));document.title=next.title;document.body.dataset.page=next.body.dataset.page;
      if(!pop){currentKey=crypto.randomUUID();history.pushState({v2key:currentKey,scrollY:0},'',url);}else currentKey=state?.v2key||crypto.randomUUID();
      currentRoute=url.pathname+url.search;initPage();root.classList.remove('navigating');
      if(pop){window.scrollTo({top:restoreY,behavior:'instant'});}else if(url.hash)goHash(url.hash,true);else window.scrollTo({top:0,behavior:'instant'});
      scrollUI();
      document.getElementById('main').focus({preventScroll:true});
    };
    if(document.startViewTransition&&!reduced.matches){
      activeTransition?.skipTransition();
      const transition=document.startViewTransition(update);activeTransition=transition;
      transition.ready.catch(()=>{});
      await transition.updateCallbackDone;
      await transition.finished.catch(()=>{});
      if(activeTransition===transition)activeTransition=null;
    }else update();
  }catch{if(sequence===routeSequence)location.assign(url.href);}finally{if(sequence===routeSequence){root.classList.remove('navigating');document.getElementById('main')?.removeAttribute('aria-busy');}}
}
document.addEventListener('click',async e=>{
  const button=e.target.closest('button');
  if(button){
    if(button===menu){const open=menu.getAttribute('aria-expanded')!=='true';menu.setAttribute('aria-expanded',String(open));nav.classList.toggle('open',open);return;}
    if(button.matches('.sound-toggle')){sound.toggle();return;}
    if(button.matches('[data-sound-start]')){sound.enable();return;}
    if(button.matches('[data-sound-dismiss]')){sound.disable();return;}
    if(button.matches('.motion-toggle')){motion=!motion;refreshMotion();return;}
    if(button.matches('.zoom-image')){openImage(button);return;}
    if(button.matches('.email-copy')){try{await navigator.clipboard.writeText('hello@valuewander.com');button.textContent='복사했습니다 ✓';document.querySelector('.copy-announcement').textContent='이메일 주소가 복사되었습니다.';sound.effect();setTimeout(()=>{if(button.isConnected)button.innerHTML='이메일 복사 <span aria-hidden="true">⧉</span>';},2500);}catch{button.textContent='hello@valuewander.com';document.querySelector('.copy-announcement').textContent='이메일 주소는 hello@valuewander.com입니다.';}return;}
  }
  const link=e.target.closest('a[href]');if(!link||e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey||link.target==='_blank'||link.hasAttribute('download'))return;
  const url=new URL(link.href,location.href);if(url.origin!==location.origin||!['http:','https:'].includes(url.protocol))return;
  if(!url.pathname.endsWith('/')&&!url.pathname.endsWith('.html'))return;
  e.preventDefault();
  if(url.pathname+url.search===currentRoute&&url.hash){savePosition();currentKey=crypto.randomUUID();history.pushState({v2key:currentKey,scrollY:0},'',url);goHash(url.hash);closeMenu();return;}
  navigate(url);
});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&menu.getAttribute('aria-expanded')==='true'){closeMenu();menu.focus();}});
window.addEventListener('popstate',e=>{const url=new URL(location.href);if(url.pathname+url.search===currentRoute){scrollPositions.set(currentKey,scrollY);currentKey=e.state?.v2key||crypto.randomUUID();if(scrollPositions.has(currentKey))window.scrollTo({top:scrollPositions.get(currentKey),behavior:'instant'});else goHash(url.hash,true);}else navigate(url,{pop:true,state:e.state});});

const cursor=document.querySelector('.cursor-note');
if(matchMedia('(hover:hover) and (pointer:fine)').matches){document.addEventListener('pointermove',e=>{cursor.style.left=`${e.clientX+35}px`;cursor.style.top=`${e.clientY+35}px`;cursor.classList.toggle('active',Boolean(e.target.closest('.work-row'))&&!reduced.matches);},{passive:true});document.addEventListener('pointerleave',()=>cursor.classList.remove('active'));}
function clock(){const element=document.getElementById('seoul-clock');if(element)element.textContent=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date());}
setInterval(()=>{if(!document.hidden)clock();},30000);clock();
initPage();
if(initialScrollY>0&&performance.getEntriesByType('navigation')[0]?.type!=='navigate')requestAnimationFrame(()=>window.scrollTo({top:initialScrollY,behavior:'instant'}));
else if(location.hash&&document.getElementById(decodeURIComponent(location.hash.slice(1))))requestAnimationFrame(()=>goHash(location.hash,true));
const legacy={ai:'/projects/automation/',planning:'/#work',career:'/#about',petbox:'/projects/petbox/','case-desillab':'/projects/desillab/','case-binusoap':'/projects/binusoap/','case-mogrami':'/projects/mogrami/','career-ad-operations':'/projects/operations/','optimust-title':'/projects/optimust/'};
if(location.hash&&!document.getElementById(location.hash.slice(1))&&legacy[location.hash.slice(1)])navigate(new URL(legacy[location.hash.slice(1)],location.origin));
