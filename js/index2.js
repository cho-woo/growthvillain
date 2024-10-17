// Three.js를 사용하여 지구본 형태로 카드 배치
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
const renderer = new THREE.WebGLRenderer({ antialias: true });

renderer.setSize(window.innerWidth, window.innerHeight);
document.getElementById('canvas-container').appendChild(renderer.domElement);

// 배경 이미지 설정
const backgroundTextureLoader = new THREE.TextureLoader();
const backgroundTexture = backgroundTextureLoader.load("img/20241008_052759.jpg"); // 상대 경로로 수정
scene.background = backgroundTexture;

// 카드 배열 설정
const geometry = new THREE.PlaneGeometry(2, 3); // 카드 크기를 두 배로 변경 (1.5, 2) -> (3, 4)
const cards = [];

// 카드 배경 색상
const cardColor = 0xff0000; // 빨간색

// 20장의 카드 생성
for (let i = 0; i < 25; i++) {
    // 카드 생성 및 빨간색 텍스처 적용
    const material = new THREE.MeshBasicMaterial({ color: cardColor });
    const card = new THREE.Mesh(geometry, material);
    cards.push(card);
    scene.add(card);
}

// 지구본 형태로 카드 배치
const radius = 8;
cards.forEach((card, index) => {
    const phi = Math.acos(-1 + (2 * index) / cards.length);
    const theta = Math.sqrt(cards.length * Math.PI) * phi;

    card.position.set(
        radius * Math.cos(theta) * Math.sin(phi),
        radius * Math.sin(theta) * Math.sin(phi),
        radius * Math.cos(phi)
    );

    // 카드가 다양한 방향을 바라보도록 회전
    card.lookAt(new THREE.Vector3(0, 0, 0));

    // 카드 아래에 텍스트 추가
    const textGeometry = new THREE.TextGeometry('텍스트 테스트', {
        font: new THREE.FontLoader().load('package.json'), // 원하는 폰트 파일 경로
        size: 0.5, // 텍스트 크기
        height: 0.1,
    });

    const textMaterial = new THREE.MeshBasicMaterial({ color: 0xffffff }); // 흰색 텍스처
    const textMesh = new THREE.Mesh(textGeometry, textMaterial);
    
    // 텍스트 위치 조정 (카드 아래로 위치)
    textMesh.position.set(card.position.x, card.position.y - 2.5, card.position.z); // 카드 아래에 위치
    scene.add(textMesh);
});

// 카메라 위치 설정
camera.position.z = 10;

// 조명 추가
const ambientLight = new THREE.AmbientLight(0xffffff, 0.8); // 전체적으로 밝기를 줌
scene.add(ambientLight);

const directionalLight = new THREE.DirectionalLight(0xffffff, 1); // 방향성 있는 빛 추가
directionalLight.position.set(5, 5, 5).normalize();
scene.add(directionalLight);

// 회전 각도와 드래그 관련 설정
let isDragging = false;
let previousMousePosition = { x: 0, y: 0 };
let rotation = { x: 0, y: 0 };

// 마우스 드래그 이벤트 리스너 추가
document.addEventListener('mousedown', function (e) {
    isDragging = true;
});

document.addEventListener('mousemove', function (e) {
    if (!isDragging) return;

    const deltaMove = {
        x: e.offsetX - previousMousePosition.x,
        y: e.offsetY - previousMousePosition.y
    };

    rotation.y += deltaMove.x * 0.01;
    rotation.x += deltaMove.y * 0.01;

    previousMousePosition = {
        x: e.offsetX,
        y: e.offsetY
    };
});

document.addEventListener('mouseup', function () {
    isDragging = false;
});

// 스크롤 확대/축소 기능
document.addEventListener('wheel', (event) => {
    event.preventDefault();
    const zoomFactor = 0.5;
    if (event.deltaY < 0) {
        camera.position.z -= zoomFactor; // 스크롤 업 시 확대
    } else {
        camera.position.z += zoomFactor; // 스크롤 다운 시 축소
    }
});

// 렌더링 및 회전
function animate() {
    requestAnimationFrame(animate);

    // 마우스 드래그로 회전 적용
    scene.rotation.y = rotation.y;
    scene.rotation.x = rotation.x;

    renderer.render(scene, camera);
}

animate();
