import { bootstrap } from "./app/bootstrap";
import "./styles/tokens.css";
import "./styles/global.css";

// 진입점은 부트스트랩 호출만 둔다. 모의 API 시작·실패 배너 분기는 app/bootstrap.ts에 있다.
const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("#root 요소가 없습니다");
}

// 부트스트랩 자체가 실패하면(렌더 실패 등) 빈 화면 대신 짧은 안내를 보인다.
bootstrap(rootElement).catch(() => {
  rootElement.textContent = "화면을 불러오지 못했습니다. 새로 고침해 주세요.";
});
