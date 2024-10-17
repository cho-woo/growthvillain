<?php
// CORS 허용 헤더
header("Access-Control-Allow-Origin: *");
header("Access-Control-Allow-Methods: POST");
header("Access-Control-Allow-Headers: Content-Type");
header("Content-Type: application/json");

// JSON 파일 읽기
$json_data = file_get_contents('contacts.json');
echo $json_data;

// 요청이 POST일 경우
if ($_SERVER["REQUEST_METHOD"] == "POST") {
    // 폼 데이터 가져오기
    $company = trim($_POST['company']);
    $email = filter_var(trim($_POST['email']), FILTER_SANITIZE_EMAIL);
    $phone = trim($_POST['phone']);
    $source = trim($_POST['source']);
    $topic = trim($_POST['topic']);
    $message = trim($_POST['message']);

    // 현재 시간 가져오기 (Korean Time)
    date_default_timezone_set('Asia/Seoul');
    $timestamp = date('Y-m-d H:i:s');

    // 간단한 유효성 검사
    if (empty($company) || empty($email) || empty($message)) {
        http_response_code(400);
        echo json_encode(["message" => "필수 입력란이 비어 있습니다."]);
        exit;
    }

    // 데이터 배열 생성
    $data = [
        'company' => $company,
        'email' => $email,
        'phone' => $phone,
        'source' => $source,
        'topic' => $topic,
        'message' => $message,
        'timestamp' => $timestamp, // 추가된 문의 시간
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
    if (file_put_contents($filePath, json_encode($contacts, JSON_PRETTY_PRINT)) === false) {
        http_response_code(500);
        echo json_encode(["message" => "데이터 저장 중 오류가 발생했습니다."]);
        exit;
    }

    // 성공 응답
    echo json_encode(["message" => "문의가 성공적으로 전송되었습니다."]);
    exit;
}

?>
