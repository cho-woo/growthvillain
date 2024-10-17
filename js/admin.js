const postForm = document.getElementById('post-form');
const postList = document.getElementById('postList');
let posts = JSON.parse(localStorage.getItem('posts')) || [];
let undoStack = []; // 실행 취소 스택
let redoStack = []; // 다시 실행 스택


// 한 페이지당 게시글 수
const postsPerPage = 5; 
let currentPage = 1; 

// 날짜 포맷팅 함수
function formatDateToKST(isoDate) {
    const date = new Date(isoDate);
    
    // KST(한국 표준시)로 변환
    const kstOffset = 9 * 60; // KST는 UTC+9
    const utcDate = date.getTime() + (date.getTimezoneOffset() * 60000);
    const kstDate = new Date(utcDate + (kstOffset * 60000));

    // 형식화
    const year = kstDate.getFullYear();
    const month = String(kstDate.getMonth() + 1).padStart(2, '0'); // 1월은 0부터 시작
    const day = String(kstDate.getDate()).padStart(2, '0');
    const hours = String(kstDate.getHours()).padStart(2, '0');
    const minutes = String(kstDate.getMinutes()).padStart(2, '0');
    const seconds = String(kstDate.getSeconds()).padStart(2, '0');

    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
}

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
        const formattedDate = formatDateToKST(post.date); // 날짜 포맷팅
        const postDiv = document.createElement('li');
        postDiv.innerHTML = `
            <div>
                <strong>${post.title}</strong> - ${formattedDate} <!-- 포맷된 날짜 사용 -->
                <p>${post.subtitle || ''}</p> <!-- 부제목 표시 -->
                <div class="limit-lines">${post.content}</div> <!-- 내용을 div로 묶어 줄 제한 적용 -->
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
    const subtitle = document.getElementById('post-subtitle').value; // 부제목 추가

    if (title && content) {
        const slug = createSlug(title); // 제목을 URL-friendly한 형태로 변환
        const newPost = {
            id: Date.now(), // 고유한 ID 할당
            title: title,
            content: content,
            subtitle: subtitle, // 부제목 추가
            date: new Date().toISOString(),
            slug: slug, // 슬러그 추가
        };

        posts.push(newPost);
        localStorage.setItem('posts', JSON.stringify(posts));
        renderPosts();
        postForm.reset();

        // 생성된 URL을 보여주는 부분 추가
        const postUrl = `blog.html?id=${newPost.id}&slug=${slug}`;
        const urlDisplay = document.getElementById('url-display'); // URL을 표시할 HTML 요소
        urlDisplay.textContent = `작성 완료! 포스트 URL: ${postUrl}`; // URL 표시

    } else {
        alert('제목과 내용을 입력하세요.');
    }
}



// 제목을 URL-friendly한 형태로 변환하는 함수
function createSlug(title) {
    return title
        .toLowerCase() // 소문자로 변환
        .replace(/[^가-힣a-z0-9]+/g, '-') // 한글, 알파벳과 숫자 외의 문자들을 하이픈으로 변환
        .replace(/^-+|-+$/g, ''); // 시작과 끝의 하이픈 제거
}



// 포스트 수정
function editPost(postId) {
    const post = posts.find(p => p.id === postId); // ID를 기반으로 포스트 검색
    if (post) {
        document.getElementById('post-title').value = post.title;
        document.getElementById('post-subtitle').value = post.subtitle; // 부제목 필드에 값 설정
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
                subtitle: document.getElementById('post-subtitle').value, // 부제목 저장
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
// 보기 버튼 클릭 시 URL 생성 (유지)
function viewPost(postId) {
    const post = posts.find(p => p.id === postId);
    if (post) {
        const postUrl = `blog.html?id=${post.id}&slug=${post.slug}`; // URL에 ID와 SLUG 포함
        window.location.href = postUrl; // 해당 URL로 이동
    }
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
// 이미지 업로드
document.getElementById('uploadImage').addEventListener('click', function(event) {
    event.preventDefault();
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';

    input.addEventListener('change', function(event) {
        const file = event.target.files[0];

        if (file) {
            const formData = new FormData();
            formData.append('file', file);

            // 파일을 서버로 전송
            fetch('http://localhost:8000/upload.php', {
                method: 'POST',
                body: formData,
                mode: 'cors' // CORS 모드 설정
            })
            .then(response => response.json())
            .then(data => {
                if (data.url) {
                    const imageUrl = data.url;
                    const fileName = file.name; // 파일 이름 추출

                    // 이미지와 리사이저를 감싸는 새로운 div 생성
                    const wrapper = document.createElement('div');
                    wrapper.classList.add('resizable');
                    wrapper.style.position = 'relative';

                    const imgElement = document.createElement('img');
                    imgElement.src = imageUrl; // 서버에서 반환된 URL 사용
                    imgElement.style.maxWidth = '100%';
                    imgElement.style.height = 'auto';
                    imgElement.alt = fileName; // alt 속성에 파일 이름 설정

                    // 리사이저 추가
                    const resizer = document.createElement('div');
                    resizer.classList.add('resizer');
                    resizer.style.position = 'absolute';
                    resizer.style.bottom = '0';
                    resizer.style.right = '0';
                    resizer.style.cursor = 'nwse-resize';

                    // 리사이저 드래그 기능
                    resizer.addEventListener('mousedown', function(e) {
                        e.preventDefault();
                        const startX = e.clientX;
                        const startY = e.clientY;
                        const startWidth = imgElement.offsetWidth;
                        const startHeight = imgElement.offsetHeight;

                        const aspectRatio = startWidth / startHeight;

                        function resize(e) {
                            let newWidth = startWidth + (e.clientX - startX);
                            let newHeight;

                            if (e.shiftKey) {
                                newHeight = newWidth / aspectRatio;
                            } else {
                                newHeight = startHeight + (e.clientY - startY);
                            }

                            imgElement.style.width = newWidth + 'px';
                            imgElement.style.height = newHeight + 'px';
                        }

                        function stopResize() {
                            window.removeEventListener('mousemove', resize);
                            window.removeEventListener('mouseup', stopResize);
                        }

                        window.addEventListener('mousemove', resize);
                        window.addEventListener('mouseup', stopResize);
                    });

                    // wrapper에 이미지와 리사이저 추가
                    wrapper.appendChild(imgElement);
                    wrapper.appendChild(resizer);

                    // 텍스트 입력을 위한 input 필드 생성
                    const textInput = document.createElement('input');
                    textInput.type = 'text'; // 텍스트 입력 필드
                    textInput.placeholder = '이미지에 대한 설명을 입력하세요'; // 플레이스홀더
                    textInput.style.marginTop = '2px'; // 이미지와 텍스트 사이의 여백
                    textInput.style.border = '1px solid gray'; // 얇은 테두리
                    textInput.style.backgroundColor = '#f0f0f0'; // 회색 배경
                    textInput.style.color = 'black'; // 텍스트 색상 설정
                    textInput.style.padding = '3px'; // 패딩 추가
                    textInput.style.width = '80%'; // 너비 조정
                    textInput.style.display = 'block'; // 블록 요소로 설정
                    textInput.style.marginLeft = 'auto'; // 가운데 정렬을 위한 좌우 여백 설정
                    textInput.style.marginRight = 'auto';
                    textInput.style.textAlign = 'center'; // 텍스트 가운데 정렬

                    // 포스트 내용에 wrapper 추가
                    const postContent = document.getElementById('post-content');
                    postContent.appendChild(wrapper);
                    postContent.appendChild(textInput); // 텍스트 입력 영역 추가

                    // 입력 완료 후 <p> 태그로 변환
                    textInput.addEventListener('keydown', function(e) {
                        if (e.key === 'Enter') {
                            e.preventDefault(); // 엔터 키 기본 동작 방지
                            const pElement = document.createElement('p');
                            pElement.textContent = textInput.value; // input의 값으로 p 태그 내용 설정
                            pElement.style.textAlign = 'center'; // p 태그 가운데 정렬
                            postContent.appendChild(pElement); // p 태그 추가
                            textInput.style.display = 'none'; // input 필드 숨기기
                        }
                    });
                } else {
                    alert(data.error);
                }
            })
            .catch(error => {
                console.error('Error:', error);
            });
        }
    });

    input.click();
});


document.getElementById('post-content').addEventListener('keydown', function(event) {
    if (event.key === 'Enter') {
        event.preventDefault(); // 기본 엔터키 동작 방지
        document.execCommand('insertHTML', false, '<br><br>'); // 두 개의 <br> 태그 삽입
    }
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


// 실행 취소 및 다시 실행 기능
function executeUndo() {
    if (undoStack.length > 0) {
        redoStack.push(document.getElementById('post-content').innerHTML); // 현재 내용을 redoStack에 추가
        document.getElementById('post-content').innerHTML = undoStack.pop(); // undoStack에서 마지막 내용을 꺼내서 적용
    }
}

function executeRedo() {
    if (redoStack.length > 0) {
        undoStack.push(document.getElementById('post-content').innerHTML); // 현재 내용을 undoStack에 추가
        document.getElementById('post-content').innerHTML = redoStack.pop(); // redoStack에서 마지막 내용을 꺼내서 적용
    }
}

// 내용 변경 시 undo 스택에 추가
document.getElementById('post-content').addEventListener('input', function() {
    undoStack.push(document.getElementById('post-content').innerHTML); // 내용 변경 시 스택에 추가
    redoStack = []; // 새 내용이 입력되면 redoStack 초기화
});

// 키보드 이벤트 리스너
document.addEventListener('keydown', function(event) {
    if (event.ctrlKey && event.key === 'z') { // Ctrl + Z
        event.preventDefault();
        executeUndo();
    } else if (event.ctrlKey && event.key === 'y') { // Ctrl + Y
        event.preventDefault();
        executeRedo();
    }
});



document.addEventListener('DOMContentLoaded', function() {
    document.addEventListener('keydown', function(event) {
        // Alt + H 단축키를 체크
        if (event.altKey && event.key === 'h') {
            event.preventDefault(); // 기본 동작 방지

            // 구분선 div 생성
            const divider = document.createElement('div');
            divider.classList.add('divider');
            divider.style.borderBottom = '1px solid #ccc'; // 구분선 스타일 추가
            divider.style.margin = '10px 0'; // 위아래 여백 추가
            divider.style.height = '1px'; // 높이 설정 (구분선)
            divider.style.width = '100%'; // 너비 설정

            // 포스트 콘텐츠에 구분선 추가
            const postContent = document.getElementById('post-content');

            // 선택된 위치에 구분선 삽입
            const selection = window.getSelection();
            if (selection.rangeCount > 0) {
                const range = selection.getRangeAt(0);
                range.insertNode(divider);
                range.setStartAfter(divider); // 구분선 뒤로 커서 이동
                range.collapse(true);
                selection.removeAllRanges();
                selection.addRange(range);
            }
        }
    });
});



let currentTag = 'p'; // 기본값으로 p 태그를 설정

// h2, h3, h4, h5, p 버튼 추가
const h2Button = document.createElement('button');
h2Button.textContent = 'H2';
h2Button.type = 'button';
h2Button.style.padding = '8px 14px';
h2Button.addEventListener('click', () => applyFormat('h2'));

const h3Button = document.createElement('button');
h3Button.textContent = 'H3';
h3Button.type = 'button';
h3Button.style.padding = '8px 14px';
h3Button.addEventListener('click', () => applyFormat('h3'));

const h4Button = document.createElement('button');
h4Button.textContent = 'H4';
h4Button.type = 'button';
h4Button.style.padding = '8px 14px';
h4Button.addEventListener('click', () => applyFormat('h4'));

const h5Button = document.createElement('button');
h5Button.textContent = 'H5';
h5Button.type = 'button';
h5Button.style.padding = '8px 14px';
h5Button.addEventListener('click', () => applyFormat('h5'));

const pButton = document.createElement('button');
pButton.textContent = 'P';
pButton.type = 'button';
pButton.style.padding = '8px 14px';
pButton.addEventListener('click', () => applyFormat('p'));

// 툴바에 버튼 추가
const toolbar = document.getElementById('toolbar');
toolbar.appendChild(h2Button);
toolbar.appendChild(h3Button);
toolbar.appendChild(h4Button);
toolbar.appendChild(h5Button);
toolbar.appendChild(pButton);
// 버튼 클릭 시 선택된 텍스트의 태그를 변경하는 함수
function applyFormat(tag) {
    currentTag = tag;
    const selection = window.getSelection();
    if (!selection.rangeCount) return;

    const range = selection.getRangeAt(0);
    const postContent = document.getElementById('post-content');

    if (!postContent.contains(range.commonAncestorContainer)) return;

    // 선택된 내용 삭제 후 새로운 태그로 감싸기
    const selectedContent = range.extractContents();
    const newElement = document.createElement(tag);

    // p 스타일 적용
    if (tag === 'p') {
        newElement.style.fontSize = '11pt';
        newElement.style.fontWeight = '300';
        newElement.style.lineHeight = '22pt';
        newElement.style.color = 'rgb(90, 90, 90)';
        newElement.style.letterSpacing = '0.8px'; // letter-spacing 추가
    }



    newElement.appendChild(selectedContent);
    range.deleteContents(); // 기존 내용 삭제
    range.insertNode(newElement); // 새로운 요소 삽입

    // 선택 영역 유지하기 위해 범위 재설정
    selection.removeAllRanges();
    const newRange = document.createRange();
    newRange.selectNodeContents(newElement);
    selection.addRange(newRange);

    highlightActiveButton(tag); // 활성화된 버튼 업데이트
}


// 버튼 활성화 표시 함수
function highlightActiveButton(tag) {
    const buttons = [h2Button, h3Button, h4Button, h5Button, pButton];
    buttons.forEach(button => {
        button.style.backgroundColor = ''; // 기본 배경색으로 초기화
        button.style.color = ''; // 기본 글자 색상으로 초기화
    });

    // 선택된 버튼에 활성화 스타일 적용
    const activeButton = buttons.find(button => button.textContent.toLowerCase() === tag);
    if (activeButton) {
        activeButton.style.backgroundColor = '#007bff'; // 활성화된 버튼 배경색
        activeButton.style.color = '#fff'; // 활성화된 버튼 글자 색상
    }
}




// html 코드로 전환하여 보기
let isHtmlView = false; // 현재 뷰 상태를 추적하는 변수

function toggleHtmlView() {
    const postContent = document.getElementById('post-content'); // 내용 영역
    const button = document.getElementById('toggle-html-button'); // 버튼

    if (!isHtmlView) {
        // 현재 뷰가 일반 텍스트인 경우
        const htmlContent = postContent.innerHTML; // HTML 내용 가져오기
        postContent.outerHTML = `<textarea id="post-content" style="border: none; padding: 10px; min-height: 200px; width: 100%;">${htmlContent}</textarea>`;
        button.textContent = '일반 보기'; // 버튼 텍스트 변경
    } else {
        // 현재 뷰가 HTML인 경우
        const textarea = document.getElementById('post-content');
        const newContent = textarea.value; // 텍스트 에리어의 값을 가져오기
        postContent.outerHTML = `<div id="post-content" contentEditable="true" style="border: none; padding: 10px; min-height: 200px; position: relative;">${newContent}</div>`;
        button.textContent = 'HTML 코드 보기'; // 버튼 텍스트 변경
    }

    isHtmlView = !isHtmlView; // 뷰 상태 전환
}



// 텍스트 색상 변경 함수
function changeTextColor() {
    const selectedColor = document.getElementById('textColor').value;
    const selection = window.getSelection();

    if (selection.rangeCount > 0) {
        const range = selection.getRangeAt(0);
        const selectedText = selection.toString();

        if (selectedText.length > 0) {
            // 새로운 span 요소 생성
            const span = document.createElement('span');
            span.style.color = selectedColor; // 텍스트 색상 설정
            span.textContent = selectedText; // 선택된 텍스트 삽입

            // 선택된 영역을 감쌈
            range.deleteContents(); // 기존 내용 삭제
            range.insertNode(span); // 새로운 span 삽입

            // 선택 해제
            selection.removeAllRanges();
            selection.addRange(range);
        }
    }
}

// 배경색 변경 함수
function changeBackgroundColor() {
    const selectedBgColor = document.getElementById('bgColor').value;
    const selection = window.getSelection();

    if (selection.rangeCount > 0) {
        const range = selection.getRangeAt(0);
        const selectedText = selection.toString();

        if (selectedText.length > 0) {
            // 새로운 span 요소 생성
            const span = document.createElement('span');
            span.style.backgroundColor = selectedBgColor; // 배경색 설정
            span.textContent = selectedText; // 선택된 텍스트 삽입

            // 선택된 영역을 감쌈
            range.deleteContents(); // 기존 내용 삭제
            range.insertNode(span); // 새로운 span 삽입

            // 선택 해제
            selection.removeAllRanges();
            selection.addRange(range);
        }
    }
}

// 색상 선택기 이벤트 리스너 추가
document.getElementById('textColor').addEventListener('input', changeTextColor);
document.getElementById('bgColor').addEventListener('input', changeBackgroundColor);
// 선택된 텍스트 정렬 함수
function alignText(alignment) {
    const selection = window.getSelection();

    // post-content 영역 내에서만 작동하도록 체크
    const postContent = document.getElementById('post-content');

    if (selection.rangeCount > 0) {
        const range = selection.getRangeAt(0);
        const selectedText = selection.toString();

        // 선택된 텍스트가 post-content 내에 있는지 확인
        if (postContent.contains(range.startContainer) && selectedText.length > 0) {
            // 기존의 span이나 div가 있는 경우 해당 영역을 감쌈
            const parentElement = range.startContainer.parentElement;

            // 부모 요소가 div라면, 스타일을 변경
            if (parentElement.tagName.toLowerCase() === 'div') {
                parentElement.style.textAlign = alignment; // 정렬 설정
            } else {
                // 새로운 div 요소 생성
                const wrapper = document.createElement('div');
                wrapper.style.textAlign = alignment; // 정렬 설정
                wrapper.style.display = 'block'; // 블록 요소처럼 작동하도록 설정

                // 선택된 텍스트를 span으로 감싸기
                const span = document.createElement('span');
                span.textContent = selectedText; // 선택된 텍스트 삽입

                // 줄바꿈을 유지하기 위해 span을 사용
                span.style.display = 'block'; // 각 줄을 블록처럼 표시
                wrapper.appendChild(span);

                // 선택된 영역을 감쌈
                range.deleteContents(); // 기존 내용 삭제
                range.insertNode(wrapper); // 새로운 wrapper 삽입
            }

            // 선택 해제
            selection.removeAllRanges();
            selection.addRange(range);
        }
    }
}

// 이벤트 리스너 추가
document.getElementById('alignLeft').addEventListener('click', () => alignText('left'));
document.getElementById('alignCenter').addEventListener('click', () => alignText('center'));
document.getElementById('alignRight').addEventListener('click', () => alignText('right'));







let linkActive = false; // 링크 추가 상태를 추적하는 변수

// 링크 추가 및 제거 함수
function toggleLink() {
    const urlInput = document.getElementById('urlInput');
    const selectedText = window.getSelection().toString();

    if (selectedText.length > 0) {
        if (!linkActive) {
            // 링크 추가 모드
            urlInput.style.display = 'inline'; // 입력창 보이기
            urlInput.focus(); // 입력창 포커스

            urlInput.onkeypress = function(event) {
                if (event.key === 'Enter') {
                    const url = urlInput.value;

                    // 선택된 텍스트에 링크 추가
                    const selection = window.getSelection();
                    const range = selection.getRangeAt(0);
                    const linkElement = document.createElement('a');
                    linkElement.href = url;
                    linkElement.target = '_blank'; // 새 탭에서 열리도록 설정
                    linkElement.textContent = selectedText; // 링크 텍스트 설정

                    // 선택된 영역을 감쌈
                    range.deleteContents(); // 기존 내용 삭제
                    range.insertNode(linkElement); // 새로운 링크 삽입

                    // 선택 해제
                    selection.removeAllRanges();
                    selection.addRange(range);

                    // 링크 입력 상태 변경
                    linkActive = true;
                    urlInput.value = ''; // 입력 필드 초기화
                    urlInput.style.display = 'none'; // 입력창 숨기기
                }
            };
        } else {
            // 링크 제거 모드
            const selection = window.getSelection();
            if (selection.rangeCount > 0) {
                const range = selection.getRangeAt(0);
                const selectedNode = range.startContainer;

                // 선택된 영역이 링크인지 확인
                if (selectedNode.nodeType === Node.ELEMENT_NODE && selectedNode.tagName.toLowerCase() === 'a') {
                    const parent = selectedNode.parentNode;
                    const textNode = document.createTextNode(selectedNode.textContent); // 링크의 텍스트를 저장

                    parent.replaceChild(textNode, selectedNode); // 링크를 텍스트로 교체
                }
            }

            // 링크 입력 상태 변경
            linkActive = false;
            urlInput.style.display = 'none'; // 입력창 숨기기
        }
    }
}

// 링크 버튼 클릭 이벤트 리스너 추가
document.getElementById('linkButton').addEventListener('click', toggleLink);

