<?php
// 데이터베이스 연결 설정
$host = 'localhost';
$db = 'chat';
$user = 'root'; // 데이터베이스 사용자
$pass = ''; // 데이터베이스 비밀번호

$conn = new mysqli($host, $user, $pass, $db);

if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}

$data = json_decode(file_get_contents('php://input'), true);
$message = $conn->real_escape_string($data['message']);
$sql = "INSERT INTO messages (content) VALUES ('$message')";

if ($conn->query($sql) === TRUE) {
    echo json_encode(['status' => 'success']);
} else {
    echo json_encode(['status' => 'error', 'message' => $conn->error]);
}

$conn->close();
?>
