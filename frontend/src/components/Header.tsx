export function Header({ reportDate }: { reportDate: string }) {
  return (
    <div style={{
      background: 'linear-gradient(135deg, #0D1B35 0%, #162040 50%, #0D1B35 100%)',
      borderBottom: '1px solid rgba(255,255,255,.08)',
      padding: '28px 24px 24px',
      textAlign: 'center',
      position: 'relative',
      overflow: 'hidden',
    }}>
      <div style={{
        fontSize: 11, fontWeight: 800, letterSpacing: '0.12em',
        textTransform: 'uppercase', color: 'rgba(255,255,255,.4)', marginBottom: 6
      }}>
        Daily Investment Assistant
      </div>
      <div style={{ fontSize: 28, fontWeight: 800, color: '#f0f4ff', marginBottom: 6 }}>
        🧭 투자 도우미
      </div>
      <div style={{ fontSize: 16, color: 'rgba(255,255,255,.6)' }}>{reportDate} · 오늘의 판단을 정리하세요</div>
    </div>
  );
}
