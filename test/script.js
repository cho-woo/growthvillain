// 페이지 로드 시 애니메이션 효과 추가
window.addEventListener('load', () => {
    // 배경색과 텍스트 애니메이션을 위한 클래스 추가
    document.body.classList.add('fade-in');
    const container = document.querySelector('.container');
    container.classList.add('fade-in');

    // 텍스트 애니메이션 설정
    const title = document.querySelector('.title');
    title.innerHTML = title.textContent.replace(/\S/g, "<span>$&</span>");

    // 각 글자에 딜레이 추가
    const letters = title.querySelectorAll('span');
    letters.forEach((letter, index) => {
        letter.style.animationDelay = `${index * 0.1}s`;
    });
});
