document.getElementById('toggle-chat').addEventListener('click', function() {
    const chatWindow = document.getElementById('chat-window');
    chatWindow.style.display = chatWindow.style.display === 'none' ? 'flex' : 'none';
});

document.getElementById('send-btn').addEventListener('click', function() {
    const messageInput = document.getElementById('message');
    const messageText = messageInput.value.trim();

    if (messageText) {
        // 서버에 메시지 전송
        fetch('sendMessage.php', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ message: messageText }),
        })
        .then(response => response.json())
        .then(data => {
            // 메시지 전송 후 입력 필드 비우기
            messageInput.value = '';

            // 메시지 목록 업데이트
            loadMessages();
        });
    }
});

// 메시지 로드 함수
function loadMessages() {
    fetch('loadMessages.php')
    .then(response => response.json())
    .then(data => {
        const chatMessages = document.getElementById('chat-messages');
        chatMessages.innerHTML = ''; // 이전 메시지 초기화

        data.forEach(message => {
            const messageElement = document.createElement('div');
            messageElement.textContent = message;
            chatMessages.appendChild(messageElement);
        });
    });
}

// 주기적으로 메시지 로드
setInterval(loadMessages, 3000); // 3초마다 메시지 로드
