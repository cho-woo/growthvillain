document.getElementById('contact-form').addEventListener('submit', function(e) {
    e.preventDefault();

    // Form 데이터를 수집
    const formData = new FormData(this);

    // Fetch API를 이용해 Python 백엔드에 요청 보내기
    fetch('/send-email', {
        method: 'POST',
        body: formData
    }).then(response => {
        if (response.ok) {
            alert('문의가 성공적으로 전송되었습니다.');
        } else {
            alert('전송 중 오류가 발생했습니다.');
        }
    }).catch(error => {
        alert('전송 중 오류가 발생했습니다.');
    });
});

// 문의 폼 전송 이벤트 처리
document.getElementById('contact-form').addEventListener('submit', function(e) {
    e.preventDefault(); // 기본 동작 방지

    // Form 데이터를 수집
    const formData = new FormData(this);

    // Fetch API를 이용해 Python 백엔드에 요청 보내기
    fetch('/send-email', {
        method: 'POST',
        body: formData
    }).then(response => {
        if (response.ok) {
            alert('문의가 성공적으로 전송되었습니다.');
        } else {
            alert('전송 중 오류가 발생했습니다.');
        }
    }).catch(error => {
        alert('전송 중 오류가 발생했습니다.');
    });
});

// 모바일 메뉴 토글 스크립트
const mobileMenu = document.getElementById('mobile-menu');
const slideMenu = document.getElementById('slide-menu');
const closeMenu = document.getElementById('close-menu');

// 모바일 메뉴 버튼을 클릭하면 메뉴를 슬라이드로 보여줌
mobileMenu.addEventListener('click', () => {
    slideMenu.classList.add('show');
});

// 닫기 버튼을 클릭하면 슬라이드 메뉴가 사라짐
closeMenu.addEventListener('click', () => {
    slideMenu.classList.remove('show');
});

