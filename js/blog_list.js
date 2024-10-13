const postList = document.getElementById('post-list');
const loading = document.getElementById('loading');
let posts = JSON.parse(localStorage.getItem('posts')) || [];
let currentPostIndex = 0; // 현재 표시된 포스트 인덱스
const postsPerPage = 20; // 한 번에 로드할 포스트 수
let isLoading = false; // 로딩 상태 플래그

// 포스트 목록을 최신순으로 정렬하는 함수
function sortPostsByDate() {
    posts.sort((a, b) => new Date(b.date) - new Date(a.date)); // 내림차순 정렬
}

// 포스트 내용을 잘라내는 함수
function truncateContent(content, maxLength) {
    return content.length > maxLength ? content.substring(0, maxLength) + '...' : content;
}

// 포스트 목록을 화면에 표시하는 함수
function renderPosts(startIndex) {
    const endIndex = Math.min(startIndex + postsPerPage, posts.length);
    
    for (let i = startIndex; i < endIndex; i++) {
        const postItem = document.createElement('li');
        postItem.innerHTML = `
            <a href="blog.html?id=${posts[i].id}"> <!-- 'post'를 'id'로 변경 -->
                <div>
                    <strong>${posts[i].title}</strong>
                    <p class="post-preview">${truncateContent(posts[i].content, 100)}</p> <!-- 미리보기 적용, 최대 100자 -->
                    <p style="line-height: 30px;">${posts[i].date}</p>
                </div>
            </a>
        `;
        postList.appendChild(postItem);
    }
    
    currentPostIndex += postsPerPage; // 현재 인덱스 업데이트
}


// 포스트를 정렬하고 초기 포스트 렌더링
sortPostsByDate(); // 포스트 정렬
renderPosts(currentPostIndex);

// 스크롤 이벤트 리스너
window.addEventListener('scroll', () => {
    const { scrollTop, clientHeight, scrollHeight } = document.documentElement;
    
    // 페이지의 끝에 가까워졌고 현재 로딩 중이 아닐 때
    if (scrollTop + clientHeight >= scrollHeight - 5 && currentPostIndex < posts.length && !isLoading) {
        isLoading = true; // 로딩 상태 시작
        loading.style.display = 'block'; // 로딩 표시
        loading.textContent = '로딩 중...'; // 로딩 메시지 추가

        setTimeout(() => {
            renderPosts(currentPostIndex);
            loading.style.display = 'none'; // 로딩 숨기기
            isLoading = false; // 로딩 상태 종료
        }, 1000); // 로딩 효과를 위해 약간의 지연 추가
    }

    // 모든 포스트가 로드된 경우 로딩 표시 숨기기
    if (currentPostIndex >= posts.length) {
        loading.style.display = 'none'; // 더 이상 로드할 포스트가 없으므로 로딩 숨기기
    }
});
