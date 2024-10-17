<?php
// 요청이 POST일 경우
if ($_SERVER["REQUEST_METHOD"] == "POST") {
    // 폼 데이터 가져오기
    $company = $_POST['company'];
    $email = $_POST['email'];
    $phone = $_POST['phone'];
    $source = $_POST['source'];
    $topic = $_POST['topic'];
    $message = $_POST['message'];

    // 데이터 배열 생성
    $data = [
        'company' => $company,
        'email' => $email,
        'phone' => $phone,
        'source' => $source,
        'topic' => $topic,
        'message' => $message,
    ];

    // 기존 데이터 가져오기
    $filePath = 'contacts.json';
    if (file_exists($filePath)) {
        $jsonData = file_get_contents($filePath);
        $contacts = json_decode($jsonData, true);
    } else {
        $contacts = [];
    }

    // 새로운 데이터 추가
    $contacts[] = $data;

    // JSON으로 저장
    file_put_contents($filePath, json_encode($contacts, JSON_PRETTY_PRINT));

    // 리다이렉트
    header("Location: admin_contact.html");
    exit;
}
?>
