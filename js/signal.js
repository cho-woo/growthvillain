/* Native scrolling and progressive enhancement; all content works without JS. */
(() => {
  'use strict';
  const root = document.documentElement;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const header = document.querySelector('.site-header');
  const progress = document.querySelector('.reading-progress span');
  const menu = document.querySelector('.menu-toggle');
  const nav = document.querySelector('.main-nav');
  const closeMenu = () => { nav?.classList.remove('open'); menu?.setAttribute('aria-expanded', 'false'); };
  menu?.addEventListener('click', () => { const open = menu.getAttribute('aria-expanded') !== 'true'; menu.setAttribute('aria-expanded', String(open)); nav.classList.toggle('open', open); });
  nav?.querySelectorAll('a').forEach(a => a.addEventListener('click', closeMenu));
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && menu?.getAttribute('aria-expanded') === 'true') { closeMenu(); menu.focus(); } });
  window.addEventListener('resize', () => { if (innerWidth > 700) closeMenu(); }, { passive: true });
  let scrollScheduled = false;
  const renderScroll = () => { const max = root.scrollHeight - innerHeight; const y = scrollY; header?.classList.toggle('scrolled', y > 35); if (progress) progress.style.transform = `scaleX(${max > 0 ? Math.min(1, y / max) : 0})`; scrollScheduled = false; };
  window.addEventListener('scroll', () => { if (!scrollScheduled) { requestAnimationFrame(renderScroll); scrollScheduled = true; } }, { passive: true }); renderScroll();
  if ('IntersectionObserver' in window) {
    root.classList.add('js-reveal');
    const observer = new IntersectionObserver(entries => entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in-view'); observer.unobserve(e.target); } }), { threshold: .07, rootMargin: '0px 0px -20px 0px' });
    document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
    const navObserver = new IntersectionObserver(entries => entries.forEach(entry => { if (entry.isIntersecting) { nav?.querySelectorAll('a').forEach(a => a.classList.toggle('is-active', a.hash === `#${entry.target.id}`)); } }), { rootMargin: '-20% 0px -55% 0px' });
    document.querySelectorAll('section[id], footer[id]').forEach(el => navObserver.observe(el));
  }
  const clock = document.getElementById('seoul-time');
  if (clock) { const updateClock = () => { clock.textContent = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date()); }; updateClock(); setInterval(() => { if (!document.hidden) updateClock(); }, 1000); }
  const projects = [...document.querySelectorAll('.project')];
  document.querySelectorAll('.filter').forEach(button => button.addEventListener('click', () => { const category = button.dataset.filter; document.querySelectorAll('.filter').forEach(b => { b.classList.toggle('active', b === button); b.setAttribute('aria-pressed', String(b === button)); }); let count = 0; projects.forEach(project => { const show = category === 'all' || project.dataset.category === category; project.hidden = !show; if (show) { count++; project.classList.add('in-view'); } }); const status = document.getElementById('filter-status'); if (status) status.textContent = `${button.textContent.trim()} 프로젝트 ${count}개`; renderScroll(); }));
  const copyButton = document.querySelector('.copy-email');
  copyButton?.addEventListener('click', async () => { try { await navigator.clipboard.writeText('hello@valuewander.com'); copyButton.textContent = 'COPIED ✓'; document.querySelector('.copy-status').textContent = '이메일 주소가 복사되었습니다.'; setTimeout(() => { copyButton.innerHTML = 'COPY EMAIL <span aria-hidden="true">⧉</span>'; }, 2500); } catch { document.querySelector('.copy-status').textContent = '이메일 주소는 hello@valuewander.com입니다. 이메일 링크를 이용해 주세요.'; copyButton.textContent = 'hello@valuewander.com'; } });
  const cursor = document.querySelector('.cursor-label');
  if (cursor && matchMedia('(hover: hover) and (pointer: fine)').matches && !reduced.matches) { document.addEventListener('pointermove', e => { cursor.style.left = `${e.clientX}px`; cursor.style.top = `${e.clientY}px`; }, { passive: true }); projects.forEach(p => { p.addEventListener('pointerenter', () => cursor.classList.add('visible')); p.addEventListener('pointerleave', () => cursor.classList.remove('visible')); }); }
  const canvas = document.getElementById('signal-dust');
  const motionButton = document.querySelector('.motion-control');
  const ctx = canvas?.getContext('2d');
  let paused = reduced.matches, heroVisible = true, frame = 0, last = 0, width = 0, height = 0, dust = [];
  const updateMotionLabel = () => { root.classList.toggle('motion-paused', paused); if (motionButton) { motionButton.setAttribute('aria-pressed', String(paused)); motionButton.setAttribute('aria-label', paused ? '배경 움직임 재생' : '배경 움직임 일시 정지'); motionButton.innerHTML = `<span class="motion-icon" aria-hidden="true">${paused ? '▷' : 'Ⅱ'}</span> MOTION ${paused ? 'OFF' : 'ON'}`; } };
  const resizeDust = () => { if (!canvas || !ctx) return; const box = canvas.getBoundingClientRect(); width = box.width; height = box.height; const ratio = Math.min(devicePixelRatio || 1, 1.5); canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); dust = Array.from({ length: innerWidth < 700 ? 20 : 42 }, () => ({ x: Math.random() * width, y: Math.random() * height, r: .3 + Math.random() * 1.15, v: .04 + Math.random() * .11, a: .1 + Math.random() * .35 })); };
  const draw = time => { frame = 0; if (!ctx || paused || !heroVisible || document.hidden) return; const delta = Math.min(60, time - (last || time)); last = time; ctx.clearRect(0, 0, width, height); dust.forEach(p => { p.y -= p.v * delta / 16.67; p.x += .015 * delta / 16.67; if (p.y < -2) p.y = height + 2; ctx.beginPath(); ctx.fillStyle = `rgba(255,178,105,${p.a})`; ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill(); }); frame = requestAnimationFrame(draw); };
  const startDust = () => { if (!frame && !paused && heroVisible && !document.hidden) { last = 0; frame = requestAnimationFrame(draw); } };
  if (ctx) { resizeDust(); startDust(); window.addEventListener('resize', resizeDust, { passive: true }); if ('IntersectionObserver' in window) new IntersectionObserver(entries => { heroVisible = entries[0].isIntersecting; if (heroVisible) startDust(); }).observe(canvas); }
  motionButton?.addEventListener('click', () => { paused = !paused; updateMotionLabel(); if (paused) { cancelAnimationFrame(frame); frame = 0; } else startDust(); });
  reduced.addEventListener('change', e => { paused = e.matches; updateMotionLabel(); if (paused) { cancelAnimationFrame(frame); frame = 0; } else startDust(); });
  document.addEventListener('visibilitychange', () => { if (document.hidden) { cancelAnimationFrame(frame); frame = 0; } else startDust(); }); updateMotionLabel();
  // Keep previously shared deep links useful after the homepage redesign.
  const legacy = new Set(["portfolio-navigation", "portfolio-content", "ai", "planning", "performance", "commerce", "case-mogrami", "viral", "case-binusoap", "jeongango-before-title", "jeongango-after-title", "binusoap-sales-title", "binusoap-sales-desc", "case-desillab", "data", "client-data-title", "petbox", "petbox-title", "career", "leadership", "career-ad-operations", "career-operations-title", "career-profit", "career-profit-title", "career-scaling", "career-scaling-title", "career-media", "career-media-title", "career-launch", "career-launch-title", "career-analysis", "career-analysis-title", "career-review", "career-review-title", "optimust-title", "contact", "lightbox", "lightbox-img"]);
  if (legacy.has(location.hash.slice(1)) && !document.getElementById(location.hash.slice(1))) location.replace(`/work.html${location.hash}`);
})();
