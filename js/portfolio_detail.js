// 포트폴리오 데이터 배열
const portfolioItems = [
    { url: "01.html", img: "../img/logo/logo1.jpg", title: "NC소프트", desc: "홈페이지 사용자 행동 데이터 시각화" },
    { url: "02.html", img: "../img/logo/logo2.jpg", title: "정관장", desc: "GA4 최적화, 전자상거래 데이터 수집(상세)" },
    { url: "03.html", img: "../img/logo/logo3.jpg", title: "LG전자(폴리메이트)", desc: "GA4 최적화, 홈페이지 사용자 행동 데이터 시각화" },
    { url: "05.html", img: "../img/logo/logo5.jpg", title: "프롬바이오", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "06.html", img: "../img/logo/logo6.jpg", title: "굿네이버스", desc: "홈페이지 사용자 행동 데이터 수집" },
    { url: "07.html", img: "../img/logo/logo7.jpg", title: "지구랭", desc: "사용자 행동 데이터 수집, GA4/GTM 출장 강의" },
    { url: "08.html", img: "../img/logo/logo8.jpg", title: "스팀베이스", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "09.html", img: "../img/logo/logo9.jpg", title: "에이블런", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "10.html", img: "../img/logo/logo10.jpg", title: "한국직업평가진흥협회", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "11.html", img: "../img/logo/logo11.jpg", title: "아이몰", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "12.html", img: "../img/logo/logo12.jpg", title: "ICBANQ", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "13.html", img: "../img/logo/logo13.jpg", title: "영프랜드", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "14.html", img: "../img/logo/logo14.jpg", title: "튜나", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "15.html", img: "../img/logo/logo15.jpg", title: "센스톤", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "16.html", img: "../img/logo/logo16.jpg", title: "누깍", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "17.html", img: "../img/logo/logo17.jpg", title: "윤식단", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "18.html", img: "../img/logo/logo18.jpg", title: "어트랙션", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "19.html", img: "../img/logo/logo19.jpg", title: "도반한방병원", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "20.html", img: "../img/logo/logo20.jpg", title: "모두티켓", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "21.html", img: "../img/logo/logo21.jpg", title: "소리의원", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "22.html", img: "../img/logo/logo22.jpg", title: "사인트리", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "23.html", img: "../img/logo/logo23.jpg", title: "비트베스트", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "24.html", img: "../img/logo/logo24.jpg", title: "LNC", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "25.html", img: "../img/logo/logo25.jpg", title: "CANADA GOOSE", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "26.html", img: "../img/logo/logo26.jpg", title: "RUMTTON", desc: "GA4 최적화, 전자상거래 데이터 수집(기본)" },
    { url: "27.html", img: "../img/logo/logo27.jpg", title: "DESSERTCO", desc: "GA4 최적화,PHP 웹 전자상거래 데이터 수집" },
    { url: "28.html", img: "../img/logo/logo28.jpg", title: "BAROWEB", desc: "GA4 최적화,PHP 웹 전자상거래 데이터 수집" },
    { url: "29.html", img: "../img/logo/logo29.jpg", title: "VPK", desc: "GA4 최적화,PHP 웹 전자상거래 데이터 수집" },
    { url: "30.html", img: "../img/logo/logo30.jpg", title: "SAMSUNG", desc: "삼성글로벌네트웍스 홈페이지 데이터 수집 최적화" },
    { url: "31.html", img: "../img/logo/logo31.jpg", title: "숲스토리", desc: "GA4, GTM 설정, 홈페이지 사용자 행동 데이터 수집" },
    { url: "32.html", img: "../img/logo/logo32.jpg", title: "엔아이텍", desc: "니콘공식산업대리점 엔아이텍 홈페이지 데이터 수집" },
    { url: "33.html", img: "../img/logo/logo33.jpg", title: "오상자이엘", desc: "GA4, GTM 설정, 홈페이지 사용자 행동 데이터 수집" },
    { url: "34.html", img: "../img/logo/logo34.jpg", title: "택산이엔지", desc: "GA4, GTM 설정, 홈페이지 사용자 행동 데이터 수집" },
    { url: "35.html", img: "../img/logo/logo35.jpg", title: "한솔요리학원", desc: "GA4, GTM 설정, 홈페이지 사용자 행동 데이터 수집" }
]
;


// 랜덤으로 4개의 아이템 선택
function getRandomItems(arr, count) {
    const shuffled = arr.sort(() => 0.5 - Math.random());
    return shuffled.slice(0, count);
}

// 추천 포트폴리오 렌더링
function renderRecommendedPortfolio() {
    const randomItems = getRandomItems(portfolioItems, 4);
    const container = document.getElementById("random-portfolio-items");

    randomItems.forEach(item => {
        const portfolioItem = document.createElement("div");
        portfolioItem.classList.add("portfolio-item");

        portfolioItem.innerHTML = `
            <a href="${item.url}">
                <img src="${item.img}" alt="${item.title}">
                <h3>${item.title}</h3>
                <p>${item.desc}</p>
            </a>
        `;

        container.appendChild(portfolioItem);
    });
}

// 실행
document.addEventListener("DOMContentLoaded", renderRecommendedPortfolio);