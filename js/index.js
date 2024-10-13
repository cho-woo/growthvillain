document.addEventListener('DOMContentLoaded', () => {
    const video = document.querySelector('.background-video');
    const mainTitle = document.querySelector('.main-title');

    // 메인 타이틀 호버 시 백그라운드 영상 속도 조절
    if (mainTitle) {
        mainTitle.addEventListener('mouseenter', () => {
            video.playbackRate = 5;
            video.play();
        });

        mainTitle.addEventListener('mouseleave', () => {
            video.playbackRate = 1;
            video.play();
        });
    }

    const slider1 = document.querySelector('.slider1');
    const slider2 = document.querySelector('.slider2');

    // 슬라이더 복제 함수
    const cloneLogos = (slider) => {
        const cloneCount = slider.children.length;
        for (let i = 0; i < cloneCount; i++) {
            const clone = slider.children[i].cloneNode(true);
            slider.appendChild(clone);
        }
    };

    // 슬라이더 복제
    cloneLogos(slider1);
    cloneLogos(slider2);

    let position1 = 0; // 첫 번째 슬라이더 위치
    let position2 = 0; // 두 번째 슬라이더 위치
    const speed = 0.5; // 슬라이더 속도

    // 슬라이더 애니메이션 함수
    const slideLogos = () => {
        // 첫 번째 슬라이더 왼쪽으로 이동
        position1 += speed;
        if (position1 >= slider1.scrollWidth / 2) {
            position1 = 0;
        }
        slider1.style.transform = `translateX(-${position1}px)`; // 왼쪽으로 이동

        // 두 번째 슬라이더 오른쪽으로 이동
        position2 -= speed;
        if (position2 <= -slider2.scrollWidth / 2) {
            position2 = 0;
        }
        slider2.style.transform = `translateX(${position2}px)`; // 오른쪽으로 이동

        // 애니메이션 프레임 요청
        requestAnimationFrame(slideLogos);
    };

    // 슬라이드 시작
    slideLogos();
});
