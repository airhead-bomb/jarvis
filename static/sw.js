// 지금은 오프라인 캐싱 없이, PWA 설치 요건만 만족시키는 최소한의 서비스워커
self.addEventListener("install", (e) => {
  self.skipWaiting();
});

self.addEventListener("fetch", (e) => {
  // 그냥 네트워크로 통과시킴 (나중에 오프라인 캐싱 추가 가능)
});
