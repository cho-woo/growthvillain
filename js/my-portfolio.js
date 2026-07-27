// 스크롤 reveal + 숫자 카운트업 애니메이션
document.addEventListener('DOMContentLoaded', function () {
    const revealEls = document.querySelectorAll('.reveal');
    const countEls = document.querySelectorAll('[data-count]');

    function animateCount(el) {
        const target = parseInt(el.getAttribute('data-count'), 10);
        if (isNaN(target)) return;
        const duration = 900;
        const start = performance.now();

        function tick(now) {
            const progress = Math.min((now - start) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
            el.textContent = Math.round(target * eased).toLocaleString('ko-KR');
            if (progress < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
    }

    const observer = new IntersectionObserver(function (entries, obs) {
        entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            entry.target.classList.add('mp-visible');

            if (entry.target.hasAttribute('data-count')) {
                animateCount(entry.target);
            } else {
                entry.target.querySelectorAll('[data-count]').forEach(animateCount);
            }

            obs.unobserve(entry.target);
        });
    }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });

    revealEls.forEach(function (el, i) {
        el.style.transitionDelay = (i % 4) * 0.08 + 's';
        observer.observe(el);
    });

    countEls.forEach(function (el) {
        observer.observe(el);
    });
});
