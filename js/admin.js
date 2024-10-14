const postForm = document.getElementById('post-form');
const postList = document.getElementById('postList');
let posts = JSON.parse(localStorage.getItem('posts')) || [];

// 한 페이지당 게시글 수
const postsPerPage = 5; 
let currentPage = 1; 

// 포스트 목록을 화면에 표시하는 함수
function renderPosts() {
    const validPosts = posts.filter(post => post && post.title && post.content && post.date);
    validPosts.reverse(); // 최신 포스트가 위로 오도록

    // 페이지네이션을 고려하여 포스트 표시
    const totalPosts = validPosts.length;
    const totalPages = Math.ceil(totalPosts / postsPerPage);
    const startIndex = (currentPage - 1) * postsPerPage;
    const endIndex = startIndex + postsPerPage;
    const paginatedPosts = validPosts.slice(startIndex, endIndex);

    postList.innerHTML = ''; // 포스트 목록 초기화

    paginatedPosts.forEach((post) => {
        const postDiv = document.createElement('li');
        postDiv.innerHTML = `
            <div>
                <strong>${post.title}</strong> - ${post.date}
                <p>${post.content}</p>
                <button onclick="editPost(${post.id})">수정</button>
                <button onclick="deletePost(${post.id})">삭제</button>
                <button onclick="viewPost(${post.id})">보기</button> <!-- post.id로 ID 전달 -->
            </div>
        `;
        postList.appendChild(postDiv);
    });

    if (paginatedPosts.length === 0) {
        postList.innerHTML = '<li>포스트가 없습니다.</li>'; 
    }


    // 포스트 내용 줄 제한
    limitPostContentLines();

    // 페이지네이션 업데이트
    updatePagination(totalPages);
}

// 페이지 번호 버튼 출력
function updatePagination(totalPages) {
    const paginationDiv = document.getElementById('pagination');
    paginationDiv.innerHTML = ''; // 초기화

    for (let i = 1; i <= totalPages; i++) {
        const button = document.createElement('button');
        button.innerText = i;
        button.classList.add('page-button');
        button.onclick = () => {
            currentPage = i; // 현재 페이지 업데이트
            renderPosts(); // 게시글 표시
        };
        paginationDiv.appendChild(button);
    }
}

// 포스트 내용 줄 제한 함수
function limitPostContentLines() {
    document.querySelectorAll('#postList > li > div > p').forEach(function(p) {
        const originalText = p.textContent;
        const lineHeight = parseFloat(getComputedStyle(p).lineHeight);
        const maxLines = 3; // 최대 줄 수
        const maxHeight = lineHeight * maxLines;

        p.style.overflow = 'hidden'; // 넘치는 내용 숨기기

        if (p.scrollHeight > maxHeight) {
            let truncatedText = originalText;
            while (p.scrollHeight > maxHeight && truncatedText.length > 0) {
                truncatedText = truncatedText.slice(0, -1);
                p.textContent = truncatedText + '...';
            }
        }
    });
}

// 초기 포스트 렌더링
renderPosts();

let currentEditingIndex = null; // 현재 수정 중인 포스트 인덱스
// 새로운 포스트 추가
function addPost() {
    const title = document.getElementById('post-title').value;
    const content = document.getElementById('post-content').innerHTML;

    if (title && content) {
        const newPost = {
            id: Date.now(), // 고유한 ID 할당
            title: title,
            content: content,
            date: new Date().toISOString(),
        };

        posts.push(newPost);
        localStorage.setItem('posts', JSON.stringify(posts));
        renderPosts();
        postForm.reset();
    } else {
        alert('제목과 내용을 입력하세요.');
    }
}

// 포스트 수정
function editPost(postId) {
    const post = posts.find(p => p.id === postId); // ID를 기반으로 포스트 검색
    if (post) {
        document.getElementById('post-title').value = post.title;
        document.getElementById('post-content').innerHTML = post.content;

        document.querySelector('.btn-primary[type="button"]').style.display = 'none'; // 작성 버튼 숨기기
        document.getElementById('edit-complete').style.display = 'inline-block'; // 수정 완료 버튼 보이기

        currentEditingIndex = postId; // 현재 수정 중인 포스트 ID 저장
    }
}

// 수정 완료
document.getElementById('edit-complete').onclick = (e) => {
    e.preventDefault();

    if (currentEditingIndex !== null) {
        const index = posts.findIndex(p => p.id === currentEditingIndex); // 현재 수정 중인 포스트 인덱스 찾기
        if (index > -1) {
            posts[index] = {
                id: currentEditingIndex,
                title: document.getElementById('post-title').value,
                content: document.getElementById('post-content').innerHTML,
                date: new Date().toISOString(),
            };

            localStorage.setItem('posts', JSON.stringify(posts));
            renderPosts();
            postForm.reset();
            alert('수정되었습니다.');

            // 버튼 상태 초기화
            resetButtons();
        }
    }
};

// 포스트 삭제
function deletePost(postId) {
    const index = posts.findIndex(p => p.id === postId);
    if (index > -1) {
        posts.splice(index, 1);
        localStorage.setItem('posts', JSON.stringify(posts));
        renderPosts();
        alert('삭제되었습니다.');
    }
}



// 포스트 보기
function viewPost(postId) {
    const postUrl = `blog.html?id=${postId}`; // 'post'를 사용하여 URL 전달
    window.location.href = postUrl; // 포스트 링크로 이동
}



// 버튼 상태 초기화
function resetButtons() {
    document.querySelector('.btn-primary[type="button"]').style.display = 'inline-block'; // 작성 버튼 보이기
    document.getElementById('edit-complete').style.display = 'none'; // 수정 완료 버튼 숨기기
    currentEditingIndex = null; // 수정 중인 포스트 ID 초기화
    document.getElementById('post-title').value = ''; // 제목 필드 초기화
    document.getElementById('post-content').innerHTML = ''; // 내용 필드 초기화
}

// 인용구 추가
document.getElementById('quoteButton').addEventListener('click', function() {
    const quote = prompt("인용구를 입력하세요:");
    if (quote) {
        document.getElementById('post-content').innerHTML += `<blockquote>${quote}</blockquote>`; // 블록 인용 추가
    }
});

// 파일 첨부 기능 구현
document.getElementById('fileUpload').addEventListener('click', function() {
    const input = document.createElement('input');
    input.type = 'file';

    input.addEventListener('change', function(event) {
        const files = event.target.files;
        const filePreviewContainer = document.getElementById('filePreview');
        filePreviewContainer.innerHTML = ''; 

        Array.from(files).forEach(file => {
            const fileName = document.createElement('div');
            fileName.textContent = file.name; 
            const removeButton = document.createElement('button');
            removeButton.textContent = '삭제';
            removeButton.onclick = () => fileName.remove(); // 삭제 기능
            filePreviewContainer.appendChild(fileName);
            filePreviewContainer.appendChild(removeButton);
        });
    });

    input.click(); 
});

// 구분선 추가
document.getElementById('dividerButton').addEventListener('click', function() {
    document.getElementById('post-content').innerHTML += '<hr>'; // HTML로 구분선 추가
});

// URL 링크 추가
document.getElementById('linkButton').addEventListener('click', function() {
    const url = prompt("링크를 입력하세요:");
    const linkText = prompt("링크에 사용할 텍스트를 입력하세요:");
    if (url && linkText) {
        document.getElementById('post-content').innerHTML += `<a href="${url}" target="_blank">${linkText}</a>`; 
    }
});

// 이미지 업로드 및 미리보기
document.getElementById('uploadImage').addEventListener('click', function(event) {
    event.preventDefault(); 
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';

    input.addEventListener('change', function(event) {
        const file = event.target.files[0]; 

        if (file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                const imageUrl = e.target.result; 
                const imgElement = document.createElement('img');
                imgElement.src = imageUrl; 
                imgElement.style.maxWidth = '100%'; 
                imgElement.style.height = 'auto'; 

                const postContent = document.getElementById('post-content');
                postContent.innerHTML += `<img src="${imageUrl}" style="max-width:100%; height:auto;" />`; // HTML로 추가
            };
            reader.readAsDataURL(file); 
        }
    });

    input.click(); 
});

// 동영상 업로드 및 미리보기
document.getElementById('uploadVideo').addEventListener('click', function(event) {
    event.preventDefault(); 
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'video/*';

    input.addEventListener('change', function(event) {
        const file = event.target.files[0]; 

        if (file) {
            const videoUrl = URL.createObjectURL(file); 
            
            const videoElement = document.createElement('video');
            videoElement.src = videoUrl;
            videoElement.controls = true; 
            videoElement.style.width = '100%'; 
            videoElement.style.maxWidth = '200px'; 
            videoElement.style.display = 'block';
            videoElement.style.margin = '10px 0'; 

            const postContent = document.getElementById('post-content');
            postContent.appendChild(videoElement); // appendChild를 사용하여 추가
        }
    });

    input.click(); 
});

// 초기 포스트 렌더링
renderPosts();

