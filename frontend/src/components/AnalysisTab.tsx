import type { AnalysisData } from '../types';

interface Props {
  data: AnalysisData;
  status: 'loading' | 'ok' | 'error';
  onRefresh: () => void;
}

export function AnalysisTab({ data, status, onRefresh }: Props) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div className="page-section" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 20 }}>
        <div>
          <div style={{ fontSize: 12, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-4)' }}>Today Report</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--text-1)', marginTop: 8 }}>오늘 리포트</div>
          <div style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.7, marginTop: 10, maxWidth: 760 }}>
            생성된 분석 본문을 읽으면서 오늘 시장의 구조, 리스크, 주목 섹터를 차분하게 확인하는 영역입니다.
          </div>
        </div>

        <div style={{ minWidth: 220, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ padding: '14px 16px', borderRadius: 18, background: 'var(--surface-alt)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>상태</div>
            <div style={{ fontSize: 18, fontWeight: 800, color: status === 'error' ? 'var(--down)' : status === 'loading' ? 'var(--accent)' : 'var(--up)', marginTop: 8 }}>
              {status === 'loading' ? '로딩 중' : status === 'error' ? '불러오기 실패' : '준비 완료'}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 6 }}>{data.generated_at || '생성 시각 없음'}</div>
          </div>
          <button className="ghost-button" onClick={onRefresh}>본문 새로고침</button>
        </div>
      </div>

      {status === 'loading' && (
        <div className="page-section" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[92, 76, 84, 55, 68, 88].map((w, i) => (
            <div
              key={i}
              className="shimmer-line"
              style={{ height: 16, borderRadius: 999, background: 'var(--surface-alt)', width: `${w}%` }}
            />
          ))}
        </div>
      )}

      {status === 'error' && (
        <div className="page-section" style={{ textAlign: 'center', padding: '48px 24px' }}>
          <div style={{ fontSize: 34, marginBottom: 10 }}>⚠️</div>
          <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--down)' }}>분석을 불러올 수 없습니다</div>
          <div style={{ fontSize: 13, color: 'var(--text-4)', marginTop: 8 }}>{data.error || '잠시 후 다시 시도해 주세요.'}</div>
        </div>
      )}

      {status === 'ok' && data.analysis_html && (
        <div className="page-section">
          <div
            className="analysis-content"
            dangerouslySetInnerHTML={{ __html: data.analysis_html }}
          />
        </div>
      )}

      {status === 'ok' && !data.analysis_html && (
        <div className="page-section" style={{ textAlign: 'center', padding: '56px 24px' }}>
          <div style={{ fontSize: 34, marginBottom: 10 }}>🤖</div>
          <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-2)' }}>분석 데이터가 없습니다</div>
        </div>
      )}

      <div className="page-section" style={{ padding: '16px 18px', background: 'rgba(255,253,248,0.72)' }}>
        <div style={{ fontSize: 11, color: 'var(--text-4)', lineHeight: 1.7 }}>
          본 분석은 AI가 자동 생성한 참고 자료이며 투자 자문이 아닙니다. 최종 투자 판단과 손익의 책임은 투자자 본인에게 있습니다.
        </div>
      </div>
    </div>
  );
}
