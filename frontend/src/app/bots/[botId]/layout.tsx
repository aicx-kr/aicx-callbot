import { Shell } from '@/components/Shell';

export default async function BotLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ botId: string }>;
}) {
  const { botId } = await params;
  return <Shell botId={parseInt(botId, 10)}>{children}</Shell>;
}
