import {createDecisionField} from './decision-field.js';
import {createSound} from './sound.js';

const body = document.body;
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const sound = createSound();
const motionButton = document.querySelector('.motion-control');
const hero = document.querySelector('.opening');
const story = document.querySelector('.story');
const steps = [...document.querySelectorAll('.story-steps article')];
const chapters = [...document.querySelectorAll('.mast nav a, .case-index a')].map(link => ({
  link,
  target: document.getElementById(link.hash.slice(1)),
}));
let scene;
try {
  scene = createDecisionField(document.querySelector('#decision-field'), {reduced: reduced.matches});
} catch {
  // The static artwork is already in the document.
}
let paused = false;
let motion = false;
let frame = 0;
const clamp = value => Math.max(0, Math.min(1, value));

function updateScroll() {
  frame = 0;
  const y = window.scrollY;
  const full = document.documentElement.scrollHeight - innerHeight;
  body.style.setProperty('--read', full > 0 ? clamp(y / full) : 0);
  if (y < hero.offsetHeight + innerHeight) {
    const p = clamp(y / hero.offsetHeight);
    hero.style.setProperty('--hero', motion ? p : 0);
    if (motion) scene?.setProgress(p);
  }
  const readingLine = innerHeight * .53;
  const first = steps[0].getBoundingClientRect().top;
  const last = steps.at(-1).getBoundingClientRect().top;
  const progress = clamp((readingLine - first) / Math.max(1, last - first));
  story.style.setProperty('--plot', motion ? progress : 1);
  let current = steps[0];
  for (const step of steps) {
    if (step.getBoundingClientRect().top <= readingLine) current = step;
  }
  steps.forEach(step => step.classList.toggle('current', step === current));
  for (const {link, target} of chapters) {
    const rect = target.getBoundingClientRect();
    if (rect.top <= readingLine && rect.bottom >= readingLine) link.setAttribute('aria-current','location');
    else link.removeAttribute('aria-current');
  }
}
function scheduleScroll() {
  if (!frame) frame = requestAnimationFrame(updateScroll);
}
function syncMotion() {
  motion = !paused && !reduced.matches;
  body.classList.toggle('motion-on', motion);
  scene?.setMotion(motion);
  motionButton.disabled = reduced.matches;
  motionButton.setAttribute('aria-pressed',String(!motion));
  motionButton.textContent = motion ? '움직임 멈추기 Ⅱ' : reduced.matches ? '모션 감소 적용 중' : '움직임 켜기 ▷';
  scheduleScroll();
}
motionButton.addEventListener('click',() => { paused = !paused; syncMotion(); });
reduced.addEventListener('change',syncMotion);
document.querySelector('.sound-toggle').addEventListener('click',sound.toggle);
addEventListener('scroll',scheduleScroll,{passive:true});
addEventListener('resize',scheduleScroll,{passive:true});
document.addEventListener('toggle', event => {
  if (!(event.target instanceof HTMLDetailsElement)) return;
  if (!event.target.open) {
    event.target.querySelectorAll('video').forEach(video => video.pause());
  }
  scheduleScroll();
},true);
if ('ResizeObserver' in window) new ResizeObserver(scheduleScroll).observe(body);

const companies = [...document.querySelectorAll('.company')];
const search = document.querySelector('#company-search');
function filterCompanies() {
  const query = search.value.trim().normalize('NFC').toLocaleLowerCase();
  let matches = 0;
  for (const item of companies) {
    item.hidden = !item.dataset.search.toLocaleLowerCase().includes(query);
    if (!item.hidden) matches++;
  }
  document.querySelector('#company-count').textContent = matches + '개 기업';
  document.querySelector('#no-companies').hidden = matches > 0;
}
search.value = new URLSearchParams(location.search).get('q') || '';
search.addEventListener('input',filterCompanies);
filterCompanies();

// Bulk reading stays optional. A search limits the company group to its visible results.
for (const button of document.querySelectorAll('[data-expand]')) {
  const group = [...document.querySelectorAll(button.dataset.expand)];
  const label = button.textContent.replace(' 모두 펼치기','');
  function refreshGroup() {
    const visible = group.filter(item => !item.hidden);
    const open = visible.length > 0 && visible.every(item => item.open);
    button.disabled = visible.length === 0;
    button.setAttribute('aria-expanded', String(open));
    button.textContent = label + (open ? ' 모두 접기' : ' 모두 펼치기');
  }
  button.addEventListener('click', () => {
    const open = button.getAttribute('aria-expanded') !== 'true';
    group.filter(item => !item.hidden).forEach(item => { item.open = open; });
    refreshGroup();
  });
  group.forEach(item => item.addEventListener('toggle', refreshGroup));
  search.addEventListener('input', refreshGroup);
  refreshGroup();
}

const aliases = {ai:'automation', career:'about', 'case-desillab':'desillab', 'case-binusoap':'binusoap', 'case-mogrami':'mogrami', 'career-ad-operations':'operations', 'optimust-title':'optimust'};
function revealTarget(hash) {
  let id;
  try { id = decodeURIComponent(hash.slice(1)); } catch { return null; }
  const target = document.getElementById(aliases[id] || id);
  if (!target) return null;
  const company = target.closest('.company');
  if (company?.hidden) {search.value = '';filterCompanies();}
  for (let parent = target; parent; parent = parent.parentElement) {
    if (parent instanceof HTMLDetailsElement) parent.open = true;
  }
  if (target.matches('.case-sheet')) target.querySelector('.case-more').open = true;
  return target;
}
document.addEventListener('click',event => {
  const link = event.target.closest('a[href^="#"]');
  if (link && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) {
    revealTarget(link.hash);
  }
});
function followFragment() {
  const target = revealTarget(location.hash);
  if (target) requestAnimationFrame(() => target.scrollIntoView({block:'start',behavior:'instant'}));
}
addEventListener('hashchange',followFragment);
if (location.hash) followFragment();

const dialog = document.querySelector('.image-dialog');
const large = dialog.querySelector('img');
let opener;
document.addEventListener('click',event => {
  const link = event.target.closest('a.enlarge');
  if (!link || !dialog.showModal || event.ctrlKey || event.metaKey || event.shiftKey) return;
  event.preventDefault();
  opener = link;
  const source = link.querySelector('img');
  large.src = link.href;
  large.alt = source.alt;
  dialog.querySelector('.dialog-caption p').textContent = source.alt;
  dialog.querySelector('.dialog-caption a').href = link.href;
  dialog.showModal();
  dialog.querySelector('.dialog-scroll').scrollTop = 0;
});
dialog.querySelector('.dialog-close').addEventListener('click',() => dialog.close());
dialog.addEventListener('click',event => { if (event.target === dialog) dialog.close(); });
dialog.addEventListener('close',() => opener?.focus({preventScroll:true}));

const comparison = document.querySelector('.comparison');
const compareButtons = [...document.querySelectorAll('[data-compare]')];
compareButtons.forEach(button => button.addEventListener('click',() => {
  comparison.dataset.mode = button.dataset.compare;
  compareButtons.forEach(other => other.setAttribute('aria-pressed',String(other === button)));
}));
const panels = [...comparison.querySelectorAll('.compare-viewport')];
const sync = document.querySelector('.compare-sync');
panels.forEach((panel, index) => panel.addEventListener('scroll',() => {
  if (!sync.checked || comparison.dataset.mode !== 'both') return;
  const other = panels[1-index];
  const fraction = panel.scrollTop / Math.max(1,panel.scrollHeight-panel.clientHeight);
  const dest = fraction * (other.scrollHeight-other.clientHeight);
  if (Math.abs(other.scrollTop-dest) > 1) other.scrollTop = dest;
},{passive:true}));

document.querySelector('.copy-email').addEventListener('click',async () => {
  const status = document.querySelector('.copy-announcement');
  try {await navigator.clipboard.writeText('hello@valuewander.com'); status.textContent='이메일 주소를 복사했습니다.';}
  catch { status.textContent='이메일 주소는 hello@valuewander.com입니다.'; }
});
if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        entry.target.classList.add('arrived');
        observer.unobserve(entry.target);
      }
    }
  },{threshold:.08});
  document.querySelectorAll('.case-face,.chapter-heading,.flagship,.history>div').forEach(el => observer.observe(el));
}
body.classList.add('js-ready');
sound.refresh();
syncMotion();
