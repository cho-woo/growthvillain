document.addEventListener('DOMContentLoaded', () => {
    const slider1 = document.querySelector('.slider1');
    const slider2 = document.querySelector('.slider2');

    // 슬라이더 복제 함수
    const cloneLogos = (slider, multiplier) => {
        const cloneCount = slider.children.length;
        for (let i = 0; i < cloneCount * multiplier; i++) {
            const clone = slider.children[i % cloneCount].cloneNode(true); // 원본 로고의 클론을 만듭니다.
            slider.appendChild(clone);
        }
    };

    // 슬라이더 복제
    cloneLogos(slider1, 5); // 클론 수를 5배로 늘림
    cloneLogos(slider2, 5); // 클론 수를 5배로 늘림

    let position = 0; // 슬라이더 위치
    const speed = 0.5; // 슬라이더 속도

    // 슬라이더 애니메이션 함수
    const slideLogos = () => {
        position += speed;

        // 첫 번째 슬라이더를 왼쪽으로 이동
        slider1.style.transform = `translateX(-${position}px)`; 

        // 두 번째 슬라이더를 오른쪽으로 이동
        slider2.style.transform = `translateX(-${position}px)`; 

        // 애니메이션 프레임 요청
        requestAnimationFrame(slideLogos);
    };

    // 슬라이드 시작
    slideLogos();
});



    // 개인정보 취급방침 버튼과 팝업 요소 가져오기
    const privacyPolicyBtn = document.getElementById('privacy-policy-btn');
    const privacyPopup = document.getElementById('privacy-popup');
    const closePopupBtn = document.getElementById('close-popup');
    
    // 버튼 클릭 시 팝업 열기
    privacyPolicyBtn.addEventListener('click', function(event) {
        event.preventDefault();
        privacyPopup.style.display = 'block';
    });
    
    // 닫기 버튼 클릭 시 팝업 닫기
    closePopupBtn.addEventListener('click', function() {
        privacyPopup.style.display = 'none';
    });
    
    document.getElementById('contact-form').addEventListener('submit', function(e) {
        e.preventDefault(); // 기본 제출 방지
    
        const formData = new FormData(this);
    
        fetch('../php/save_contact.php', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (response.ok) {
                alert('문의가 성공적으로 전송되었습니다.'); // 피드백 메시지
                window.location.href = 'http://growthvillain.kesug.com/'; // 성공 시 리다이렉트
            } else {
                alert('문의 전송 실패: 다시 시도해주세요.');
                console.error('문의 전송 실패');
            }
        })
        .catch(error => {
            alert('서버와의 연결에 문제가 발생했습니다.');
            console.error('Error:', error);
        });
    });
    


// 페이지 로드 시 텍스트 애니메이션 적용
window.addEventListener('load', () => {
    const title = document.querySelector('.title');
    title.innerHTML = title.textContent.replace(/\S/g, "<span>$&</span>");

    // 각 글자에 딜레이 추가
    const letters = title.querySelectorAll('span');
    letters.forEach((letter, index) => {
        letter.style.animationDelay = `${index * 0.1}s`;
    });
});
