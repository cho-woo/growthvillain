// 모든 페이지에 공통으로 적용되는 JS

// DOMContentLoaded 이벤트로 모든 DOM이 로드된 후 실행
document.addEventListener("DOMContentLoaded", function() {
    // 메뉴 열기 및 닫기 기능
    const mobileMenu = document.getElementById('mobile-menu');
    const slideMenu = document.getElementById('slide-menu');
    const closeMenu = document.getElementById('close-menu');
    const header = document.querySelector('header'); // 헤더 요소 선택

    if (mobileMenu) {
        mobileMenu.addEventListener('click', function() {
            slideMenu.classList.toggle('show'); // 슬라이드 메뉴에 'show' 클래스 토글
        });
    }

    // 닫기 버튼 클릭 시 메뉴 닫기
    if (closeMenu) {
        closeMenu.addEventListener('click', function() {
            slideMenu.classList.remove('show'); // 'show' 클래스 제거
        });
    }

    // 스크롤 이벤트 핸들러
    let lastScrollTop = 0; // 마지막 스크롤 위치 초기화

    window.addEventListener('scroll', function() {
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;

        if (scrollTop > lastScrollTop) {
            // 아래로 스크롤할 때 헤더 숨기기
            header.style.top = '-80px'; // 헤더 높이 만큼 위로 숨김 (헤더의 높이에 따라 값 조정 필요)
        } else {
            // 위로 스크롤할 때 헤더 보이기
            header.style.top = '0'; // 헤더 보이기
        }

        lastScrollTop = scrollTop; // 마지막 스크롤 위치 업데이트
    });
});
