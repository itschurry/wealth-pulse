export function getQuantSignalLabel(signal?: string | null) {
  if (signal === '추천') return '롱 우위';
  if (signal === '회피') return '기대값 낮음';
  return signal || '중립';
}

export function getQuantGateLabel(status?: string | null) {
  if (status === 'passed') return '필터 통과';
  if (status === 'blocked') return '제외';
  return '주의';
}

export function getQuantActionLabel(action?: string | null) {
  if (action === 'buy') return '롱 진입 검토';
  if (action === 'hold') return '보유 유지';
  if (action === 'sell') return '익절/축소 검토';
  if (action === 'watch') return '관찰 유지';
  return action || '관찰';
}

export function getBiasLabel(bias?: string | null) {
  if (bias === 'bullish') return '롱 우위';
  if (bias === 'defensive') return '방어 우위';
  return '중립';
}

export function getSetupQualityLabel(value?: string | null) {
  if (value === 'high') return '셋업 양호';
  if (value === 'low') return '셋업 약함';
  if (value === 'unknown') return '지표 확인 전';
  return '혼합 신호';
}
