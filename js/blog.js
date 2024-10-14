const postTitle = document.getElementById('post-title');
const postDate = document.getElementById('post-date');
const postContent = document.getElementById('post-content');

// URL에서 포스트 ID 가져오기
const urlParams = new URLSearchParams(window.location.search);
const postId = urlParams.get('id'); // 'post'를 'id'로 변경

// localStorage에서 포스트를 가져옴
let posts = JSON.parse(localStorage.getItem('posts')) || [];

// 해당 포스트의 내용을 화면에 표시
if (postId !== null) {
    // 포스트 ID에 해당하는 포스트 찾기
    const post = posts.find(p => p.id == postId); // 포스트 ID를 비교하여 포스트 찾기
    if (post) {
        postTitle.textContent = post.title; // 제목 설정
        postDate.textContent = post.date; // 작성 날짜 설정
        postContent.innerHTML = post.content; // HTML을 직접 삽입하여 이미지 및 동영상 표시
    } else {
        postTitle.textContent = '포스트를 찾을 수 없습니다.';
        postDate.textContent = ''; 
        postContent.innerHTML = '<p>해당 포스트는 존재하지 않거나 삭제된 상태입니다.</p>'; // 추가 메시지
    }
} else {
    postTitle.textContent = '포스트를 찾을 수 없습니다.';
    postDate.textContent = ''; 
    postContent.innerHTML = '<p>해당 포스트는 존재하지 않거나 삭제된 상태입니다.</p>'; // 추가 메시지
}
