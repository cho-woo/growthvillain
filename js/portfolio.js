document.addEventListener("DOMContentLoaded", function() {
    const portfolioItems = document.querySelectorAll('.portfolio-item');

    function checkScroll() {
        const triggerBottom = window.innerHeight;

        portfolioItems.forEach(item => {
            const boxTop = item.getBoundingClientRect().top;

            if (boxTop < triggerBottom) {
                item.classList.add('visible'); // 요소가 보일 때 클래스 추가
            }
        });
    }

    // 페이지 로드 시 체크
    checkScroll();
    
    // 스크롤 이벤트 발생 시 체크
    window.addEventListener('scroll', checkScroll);
    
    // 무한 스크롤 구현 (추가 데이터 로딩)
    window.addEventListener('scroll', () => {
        if (window.innerHeight + window.scrollY >= document.body.offsetHeight) {
            // 여기서 추가 포트폴리오 아이템을 로드하는 로직 추가
            loadMorePortfolioItems();
        }
    });
    
    function loadMorePortfolioItems() {
        // AJAX 요청이나 다른 방법으로 추가 포트폴리오 아이템을 로드하는 로직
        // 예: DOM에 새로운 .portfolio-item을 추가
        // const newItem = document.createElement('div');
        // newItem.className = 'portfolio-item';
        // newItem.innerHTML = '새로운 아이템'; // 새 아이템의 내용
        // document.querySelector('.portfolio-grid').appendChild(newItem);
        
        // 추가된 아이템에 애니메이션 적용
        // checkScroll(); // 새 아이템이 추가된 후 다시 체크
    }
});
