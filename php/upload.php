<?php
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, GET, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    exit; // OPTIONS 요청에 대한 응답
}

error_reporting(E_ALL);
ini_set('display_errors', 1);

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $targetDir = 'img/'; // 이미지 저장할 디렉토리
    if (!is_dir($targetDir)) {
        mkdir($targetDir, 0777, true); // 디렉토리가 없으면 생성
    }

    $originalFileName = basename($_FILES['file']['name']);
    $fileExtension = strtolower(pathinfo($originalFileName, PATHINFO_EXTENSION));
    $fileNameWithoutExt = pathinfo($originalFileName, PATHINFO_FILENAME);
    
    // 파일명이 중복되는 경우 처리
    $targetFile = $targetDir . $originalFileName;
    $counter = 1;
    while (file_exists($targetFile)) {
        $newFileName = $fileNameWithoutExt . " ($counter)." . $fileExtension; // 새로운 파일명 생성
        $targetFile = $targetDir . $newFileName; // 새로운 경로 설정
        $counter++;
    }

    $uploadOk = 1;

    $check = getimagesize($_FILES['file']['tmp_name']);
    if ($check === false) {
        echo json_encode(['error' => '파일이 이미지가 아닙니다.']);
        exit;
    }

    if ($_FILES['file']['size'] > 5000000) {
        echo json_encode(['error' => '파일 크기가 너무 큽니다.']);
        exit;
    }

    $allowedTypes = ['jpg', 'jpeg', 'png', 'gif'];
    if (!in_array($fileExtension, $allowedTypes)) {
        echo json_encode(['error' => '허용되지 않는 파일 형식입니다.']);
        exit;
    }

    if (move_uploaded_file($_FILES['file']['tmp_name'], $targetFile)) {
        // 절대 URL 생성
        $absoluteUrl = 'http://' . $_SERVER['HTTP_HOST'] . '/' . $targetFile;
        echo json_encode(['url' => $absoluteUrl]);
    } else {
        echo json_encode(['error' => '파일 업로드에 실패했습니다.']);
    }
} else {
    echo json_encode(['error' => '잘못된 요청입니다.']);
}
