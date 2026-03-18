#!/usr/bin/env python3
"""
/reports 디렉토리의 HTML 파일 목록으로 index.html을 생성합니다.
컨테이너 시작 시 entrypoint.sh에 의해 한 번 실행됩니다.
"""

import re
from pathlib import Path

REPORTS_DIR = Path("/reports")
OUTPUT = Path("/usr/share/nginx/html/index.html")


def build_index():
    files = sorted(REPORTS_DIR.glob("*.html"), reverse=True)

    items_html = ""
    for i, f in enumerate(files):
        name = f.name
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", name)
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3)
            date_label = f"{y}년 {mo}월 {d}일"
            date_short = f"{y}.{mo}.{d}"
        else:
            date_label = name
            date_short = ""

        badge = '<span class="latest-badge">최신</span>' if i == 0 else ""

        items_html += f"""
        <li>
          <a href="/reports/{name}" class="{"item-latest" if i == 0 else ""}">
            <div class="item-icon">📊</div>
            <div class="item-body">
              <div class="item-title">{date_label} 일일 경제 리포트 {badge}</div>
              <div class="item-sub">{name}</div>
            </div>
            <div class="item-date">{date_short}</div>
            <div class="item-arrow">›</div>
          </a>
        </li>"""

    if not items_html:
        items_html = "<li class='empty'>리포트 파일이 없습니다.</li>"

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>📊 Daily Report 뷰어</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg: #EEF2F7;
      --surface: #fff;
      --border: #E2E8F0;
      --blue: #2563EB;
      --navy: #0F1F3D;
      --text-1: #111827;
      --text-3: #6B7280;
      --text-4: #9CA3AF;
    }}
    html {{ -webkit-font-smoothing: antialiased; }}
    body {{
      font-family: "Noto Sans KR", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text-1);
      min-height: 100vh;
    }}

    /* Header */
    .site-header {{
      background: linear-gradient(140deg, #0A1628 0%, #102045 40%, #1A3A6E 100%);
      color: #fff;
      padding: 40px 24px 36px;
      text-align: center;
      position: relative;
      overflow: hidden;
    }}
    .site-header::before {{
      content: "";
      position: absolute;
      width: 280px; height: 280px;
      border-radius: 50%;
      right: -60px; top: -100px;
      background: radial-gradient(circle, rgba(59,130,246,.2) 0%, transparent 70%);
    }}
    .header-eyebrow {{
      font-size: 11px;
      font-weight: 500;
      letter-spacing: .18em;
      text-transform: uppercase;
      opacity: .5;
      margin-bottom: 10px;
      position: relative;
    }}
    .header-title {{
      font-size: 28px;
      font-weight: 700;
      letter-spacing: -.5px;
      margin-bottom: 6px;
      position: relative;
    }}
    .header-sub {{
      font-size: 14px;
      opacity: .65;
      position: relative;
    }}

    /* Container */
    .container {{ max-width: 760px; margin: 36px auto; padding: 0 16px 48px; }}

    /* Stats row */
    .stats-row {{
      display: flex;
      gap: 12px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }}
    .stat-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px 20px;
      flex: 1;
      min-width: 120px;
      text-align: center;
      box-shadow: 0 1px 3px rgba(0,0,0,.06);
    }}
    .stat-num {{ font-size: 22px; font-weight: 700; color: var(--blue); }}
    .stat-label {{ font-size: 12px; color: var(--text-3); margin-top: 2px; }}

    /* Report list card */
    .list-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      overflow: hidden;
      box-shadow: 0 2px 8px rgba(0,0,0,.06);
    }}
    .list-header {{
      padding: 14px 22px;
      border-bottom: 1px solid var(--border);
      font-size: 13px;
      font-weight: 600;
      color: var(--text-3);
      letter-spacing: .04em;
      text-transform: uppercase;
      background: #FAFBFC;
    }}
    ul {{ list-style: none; }}
    ul li a {{
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 16px 22px;
      text-decoration: none;
      color: var(--text-1);
      border-bottom: 1px solid #F1F5F9;
      transition: background .13s;
    }}
    ul li:last-child a {{ border-bottom: none; }}
    ul li a:hover {{ background: #EFF6FF; }}
    ul li a.item-latest {{ background: #FAFFFE; }}
    ul li a.item-latest:hover {{ background: #F0FDF4; }}

    .item-icon {{ font-size: 22px; flex-shrink: 0; }}
    .item-body {{ flex: 1; min-width: 0; }}
    .item-title {{
      font-weight: 600;
      font-size: 14.5px;
      color: var(--text-1);
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .item-sub {{ font-size: 12px; color: var(--text-4); font-family: monospace; margin-top: 2px; }}
    .item-date {{ font-size: 12px; color: var(--text-3); font-weight: 500; white-space: nowrap; }}
    .item-arrow {{ font-size: 20px; color: var(--text-4); font-weight: 300; }}
    .latest-badge {{
      background: #DCFCE7;
      color: #166534;
      border: 1px solid #BBF7D0;
      border-radius: 99px;
      padding: 1px 9px;
      font-size: 11px;
      font-weight: 600;
    }}
    .empty {{ padding: 40px; text-align: center; color: var(--text-4); font-size: 14px; }}

    /* Footer */
    footer {{ text-align: center; padding: 20px; color: var(--text-4); font-size: 12px; }}

    @media (max-width: 480px) {{
      .stats-row {{ gap: 8px; }}
      ul li a {{ padding: 14px 16px; gap: 10px; }}
    }}
  </style>
</head>
<body>
  <div class="site-header">
    <div class="header-eyebrow">Daily Report Archive</div>
    <div class="header-title">📊 일일 경제 리포트</div>
    <div class="header-sub">자동 생성 경제 분석 리포트 아카이브</div>
  </div>

  <div class="container">
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-num">{len(files)}</div>
        <div class="stat-label">총 리포트</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{"매일" if len(files) > 0 else "—"}</div>
        <div class="stat-label">생성 주기</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">07:00</div>
        <div class="stat-label">KST 생성 시각</div>
      </div>
    </div>

    <div class="list-card">
      <div class="list-header">📁 리포트 목록</div>
      <ul>{items_html}
      </ul>
    </div>
  </div>

  <footer>Daily Report Viewer &nbsp;·&nbsp; /reports 디렉토리를 마운트하면 자동으로 목록에 표시됩니다.</footer>
</body>
</html>"""

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"✅ index.html 생성 완료 ({len(files)}개 리포트)")


if __name__ == "__main__":
    build_index()

