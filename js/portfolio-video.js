(() => {
  'use strict';
  const video = document.getElementById('portfolio-intro-video');
  if (!video) return;
  const sound = document.querySelector('[data-intro-sound]');
  const soundLabel = sound.querySelector('span');
  const play = document.querySelector('[data-intro-play]');
  const status = document.querySelector('[data-intro-status]');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let automaticPause = false;
  let resumeAfterVisibility = false;
  const updateSound = () => {
    const audible = !video.muted && video.volume > 0;
    soundLabel.textContent = audible ? '소리 끄기' : '소리 켜기';
    sound.setAttribute('aria-pressed', String(audible));
  };
  const tryPlay = () => {
    const attempt = video.play();
    if (attempt) attempt.catch(() => { play.hidden = false; });
  };
  sound.addEventListener('click', () => {
    video.muted = !(video.muted || video.volume === 0);
    if (!video.muted && video.volume === 0) video.volume = 1;
    updateSound();
    // Playback with sound begins only in response to this visitor gesture.
    if (video.paused) tryPlay();
  });
  play.addEventListener('click', tryPlay);
  video.addEventListener('volumechange', updateSound);
  video.addEventListener('playing', () => { play.hidden = true; status.hidden = true; });
  video.addEventListener('error', () => {
    status.textContent = '영상을 불러오지 못했습니다. 아래 포트폴리오를 먼저 살펴보세요.';
    status.hidden = false;
    sound.disabled = true;
  });
  const applyMotionPreference = () => {
    if (reducedMotion.matches) { video.autoplay = false; video.pause(); play.hidden = false; }
    else { video.autoplay = true; tryPlay(); }
  };
  reducedMotion.addEventListener('change', applyMotionPreference);
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(entries => {
      const visible = entries[0].isIntersecting;
      if (!visible && !video.paused) { automaticPause = true; video.pause(); }
      else if (visible && automaticPause && !document.hidden && !reducedMotion.matches) {
        automaticPause = false; tryPlay();
      }
    }, { threshold: 0.1 }).observe(video);
  }
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { resumeAfterVisibility = !video.paused; video.pause(); }
    else if (resumeAfterVisibility && !automaticPause && !reducedMotion.matches) { resumeAfterVisibility = false; tryPlay(); }
  });
  updateSound();
  applyMotionPreference();
})();
