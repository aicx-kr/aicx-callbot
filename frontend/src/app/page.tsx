import { redirect } from 'next/navigation';

interface CallbotAgentDTO {
  id: number;
  memberships: { bot_id: number; role: string }[];
}

async function getFirstMainBotId(): Promise<number | null> {
  const backend = process.env.BACKEND_URL || 'http://localhost:8000';
  try {
    const r = await fetch(`${backend}/api/callbot-agents`, { cache: 'no-store' });
    if (r.ok) {
      const callbots: CallbotAgentDTO[] = await r.json();
      const firstWithMain = callbots.find((c) => c.memberships.some((m) => m.role === 'main'));
      const main = firstWithMain?.memberships.find((m) => m.role === 'main');
      if (main) return main.bot_id;
    }
  } catch {
    // ignore — fall back to bots list
  }
  try {
    const r = await fetch(`${backend}/api/bots`, { cache: 'no-store' });
    if (!r.ok) return null;
    const bots: { id: number }[] = await r.json();
    return bots[0]?.id ?? null;
  } catch {
    return null;
  }
}

export default async function Home() {
  const id = await getFirstMainBotId();
  if (id) redirect(`/bots/${id}/persona`);
  redirect('/tenants');
}
