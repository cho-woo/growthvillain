/* Progressive enhancements: the entire portfolio remains readable without JavaScript. */
(() => {
  'use strict';
  const nav = document.querySelector('.dnav');
  const links = [...nav.querySelectorAll('a[data-sec]')];
  const sections = links.map(link => document.getElementById(link.dataset.sec)).filter(Boolean);
  const toggle = nav.querySelector('.nav-toggle');
  const currentLabel = nav.querySelector('[data-current-section]');
  const progress = nav.querySelector('.reading-progress span');
  const mobile = window.matchMedia('(max-width: 780px)');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let activeSection = '';
  let scheduled = false;

  nav.classList.add('enhanced');
  toggle.hidden = false;
  const closeMenu = () => {
    nav.classList.remove('menu-open');
    toggle.setAttribute('aria-expanded', 'false');
  };
  toggle.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') !== 'true';
    nav.classList.toggle('menu-open', open);
    toggle.setAttribute('aria-expanded', String(open));
  });
  nav.addEventListener('keydown', event => {
    if (event.key === 'Escape' && nav.classList.contains('menu-open')) {
      closeMenu();
      toggle.focus();
    }
  });
  document.addEventListener('click', event => {
    if (!nav.contains(event.target)) closeMenu();
  });
  nav.addEventListener('focusout', () => {
    requestAnimationFrame(() => {
      if (!nav.contains(document.activeElement)) closeMenu();
    });
  });
  mobile.addEventListener('change', closeMenu);
  links.forEach(link => link.addEventListener('click', () => {
    closeMenu();
    if (mobile.matches) {
      const destination = document.getElementById(link.dataset.sec);
      destination.setAttribute('tabindex', '-1');
      destination.focus({ preventScroll: true });
    }
  }));
  const updatePosition = () => {
    scheduled = false;
    const marker = nav.getBoundingClientRect().height + Math.min(window.innerHeight * .24, 180);
    let current = sections[0];
    sections.forEach(section => { if (section.getBoundingClientRect().top <= marker) current = section; });
    if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 8) current = sections[sections.length - 1];
    if (current && current.id !== activeSection) {
      activeSection = current.id;
      links.forEach(link => {
        const active = link.dataset.sec === activeSection;
        link.classList.toggle('active', active);
        if (active) {
          link.setAttribute('aria-current', 'location');
          currentLabel.textContent = link.textContent;
        } else link.removeAttribute('aria-current');
      });
    }
    const range = document.documentElement.scrollHeight - window.innerHeight;
    progress.style.transform = `scaleX(${range > 0 ? Math.min(1, Math.max(0, window.scrollY / range)) : 1})`;
  };
  const schedulePosition = () => {
    if (!scheduled) { scheduled = true; requestAnimationFrame(updatePosition); }
  };
  window.addEventListener('scroll', schedulePosition, { passive: true });
  window.addEventListener('resize', schedulePosition, { passive: true });
  window.addEventListener('load', schedulePosition);
  updatePosition();

  const backgroundVideo = document.querySelector('.dbg-video');
  const updateBackgroundMotion = () => {
    if (!backgroundVideo) return;
    if (reducedMotion.matches || document.hidden) backgroundVideo.pause();
    else backgroundVideo.play().catch(() => {});
  };
  reducedMotion.addEventListener('change', updateBackgroundMotion);
  document.addEventListener('visibilitychange', updateBackgroundMotion);
  updateBackgroundMotion();

  const chart = document.querySelector('.brand-sales-chart');
  if (chart) {
    const amounts = { 5: 22, 6: 23, 7: 37, 8: 43 };
    const buttons = [...chart.querySelectorAll('[data-sales-select]')];
    const label = chart.querySelector('[data-sales-label]');
    const value = chart.querySelector('[data-sales-value]');
    const selectMonth = month => {
      buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.salesSelect === month)));
      chart.querySelectorAll('[data-sales-month]').forEach(bar => bar.classList.toggle('is-selected', bar.dataset.salesMonth === month));
      label.textContent = month === '7' ? '7월 매출 · 개선' : `${month}월 매출`;
      value.textContent = `${amounts[month]}억 원`;
    };
    chart.querySelector('.sales-controls').hidden = false;
    buttons.forEach((button, index) => {
      button.addEventListener('click', () => selectMonth(button.dataset.salesSelect));
      button.addEventListener('keydown', event => {
        let next;
        if (event.key === 'ArrowRight') next = (index + 1) % buttons.length;
        if (event.key === 'ArrowLeft') next = (index + buttons.length - 1) % buttons.length;
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = buttons.length - 1;
        if (next === undefined) return;
        event.preventDefault();
        buttons[next].focus();
        selectMonth(buttons[next].dataset.salesSelect);
      });
    });
    selectMonth('8');
  }

  const comparison = document.querySelector('.detail-comparison');
  if (comparison) {
    const panels = [...comparison.querySelectorAll('.comparison-preview')];
    const tools = document.querySelector('.comparison-tools');
    const sync = tools.querySelector('[data-comparison-sync]');
    let syncing = false;
    let expanded = null;
    let lastSource = panels[0];
    const fraction = panel => panel.scrollTop / Math.max(1, panel.scrollHeight - panel.clientHeight);
    const applyFraction = (panel, ratio) => { panel.scrollTop = Math.max(0, panel.scrollHeight - panel.clientHeight) * ratio; };
    const syncFrom = source => {
      if (!sync.checked || syncing || expanded) return;
      syncing = true;
      const ratio = fraction(source);
      panels.forEach(panel => { if (panel !== source) applyFraction(panel, ratio); });
      requestAnimationFrame(() => { syncing = false; });
    };
    tools.hidden = false;
    panels.forEach(panel => panel.addEventListener('scroll', () => {
      if (syncing) return;
      lastSource = panel;
      syncFrom(panel);
    }, { passive: true }));
    sync.addEventListener('change', () => syncFrom(lastSource));
    tools.querySelector('[data-comparison-reset]').addEventListener('click', () => {
      syncing = true;
      panels.forEach(panel => { panel.scrollTop = 0; });
      requestAnimationFrame(() => { syncing = false; });
    });

    if (typeof HTMLDialogElement !== 'undefined') {
      const dialog = document.createElement('dialog');
      dialog.className = 'preview-dialog';
      dialog.setAttribute('aria-labelledby', 'preview-dialog-title');
      dialog.innerHTML = '<div class="preview-dialog-head"><h2 id="preview-dialog-title"></h2><button class="quiet-button" type="button" data-preview-close>닫기 <span aria-hidden="true">×</span></button></div><div class="preview-dialog-content"></div>';
      document.body.appendChild(dialog);
      const content = dialog.querySelector('.preview-dialog-content');
      let placeholder;
      let opener;
      comparison.querySelectorAll('[data-preview-open]').forEach(button => {
        button.hidden = false;
        button.addEventListener('click', () => {
          opener = button;
          expanded = comparison.querySelector(`.comparison-${button.dataset.previewOpen} .comparison-preview`);
          const position = fraction(expanded);
          placeholder = document.createComment('detail preview position');
          expanded.before(placeholder);
          content.appendChild(expanded);
          dialog.querySelector('h2').textContent = `정안고 · ${button.dataset.previewOpen === 'before' ? '개선 전' : '개선 후'}`;
          document.body.classList.add('preview-open');
          dialog.showModal();
          applyFraction(expanded, position);
          dialog.querySelector('[data-preview-close]').focus();
        });
      });
      dialog.querySelector('[data-preview-close]').addEventListener('click', () => dialog.close());
      dialog.addEventListener('click', event => {
        if (event.target !== dialog) return;
        const bounds = dialog.getBoundingClientRect();
        if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
      });
      dialog.addEventListener('close', () => {
        if (!expanded) return;
        const position = fraction(expanded);
        placeholder.replaceWith(expanded);
        applyFraction(expanded, position);
        expanded = null;
        document.body.classList.remove('preview-open');
        opener.focus({ preventScroll: true });
        schedulePosition();
      });
    }
  }

  // Preserve the legacy image viewer while making it operable from a keyboard.
  const lightbox = document.getElementById('lightbox');
  if (lightbox) {
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'quiet-button lightbox-close';
    close.textContent = '닫기 ×';
    lightbox.prepend(close);
    lightbox.setAttribute('role', 'dialog');
    lightbox.setAttribute('aria-label', '이미지 크게 보기');
    lightbox.setAttribute('aria-modal', 'true');
    let previousFocus;
    const closeBox = () => lightbox.classList.remove('open');
    close.addEventListener('click', closeBox);
    const lightboxImage = document.getElementById('lightbox-img');
    lightboxImage.tabIndex = 0;
    lightboxImage.setAttribute('role', 'button');
    lightboxImage.setAttribute('aria-label', '이미지 확대 또는 축소');
    lightboxImage.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); lightboxImage.click(); }
    });
    lightbox.addEventListener('keydown', event => {
      if (event.key !== 'Tab') return;
      event.preventDefault();
      (document.activeElement === close ? lightboxImage : close).focus();
    });
    new MutationObserver(() => {
      if (lightbox.classList.contains('open')) {
        previousFocus = document.activeElement;
        close.focus();
      } else if (previousFocus && previousFocus.isConnected) previousFocus.focus({ preventScroll: true });
    }).observe(lightbox, { attributes: true, attributeFilter: ['class'] });
    document.querySelectorAll('.eshot img').forEach(image => {
      image.tabIndex = 0;
      image.setAttribute('role', 'button');
      image.setAttribute('aria-label', `${image.alt || '이미지'} 크게 보기`);
      image.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); image.click(); }
      });
    });
  }
})();
