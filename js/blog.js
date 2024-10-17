const postTitle = document.getElementById('post-title');
const postSubtitle = document.getElementById('post-subtitle');
const postDate = document.getElementById('post-date');
const postContent = document.getElementById('post-content');

// URL에서 포스트 ID 가져오기
const urlParams = new URLSearchParams(window.location.search);
const postId = urlParams.get('id');

// localStorage에서 포스트를 가져옴
let posts = [];

// 날짜 포맷팅 함수
function formatDateToKST(isoDate) {
    const date = new Date(isoDate);
    const kstOffset = 9 * 60;
    const utcDate = date.getTime() + (date.getTimezoneOffset() * 60000);
    const kstDate = new Date(utcDate + (kstOffset * 60000));
    
    const year = kstDate.getFullYear();
    const month = String(kstDate.getMonth() + 1).padStart(2, '0');
    const day = String(kstDate.getDate()).padStart(2, '0');
    const hours = String(kstDate.getHours()).padStart(2, '0');
    const minutes = String(kstDate.getMinutes()).padStart(2, '0');
    const seconds = String(kstDate.getSeconds()).padStart(2, '0');

    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
}

// 포스트를 날짜별로 정렬하는 함수
function sortPostsByDate() {
    posts.sort((a, b) => new Date(b.date) - new Date(a.date));
}

// 해당 포스트의 내용을 화면에 표시
function renderPostDetails() {
    if (postId !== null) {
        const post = posts.find(p => p.id === Number(postId));
        if (post) {
            postTitle.textContent = post.title;
            postSubtitle.textContent = post.subtitle;
            postDate.innerHTML = `<span class="admin-label">by.villain01</span> <span class="date">${formatDateToKST(post.date)}</span>`;
            postContent.innerHTML = post.content;
        } else {
            postTitle.textContent = '포스트를 찾을 수 없습니다.';
            postSubtitle.textContent = '';
            postDate.textContent = '';
            postContent.innerHTML = '<p>해당 포스트는 존재하지 않거나 삭제된 상태입니다.</p>';
        }
    } else {
        postTitle.textContent = '포스트를 찾을 수 없습니다.';
        postSubtitle.textContent = '';
        postDate.textContent = '';
        postContent.innerHTML = '<p>해당 포스트는 존재하지 않거나 삭제된 상태입니다.</p>';
    }
}


// 추천 글을 표시하는 함수
function renderSuggestions() {
    const suggestionsContainer = document.querySelector('.suggestion');
    suggestionsContainer.innerHTML = ''; // 기존 내용 초기화

    // 추천할 포스트를 선택 (여기서는 5개로 제한)
    const suggestedPosts = posts.slice(0, 5);

    suggestedPosts.forEach(post => {
        const suggestionItem = document.createElement('div');
        suggestionItem.className = 'suggestion-item';
        
        // 전체 영역을 클릭 가능하게 하기 위해 a 태그로 감쌈
        suggestionItem.innerHTML = `
            <a href="blog.html?id=${post.id}&slug=${post.slug}" class="suggestion-link">
                <h3>${post.title}</h3>
                <p>${post.subtitle}</p>
                <span>${formatDateToKST(post.date)}</span>
            </a>
        `;
        
        suggestionsContainer.appendChild(suggestionItem);
    });
}




// 초기 포스트 렌더링
function initializePosts() {
    loadPostsFromLocalStorage();
    sortPostsByDate();
    renderPostDetails();
    renderSuggestions();
}

// 로컬 스토리지에서 포스트를 가져오는 함수
function loadPostsFromLocalStorage() {
    try {
        posts = JSON.parse(localStorage.getItem('posts')) || [];
        console.log('로컬 저장소에서 포스트를 가져왔습니다:', posts);
        if (posts.length === 0) {
            console.log('로컬 저장소에 포스트가 없습니다.');
        }
    } catch (error) {
        console.error('로컬 저장소에서 포스트를 불러오는 중 오류가 발생했습니다:', error);
        posts = [];
    }
}

// 페이지 초기화
document.addEventListener('DOMContentLoaded', initializePosts);
