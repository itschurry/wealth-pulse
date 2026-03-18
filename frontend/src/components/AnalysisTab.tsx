import type { AnalysisData } from '../types';

interface Props {
  data: AnalysisData;
  status: 'loading' | 'ok' | 'error';
  onRefresh: () => void;
}

export function AnalysisTab({ data, status, onRefresh }: Props) {
  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {status === 'loading' && (
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              border: '2px solid #3b82f6', borderTopColor: 'transparent',
              display: 'inline-block', animation: 'spin .8s linear infinite',
            }} />
          )}
          {status === 'ok' && <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--up)', boxShadow: '0 0 6px var(--up)', display: 'inline-block' }} />}
          {status === 'error' && <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--down)', display: 'inline-block' }} />}
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
            {status === 'loading' ? '분석 로딩 중...'
              : status === 'error' ? '분석 불러오기 실패'
              : data.generated_at ? `생성: ${new Date(data.generated_at).toLocaleString('ko-KR')}`
              : 'AI 분석'}
          </span>
        </div>
        <button onClick={onRefresh} style={{
          background: 'rgba(59,130,246,.12)', border: '1px solid rgba(59,130,246,.3)',
          borderRadius: 8, color: '#93c5fd', cursor: 'pointer', fontSize: 16, padding: '4px 10px',
        }} title="새로고침">↻</button>
      </div>

      {/* Loading skeleton */}
      {status === 'loading' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[80, 60, 90, 40, 70].map((w, i) => (
            <div key={i} className="shimmer-line" style={{
              height: 16, borderRadius: 8,
              background: 'var(--surface-alt)',
              width: `${w}%`,
            }} />
          ))}
        </div>
      )}

      {/* Error state */}
      {status === 'error' && (
        <div style={{
          textAlign: 'center', padding: '40px 20px',
          background: 'var(--card-bg)', borderRadius: 16,
          border: '1px solid var(--down-border)',
        }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>⚠️</div>
          <div style={{ color: 'var(--down)', fontWeight: 600, marginBottom: 4 }}>분석을 불러올 수 없습니다</div>
          <div style={{ fontSize: 13, color: 'var(--text-4)' }}>{data.error || '잠시 후 다시 시도해 주세요'}</div>
        </div>
      )}

      {/* Analysis content */}
      {status === 'ok' && data.analysis_html && (
        <div
          style={{
            background: 'var(--card-bg)',
            border: '1px solid var(--border)',
            borderRadius: 16,
            padding: '20px 24px',
          }}
          className="analysis-content"
          dangerouslySetInnerHTML={{ __html: data.analysis_html }}
        />
      )}

      {status === 'ok' && !data.analysis_html && (
        <div style={{
          textAlign: 'center', padding: '60px 20px',
          background: 'var(--card-bg)', borderRadius: 16, border: '1px solid var(--border)',
        }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>🤖</div>
          <div style={{ color: 'var(--text-2)', fontWeight: 600 }}>분석 데이터가 없습니다</div>
        </div>
      )}

      {/* Disclaimer */}
      <div style={{
        marginTop: 16, padding: '12px 16px',
        background: 'rgba(255,255,255,.03)', borderRadius: 10,
        border: '1px solid var(--border-light)',
        fontSize: 11, color: 'var(--text-4)', lineHeight: 1.6,
      }}>
        ⚠️ 본 분석은 AI가 자동 생성한 참고 자료이며, 투자 조언이 아닙니다. 투자 결정은 본인의 판단과 책임 하에 이루어져야 합니다.
      </div>
    </div>
  );
}
