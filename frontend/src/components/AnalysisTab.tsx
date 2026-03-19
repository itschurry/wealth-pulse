import { useMemo } from 'react';
import type { AnalysisData } from '../types';

interface Props {
  data: AnalysisData;
  status: 'loading' | 'ok' | 'error';
  onRefresh: () => void;
}

export function AnalysisTab({ data, status, onRefresh }: Props) {
  const report = useMemo(() => {
    if (!data.analysis_html || typeof window === 'undefined') {
      return { html: data.analysis_html || '', outline: [] as Array<{ id: string; title: string; level: 2 | 3 }>, readMinutes: 0 };
    }

    const parser = new DOMParser();
    const doc = parser.parseFromString(data.analysis_html, 'text/html');
    const outline: Array<{ id: string; title: string; level: 2 | 3 }> = [];

    doc.body.querySelectorAll('h2, h3').forEach((node, index) => {
      const level = node.tagName === 'H2' ? 2 : 3;
      const id = `report-section-${index + 1}`;
      node.id = id;
      outline.push({
        id,
        title: node.textContent?.trim() || `섹션 ${index + 1}`,
        level,
      });
    });

    const text = (doc.body.textContent || '').replace(/\s+/g, ' ').trim();
    const readMinutes = text ? Math.max(1, Math.round(text.split(' ').length / 240)) : 0;

    return {
      html: doc.body.innerHTML,
      outline,
      readMinutes,
    };
  }, [data.analysis_html]);

  const summaryLines = data.summary_lines?.slice(0, 3) || [];

  return (
    <div className="report-shell">
      <div className="report-masthead page-section">
        <div>
          <div className="report-kicker">Today Report</div>
          <div className="report-title">읽는 흐름에 맞춘 오늘 리포트</div>
          <div className="report-description">
            카드식 정보 과밀도를 줄이고, 요약에서 본문으로 자연스럽게 이어지도록 문서형 레이아웃으로 정리했습니다.
          </div>
        </div>
        <div className="report-stat-grid">
          <div className="report-stat-card">
            <div className="report-stat-label">상태</div>
            <div className={`report-stat-value ${status === 'error' ? 'is-down' : status === 'loading' ? 'is-accent' : 'is-up'}`}>
              {status === 'loading' ? '로딩 중' : status === 'error' ? '불러오기 실패' : '준비 완료'}
            </div>
            <div className="report-stat-note">{data.generated_at || '생성 시각 없음'}</div>
          </div>
          <div className="report-stat-card">
            <div className="report-stat-label">예상 읽기</div>
            <div className="report-stat-value">{report.readMinutes ? `${report.readMinutes}분` : '대기'}</div>
            <div className="report-stat-note">요약 포함 기준</div>
          </div>
          <div className="report-stat-card">
            <div className="report-stat-label">섹션 수</div>
            <div className="report-stat-value">{report.outline.filter((item) => item.level === 2).length || '—'}</div>
            <div className="report-stat-note">본문 주요 구간</div>
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
        <div className="report-layout">
          <aside className="report-rail">
            <div className="report-rail-card">
              <div className="report-rail-label">Opening Brief</div>
              <div className="report-rail-title">세 줄로 먼저 읽기</div>
              <div className="report-brief-list">
                {(summaryLines.length > 0 ? summaryLines : ['핵심 요약을 준비 중입니다.']).map((line, index) => (
                  <div key={index} className="report-brief-item">
                    <span className="report-brief-index">{index + 1}</span>
                    <span>{line}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="report-rail-card">
              <div className="report-rail-label">Contents</div>
              <div className="report-rail-title">본문 이동</div>
              <nav className="report-outline">
                {report.outline.length === 0 ? (
                  <div className="report-outline-empty">목차를 만드는 중입니다.</div>
                ) : report.outline.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`report-outline-link ${item.level === 3 ? 'is-sub' : ''}`}
                    onClick={() => document.getElementById(item.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                  >
                    {item.title}
                  </button>
                ))}
              </nav>
            </div>

            <div className="report-rail-card subtle">
              <div className="report-rail-label">Reading Notes</div>
              <div className="report-note-line">생성 시각 {data.generated_at || '확인 중'}</div>
              <div className="report-note-line">권장 흐름 요약 → 본문 → 액션 보드</div>
              <div className="report-note-line">실시간 탭은 보조 확인용입니다.</div>
            </div>
          </aside>

          <article className="page-section report-article">
            <div
              className="analysis-content"
              dangerouslySetInnerHTML={{ __html: report.html }}
            />
          </article>
        </div>
      )}

      {status === 'ok' && !data.analysis_html && (
        <div className="page-section" style={{ textAlign: 'center', padding: '56px 24px' }}>
          <div style={{ fontSize: 34, marginBottom: 10 }}>🤖</div>
          <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-2)' }}>분석 데이터가 없습니다</div>
        </div>
      )}

      <div className="page-section report-disclaimer">
        <div style={{ fontSize: 11, color: 'var(--text-4)', lineHeight: 1.7 }}>
          본 분석은 AI가 자동 생성한 참고 자료이며 투자 자문이 아닙니다. 최종 투자 판단과 손익의 책임은 투자자 본인에게 있습니다.
        </div>
      </div>
    </div>
  );
}
