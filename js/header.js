// 비동기적으로 헤더와 푸터를 불러오기 위한 함수
async function loadHeaderFooter() {
    // 헤더와 푸터를 각각 fetch로 불러온 후 innerHTML에 삽입
    const headerResponse = await fetch('../header.html');
    const footerResponse = await fetch('../footer.html');
    const sliderResponse = await fetch('../slider.html');
    
    const headerText = await headerResponse.text();
    const footerText = await footerResponse.text();
    const sliderText = await sliderResponse.text();

    // 콘솔에 불러온 텍스트를 출력하여 확인합니다.
    console.log("헤더 텍스트: ", headerText);  // 헤더 파일 내용
    console.log("푸터 텍스트: ", footerText);  // 푸터 파일 내용
    console.log("슬라이더 텍스트: ", sliderText);  // 슬라이더 파일 내용

    // 'header', 'footer', 'slider' 요소에 불러온 텍스트를 삽입합니다.
    document.getElementById('header').innerHTML = headerText;
    document.getElementById('footer').innerHTML = footerText;
    document.getElementById('slider').innerHTML = sliderText;

    // 헤더가 로드된 후 스크롤 이벤트를 적용합니다.
    setupScrollEvent();
}

// 헤더의 스크롤 동작을 설정하는 함수
function setupScrollEvent() {
    const header = document.getElementById('header');  // 'header' div를 가져옵니다.

    if (!header) return;  // 만약 header가 없으면 함수 종료

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
}

// 페이지 로드 시 헤더와 푸터를 불러오는 함수 실행
window.addEventListener("DOMContentLoaded", loadHeaderFooter);
