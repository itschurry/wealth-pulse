import { useMemo } from 'react';
import type { AnalysisData } from '../types';
import { formatLinkLabel, renderTextWithLinks } from '../utils/linkify';
import { getBiasLabel } from '../utils/quantLabels';

interface Props {
  data: AnalysisData;
  status: 'loading' | 'ok' | 'error';
  onRefresh: () => void;
}

export function AnalysisTab({ data, status, onRefresh }: Props) {
  const playbook = data.analysis_playbook;
  const report = useMemo(() => {
    if (!data.analysis_html || typeof window === 'undefined') {
      return { html: data.analysis_html || '', outline: [] as Array<{ id: string; title: string; level: 2 | 3 }>, readMinutes: 0 };
    }

    const parser = new DOMParser();
    const doc = parser.parseFromString(data.analysis_html, 'text/html');
    const outline: Array<{ id: string; title: string; level: 2 | 3 }> = [];
    const urlPattern = /(https?:\/\/[^\s<>()]+[^\s<>().,;:!?"'])/g;
    const subsectionPattern = /^(\d+)[\.\)]\s*(.+)$/;

    const getSubsectionTitle = (node: Node) => {
      if (node.nodeType !== Node.ELEMENT_NODE) return null;

      const element = node as HTMLElement;
      const rawText = element.textContent?.replace(/\s+/g, ' ').trim() || '';
      if (!rawText) return null;

      if (element.tagName === 'H3') {
        return { title: rawText };
      }

      if (element.tagName === 'P') {
        const match = rawText.match(subsectionPattern);
        if (match) {
          return {
            number: match[1].padStart(2, '0'),
            title: match[2].trim(),
          };
        }
      }

      return null;
    };

    const linkifyTextNodes = (root: ParentNode) => {
      const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      const nodes: Text[] = [];

      let currentNode = walker.nextNode();
      while (currentNode) {
        const textNode = currentNode as Text;
        const parent = textNode.parentElement;
        urlPattern.lastIndex = 0;
        if (parent && !['A', 'SCRIPT', 'STYLE'].includes(parent.tagName) && urlPattern.test(textNode.textContent || '')) {
          nodes.push(textNode);
        }
        currentNode = walker.nextNode();
      }

      nodes.forEach((textNode) => {
        const text = textNode.textContent || '';
        urlPattern.lastIndex = 0;

        const fragment = doc.createDocumentFragment();
        let lastIndex = 0;
        let match = urlPattern.exec(text);

        while (match) {
          const [url] = match;
          const start = match.index;

          if (start > lastIndex) {
            fragment.appendChild(doc.createTextNode(text.slice(lastIndex, start)));
          }

          const anchor = doc.createElement('a');
          anchor.className = 'inline-link';
          anchor.href = url;
          anchor.target = '_blank';
          anchor.rel = 'noreferrer';
          anchor.textContent = formatLinkLabel(url);
          fragment.appendChild(anchor);

          lastIndex = start + url.length;
          match = urlPattern.exec(text);
        }

        if (lastIndex < text.length) {
          fragment.appendChild(doc.createTextNode(text.slice(lastIndex)));
        }

        textNode.parentNode?.replaceChild(fragment, textNode);
      });
    };

    const decorateInlineLabels = (root: ParentNode) => {
      root.querySelectorAll('p > strong:first-child, li > strong:first-child, li > p > strong:first-child').forEach((node) => {
        const strong = node as HTMLElement;
        if ((strong.textContent || '').trim().endsWith(':')) {
          strong.classList.add('report-inline-label');
        }
      });
    };

    doc.body.querySelectorAll('h2').forEach((node, index) => {
      const id = `report-section-${index + 1}`;
      const rawTitle = node.textContent?.trim() || `섹션 ${index + 1}`;
      const match = rawTitle.match(/^(\d+)\.\s*(.+)$/);
      const title = match?.[2]?.trim() || rawTitle;
      const number = match?.[1]?.padStart(2, '0') || String(index + 1).padStart(2, '0');

      node.id = id;
      node.classList.add('report-section-heading');
      node.innerHTML = `<span class="report-section-number">${number}</span><span class="report-section-title-text">${title}</span>`;

      outline.push({
        id,
        title,
        level: 2,
      });
    });

    const groupedBody = doc.createElement('div');
    let activeSection: HTMLElement | null = null;

    Array.from(doc.body.childNodes).forEach((node) => {
      if (node.nodeType === Node.ELEMENT_NODE && (node as HTMLElement).tagName === 'H2') {
        const section = doc.createElement('section');
        section.className = 'report-section-block';
        section.appendChild(node);
        groupedBody.appendChild(section);
        activeSection = section;
        return;
      }

      if (activeSection) {
        activeSection.appendChild(node);
      } else {
        groupedBody.appendChild(node);
      }
    });

    groupedBody.querySelectorAll('.report-section-block').forEach((section, sectionIndex) => {
      const nodes = Array.from(section.childNodes);
      const heading = nodes.shift();
      const sectionBody = doc.createElement('div');
      sectionBody.className = 'report-section-body';
      let activeSubsectionContent: HTMLElement | null = null;
      let subsectionCount = 0;

      if (!heading) return;

      section.innerHTML = '';
      section.appendChild(heading);

      nodes.forEach((node) => {
        const subsection = getSubsectionTitle(node);
        if (subsection) {
          subsectionCount += 1;
          const subsectionId = (node as HTMLElement).id || `report-section-${sectionIndex + 1}-subsection-${subsectionCount}`;
          const subsectionBlock = doc.createElement('div');
          subsectionBlock.className = 'report-subsection-block';

          const subsectionHeading = doc.createElement('div');
          subsectionHeading.className = 'report-subsection-heading';
          subsectionHeading.id = subsectionId;
          subsectionHeading.innerHTML = `
            <span class="report-subsection-index">${subsection.number || String(subsectionCount).padStart(2, '0')}</span>
            <span class="report-subsection-title">${subsection.title}</span>
          `;

          const subsectionBody = doc.createElement('div');
          subsectionBody.className = 'report-subsection-body';

          subsectionBlock.appendChild(subsectionHeading);
          subsectionBlock.appendChild(subsectionBody);
          sectionBody.appendChild(subsectionBlock);
          activeSubsectionContent = subsectionBody;

          outline.push({
            id: subsectionId,
            title: subsection.title,
            level: 3,
          });
          return;
        }

        (activeSubsectionContent || sectionBody).appendChild(node);
      });

      section.appendChild(sectionBody);
    });

    doc.body.innerHTML = groupedBody.innerHTML;
    decorateInlineLabels(doc.body);
    linkifyTextNodes(doc.body);

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
        </div>
        <div className="report-stat-panel">
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
          </div>
          <div className="report-stat-actions">
            <button className="ghost-button" onClick={onRefresh}>본문 새로고침</button>
          </div>
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
                    <span>{renderTextWithLinks(line)}</span>
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

            {playbook && (
              <div className="report-rail-card">
                <div className="report-rail-label">Playbook</div>
                <div className="report-rail-title">단타 / 중기 프레임</div>
                <div className="report-note-line">시장 국면 {playbook.market_regime || 'neutral'}</div>
                <div className="report-note-line">단타 바이어스 {getBiasLabel(playbook.short_term_bias)}</div>
                <div className="report-note-line">중기 바이어스 {getBiasLabel(playbook.mid_term_bias)}</div>
                <div className="report-note-line">유리 섹터 {(playbook.favored_sectors || []).slice(0, 2).join(', ') || '없음'}</div>
                <div className="report-note-line">핵심 리스크 {(playbook.key_risks || [])[0] || '없음'}</div>
              </div>
            )}

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
