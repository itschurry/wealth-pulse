import { useCallback, useMemo } from 'react';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import type { ConsoleSnapshot } from '../types/consoleView';
import { formatDateTime } from '../utils/format';

interface UniversePageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

export function UniversePage({ snapshot, loading, errorMessage, onRefresh }: UniversePageProps) {
  const { entries, push, clear } = useConsoleLogs();
  const items = snapshot.universe.items || [];

  const statusItems = useMemo(() => ([
    { label: '유니버스 규칙', value: `${items.length}개`, tone: 'neutral' as const },
    { label: '총 종목 수', value: `${items.reduce((sum, item) => sum + Number(item.symbol_count || 0), 0)}개`, tone: 'good' as const },
    { label: '제외 종목', value: `${items.reduce((sum, item) => sum + Number(item.excluded_count || 0), 0)}개`, tone: 'bad' as const },
    { label: '최근 갱신', value: formatDateTime(items[0]?.updated_at), tone: 'neutral' as const },
  ]), [items]);

  const handleRefresh = useCallback(() => {
    onRefresh();
    push('info', '유니버스 스냅샷을 다시 불러왔습니다.', undefined, 'engine');
  }, [onRefresh, push]);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="유니버스"
            subtitle="고정 종목 목록 대신 universe rule 기반 종목군을 보여줍니다. 최근 변경 내역과 주요 제외 사유를 같이 확인할 수 있습니다."
            lastUpdated={snapshot.fetchedAt}
            loading={loading}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={handleRefresh}
            logs={entries}
            onClearLogs={clear}
          />

          {items.map((item) => (
            <section key={`${item.rule_name}:${item.market}`} className="page-section" style={{ display: 'grid', gap: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>{item.rule_name}</div>
                  <div className="signal-cell-copy" style={{ marginTop: 4 }}>{item.market || '-'} · 종목 {item.symbol_count || 0}개 · 제외 {item.excluded_count || 0}개</div>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-3)', textAlign: 'right' }}>
                  <div>생성 {formatDateTime(item.created_at)}</div>
                  <div>갱신 {formatDateTime(item.updated_at)}</div>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-4)', marginBottom: 8 }}>최근 변경</div>
                  <div className="signal-cell-copy">추가 {item.recent_changes?.added_count || 0} · 제외 {item.recent_changes?.removed_count || 0}</div>
                  <div style={{ marginTop: 8, fontSize: 12 }}>{(item.recent_changes?.added || []).slice(0, 8).join(', ') || '추가 없음'}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-4)', marginBottom: 8 }}>포함 종목 예시</div>
                  <div style={{ fontSize: 12 }}>{(item.symbols || []).slice(0, 10).map((symbol) => symbol.code).join(', ') || '데이터 없음'}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-4)', marginBottom: 8 }}>주요 제외 사유</div>
                  <div style={{ fontSize: 12 }}>{(item.excluded || []).slice(0, 6).map((symbol) => `${symbol.code}(${symbol.reason})`).join(', ') || '제외 없음'}</div>
                </div>
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
