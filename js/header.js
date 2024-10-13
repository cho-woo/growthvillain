// 모든 페이지에 공통으로 적용되는 JS //

// DOMContentLoaded 이벤트로 모든 DOM이 로드된 후 실행
document.addEventListener("DOMContentLoaded", function() {
    // 메뉴 열기 및 닫기 기능
    const mobileMenu = document.getElementById('mobile-menu');
    const slideMenu = document.getElementById('slide-menu');
    const closeMenu = document.getElementById('close-menu');

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
});
