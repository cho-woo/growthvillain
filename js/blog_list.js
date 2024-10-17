const postList = document.getElementById('post-list');
const loading = document.getElementById('loading');
let posts = [];
let currentPostIndex = 0; // 현재 표시된 포스트 인덱스
const postsPerPage = 20; // 한 번에 로드할 포스트 수
let isLoading = false; // 로딩 상태 플래그

// 로컬 스토리지에서 포스트 로드
function loadPostsFromLocalStorage() {
    try {
        posts = JSON.parse(localStorage.getItem('posts')) || [];
    } catch (error) {
        console.error('로컬 저장소에서 포스트를 불러오는 중 오류가 발생했습니다:', error);
        posts = [];
    }
}

// 포스트 목록을 최신순으로 정렬하는 함수
function sortPostsByDate() {
    posts.sort((a, b) => new Date(b.date) - new Date(a.date)); // 내림차순 정렬
}

// 포스트 내용을 잘라내는 함수
function truncateContent(content, maxLength) {
    return content.length > maxLength ? content.substring(0, maxLength) + '...' : content;
}

// 로딩 상태 표시 함수
function showLoading() {
    loading.style.display = 'block';
    loading.textContent = '로딩 중...';
}

// 로딩 상태 숨김 함수
function hideLoading() {
    loading.style.display = 'none';
}

// 포스트 목록을 화면에 표시하는 함수
function renderPosts(startIndex) {
    const endIndex = Math.min(startIndex + postsPerPage, posts.length);
    
    for (let i = startIndex; i < endIndex; i++) {
        const postItem = document.createElement('li');
        postItem.innerHTML = `
            <a href="blog.html?id=${posts[i].id}&slug=${posts[i].slug}"> <!-- SLUG를 URL에 포함 -->
                <div>
                    <strong>${posts[i].title}</strong>
                    <p class="post-preview">${truncateContent(posts[i].content, 100)}</p>
                    <p style="line-height: 30px;">${posts[i].date}</p>
                </div>
            </a>
        `;
        postList.appendChild(postItem);
    }
    
    currentPostIndex += postsPerPage; // 현재 인덱스 업데이트
}


// 스크롤 이벤트 핸들러 (throttle 적용)
let throttleTimer;
function handleScrollEvent() {
    if (throttleTimer) return;
    
    throttleTimer = setTimeout(() => {
        const { scrollTop, clientHeight, scrollHeight } = document.documentElement;

        if (scrollTop + clientHeight >= scrollHeight - 5 && currentPostIndex < posts.length && !isLoading) {
            isLoading = true;
            showLoading();

            setTimeout(() => {
                renderPosts(currentPostIndex);
                hideLoading();
                isLoading = false;
            }, 1000); // 로딩 효과를 위해 약간의 지연 추가
        }

        if (currentPostIndex >= posts.length) {
            hideLoading(); // 더 이상 로드할 포스트가 없으므로 로딩 숨기기
        }

        throttleTimer = null;
    }, 200); // 200ms throttle 적용
}

// 초기 설정
loadPostsFromLocalStorage();
sortPostsByDate();
renderPosts(currentPostIndex);

// 스크롤 이벤트 리스너 추가
window.addEventListener('scroll', handleScrollEvent);
