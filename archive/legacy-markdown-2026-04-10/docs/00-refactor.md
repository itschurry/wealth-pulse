📦 WealthPulse — Execution Engine 도입 작업지시서
🎯 목적

현재 WealthPulse는 전략/분석 중심 구조이며 실제 주문 실행 흐름이 없음.
이를 해결하기 위해 Execution Engine 기반 주문 파이프라인을 도입한다.

1️⃣ 전체 구조 개편
🔥 목표 아키텍처
[Strategy Engine]
    ↓
[Signal Engine]
    ↓
[Execution Engine]   ← 신규 추가 (핵심)
    ↓
[Risk Engine]
    ↓
[Order Engine]
    ↓
[Broker]
2️⃣ 신규 컴포넌트 정의
2.1 Execution Engine (핵심)
📂 위치
services/execution_engine.py
🎯 역할
signal → 주문 여부 결정
포지션 사이징
최종 order 생성
🧠 인터페이스
class ExecutionEngine:
    def __init__(self, risk_engine, portfolio):
        self.risk_engine = risk_engine
        self.portfolio = portfolio

    def decide(self, signal):
        # 1. signal 필터링
        if signal.score < signal.threshold:
            return None

        # 2. 리스크 체크
        risk = self.risk_engine.evaluate(signal)
        if risk.blocked:
            return None

        # 3. 포지션 사이즈 계산
        size = self._calc_size(signal)

        return {
            "symbol": signal.symbol,
            "side": signal.side,
            "size": size,
            "price": signal.price,
        }

    def _calc_size(self, signal):
        capital = self.portfolio.available_cash
        return capital * 0.02  # 기본 2% 룰 (추후 확장)
2.2 Signal Engine (분리 필요)
📂 위치
apps/api/services/live_signal_engine.py
🎯 역할
runtime 전략 결과 → 실시간 signal 생성
class SignalEngine:
    def generate(self, market_data, strategy):
        return Signal(
            symbol=market_data.symbol,
            score=strategy.score(market_data),
            side=strategy.side,
            price=market_data.price,
        )
2.3 Order Engine
📂 위치
services/order_engine.py
🎯 역할
execution 결과 → broker 전달
class OrderEngine:
    def __init__(self, broker):
        self.broker = broker

    def execute(self, order):
        return self.broker.send_order(order)
3️⃣ 상태 모델 강제 정의 (중요)
🎯 상태 흐름
SCANNED
→ SIGNAL_GENERATED
→ EXECUTION_DECIDED
→ ORDER_CREATED
→ ORDER_SENT
→ FILLED / REJECTED
📂 모델 정의
models/trade_state.py
from enum import Enum

class TradeState(Enum):
    SCANNED = "scanned"
    SIGNAL = "signal_generated"
    DECIDED = "execution_decided"
    ORDER_CREATED = "order_created"
    SENT = "order_sent"
    FILLED = "filled"
    REJECTED = "rejected"
4️⃣ 기존 구조 수정 포인트
❌ 현재 문제
항목	문제
scanner	실행 후보처럼 사용됨
final_action	의미 불명확
runtime	실행 역할까지 떠안음
✅ 수정 방향
1. scanner → 탐색 전용
scanner = discovery only
2. final_action 제거 or 축소
final_action → execution_decision 으로 대체
3. runtime 역할 축소
runtime = 전략 생성/검증 전용
5️⃣ 이벤트 기반 실행 흐름
🎯 핵심 흐름
def trading_loop(market_data):

    signal = signal_engine.generate(market_data, strategy)

    if not signal:
        return

    order = execution_engine.decide(signal)

    if not order:
        return

    result = order_engine.execute(order)

    log(result)
6️⃣ UI 수정 지시
❌ 현재 구조
탐색 / 후보 / 분석 / 반영
→ 흐름이 안 보임
✅ 수정 구조
[탐색] → [신호] → [판단] → [주문]
🎯 화면 구성
탭	내용
탐색	scanner 결과
신호	전략 통과 종목
판단	execution 결과
주문	실제 주문 상태
⚠️ 필수 추가
✅ “자동 주문 ON/OFF 토글”
✅ 주문 전 confirm 옵션
✅ 로그 표시 (order 결과)
7️⃣ Risk Engine 연동 강화
🎯 조건
if portfolio.exposure > 0.3:
    block

if drawdown > 0.1:
    block
8️⃣ Broker 인터페이스 표준화
📂 위치
services/broker/base.py
class Broker:
    def send_order(self, order):
        raise NotImplementedError
9️⃣ 테스트 지시
필수 테스트
 signal → order 생성 여부
 risk block 동작
 중복 주문 방지
 주문 실패 retry
🔟 단계별 적용 순서
1. Execution Engine 구현
2. Signal Engine 분리
3. Order Engine 추가
4. 상태 모델 적용
5. trading loop 연결
6. UI 구조 수정
7. risk/broker 연동
💣 최종 요약 (진짜 중요)

👉 지금 구조
= 분석 시스템

👉 이 작업 후
= 실제 트레이딩 시스템

😏 한마디만 한다

지금까지는 “똑똑한 분석 툴”이었고
이거 넣으면 그때부터 “돈 벌려고 만든 시스템” 되는 거야
