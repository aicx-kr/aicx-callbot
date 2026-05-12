/** 보이스·언어·LLM 모델 옵션 — 콘솔 전체 단일 진실. */

export interface SelectOption {
  id: string;
  label: string;
}

export const KO_VOICES: SelectOption[] = [
  { id: 'ko-KR-Neural2-A', label: '수아 (여성, Neural2-A)' },
  { id: 'ko-KR-Neural2-B', label: '나리 (여성, Neural2-B)' },
  { id: 'ko-KR-Neural2-C', label: '준호 (남성, Neural2-C)' },
  { id: 'ko-KR-Wavenet-A', label: '미라 (여성, Wavenet-A)' },
  { id: 'ko-KR-Wavenet-D', label: '도윤 (남성, Wavenet-D)' },
];

export const LANGUAGES: SelectOption[] = [
  { id: 'ko-KR', label: '한국어' },
  { id: 'en-US', label: 'English' },
  { id: 'ja-JP', label: '日本語' },
];

export const LLM_MODELS: string[] = [
  'gemini-3.1-flash-lite',
  'gemini-3.1-pro-preview',
  'gemini-2.5-flash',
  'gemini-2.5-pro',
  'gemini-flash-latest',
];
