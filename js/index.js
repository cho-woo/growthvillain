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
