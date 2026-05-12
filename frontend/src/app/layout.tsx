import './globals.css';
import type { Metadata } from 'next';
import { Providers } from '@/components/Providers';

export const metadata: Metadata = {
  title: 'Callbot Console',
  description: 'B2B 에이전트 콘솔 — vox 내재화 MVP',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <body className="bg-ink-50 text-ink-900 dark:bg-ink-900 dark:text-ink-50">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
