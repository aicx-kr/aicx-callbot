'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import useSWR from 'swr';
import { useState } from 'react';
import {
  ChevronDown, ChevronRight, FileText, BookOpen, Sparkles, BarChart3, Tags, Lightbulb,
  PhoneCall, Building2, Search, Home as HomeIcon, MessageSquare, Wrench, Code, PhoneOff, ArrowLeftRight, Globe, KeyRound, GitBranch, Settings, Server, Bot as BotIcon,
} from 'lucide-react';
import clsx from 'clsx';
import { fetcher } from '@/lib/api';
import type { Skill, KnowledgeItem, Tenant, Bot, Tool, CallbotAgent } from '@/lib/types';

export function Sidebar({ botId, botName }: { botId: number; botName?: string }) {
  const pathname = usePathname();
  const { data: skills } = useSWR<Skill[]>(`/api/skills?bot_id=${botId}`, fetcher);
  const { data: kbs } = useSWR<KnowledgeItem[]>(`/api/knowledge?bot_id=${botId}`, fetcher);
  const { data: tools } = useSWR<Tool[]>(`/api/tools?bot_id=${botId}`, fetcher);
  const { data: tenants } = useSWR<Tenant[]>('/api/tenants', fetcher);
  const { data: bots } = useSWR<Bot[]>('/api/bots', fetcher);
  const { data: callbots } = useSWR<CallbotAgent[]>('/api/callbot-agents', fetcher);

  const [openKb, setOpenKb] = useState(true);
  const [openSkill, setOpenSkill] = useState(true);
  const [openTool, setOpenTool] = useState(true);

  const tenant = tenants?.find((t) => bots?.find((b) => b.id === botId)?.tenant_id === t.id);
  const isActive = (href: string) => pathname === href || pathname.startsWith(href + '/');
  const currentBot = bots?.find((b) => b.id === botId);
  const isFlowAgent = currentBot?.agent_type === 'flow';
  const [agentMenuOpen, setAgentMenuOpen] = useState(false);
  // CallbotAgent 단위로 분류: 현재 봇이 속한 callbot 우선
  const callbotsInTenant = (callbots || []).filter((c) => c.tenant_id === currentBot?.tenant_id);
  const currentCallbot = callbotsInTenant.find((c) => c.memberships.some((m) => m.bot_id === botId));
  const [expandedCallbot, setExpandedCallbot] = useState<number | null>(currentCallbot?.id ?? null);
  // bot lookup helper
  const botById = (id: number) => bots?.find((b) => b.id === id);

  return (
    <aside className="w-[260px] shrink-0 border-r border-ink-100 dark:border-ink-700 bg-white dark:bg-ink-900 flex flex-col h-full min-h-0">
      <div className="p-3 border-b border-ink-100 dark:border-ink-700 shrink-0 relative">
        <button
          onClick={() => setAgentMenuOpen((v) => !v)}
          className="w-full flex items-center gap-2 px-2 py-2 rounded-md hover:bg-ink-50 dark:hover:bg-ink-800 text-left"
        >
          <div className="w-7 h-7 rounded-md bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white text-xs font-bold flex items-center justify-center">
            {(tenant?.name?.[0] || 'A').toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold truncate dark:text-ink-100">{tenant?.name ?? '워크스페이스'}</div>
            <div className="text-[11px] text-ink-500 dark:text-ink-400 truncate">{botName ?? '...'}</div>
          </div>
          <ChevronDown className={clsx('w-3.5 h-3.5 text-ink-400 transition-transform', agentMenuOpen && 'rotate-180')} />
        </button>

        {agentMenuOpen && (
          <>
            <div className="fixed inset-0 z-30" onClick={() => setAgentMenuOpen(false)} />
            <div className="absolute left-3 right-3 top-[64px] z-40 bg-white dark:bg-ink-800 border border-ink-200 dark:border-ink-700 rounded-md shadow-lg overflow-hidden">
              <div className="px-3 py-2 text-[10px] uppercase font-semibold tracking-wider text-ink-500 dark:text-ink-400 border-b border-ink-100 dark:border-ink-700 flex items-center gap-1.5">
                <BotIcon className="w-3.5 h-3.5" /> {tenant?.name} · 콜봇 에이전트
              </div>
              <div className="max-h-[360px] overflow-y-auto scrollbar-thin">
                {callbotsInTenant.length === 0 && (
                  <div className="px-3 py-3 text-xs text-ink-400 dark:text-ink-500">콜봇 에이전트가 없습니다.</div>
                )}
                {callbotsInTenant.map((c) => {
                  const expanded = expandedCallbot === c.id;
                  const sortedMembers = [...c.memberships].sort((a, b) => (a.role === 'main' ? -1 : b.role === 'main' ? 1 : a.order - b.order));
                  const mainMember = c.memberships.find((m) => m.role === 'main');
                  const mainBotId = mainMember?.bot_id;
                  return (
                    <div key={c.id} className="border-b border-ink-100 dark:border-ink-700 last:border-b-0">
                      <div className="flex items-stretch">
                        <button
                          onClick={() => setExpandedCallbot(expanded ? null : c.id)}
                          className="px-2 hover:bg-ink-50 dark:hover:bg-ink-700 flex items-center"
                          aria-label={expanded ? '접기' : '펼치기'}
                        >
                          {expanded ? <ChevronDown className="w-3.5 h-3.5 text-ink-400" /> : <ChevronRight className="w-3.5 h-3.5 text-ink-400" />}
                        </button>
                        <Link
                          href={mainBotId ? `/bots/${mainBotId}/persona` : `/callbot-agents/${c.id}`}
                          onClick={() => setAgentMenuOpen(false)}
                          className="flex-1 flex items-center gap-2 px-2 py-2 text-sm hover:bg-ink-50 dark:hover:bg-ink-700"
                          title="메인 에이전트로 진입"
                        >
                          <div className="w-5 h-5 rounded bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white text-[9px] font-bold flex items-center justify-center shrink-0">
                            {c.name[0]}
                          </div>
                          <span className="truncate flex-1 font-semibold dark:text-ink-100">{c.name}</span>
                          <span className="text-[10px] text-ink-400 dark:text-ink-500">{c.memberships.length}</span>
                        </Link>
                      </div>
                      {expanded && (
                        <div className="pl-7 pb-1">
                          {sortedMembers.map((m) => {
                            const b = botById(m.bot_id);
                            if (!b) return null;
                            return (
                              <Link
                                key={m.id}
                                href={`/bots/${b.id}/persona`}
                                onClick={() => setAgentMenuOpen(false)}
                                className={clsx(
                                  'flex items-center gap-1.5 px-2 py-1.5 text-[13px] rounded ml-1 mr-2',
                                  b.id === botId
                                    ? 'bg-violet-50 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300'
                                    : 'hover:bg-ink-50 dark:hover:bg-ink-700 dark:text-ink-200',
                                )}
                              >
                                <span className={clsx(
                                  'text-[9px] font-bold tracking-wider px-1 rounded',
                                  m.role === 'main'
                                    ? 'bg-violet-200 dark:bg-violet-800 text-violet-800 dark:text-violet-200'
                                    : 'bg-ink-100 dark:bg-ink-700 text-ink-500 dark:text-ink-400',
                                )}>{m.role === 'main' ? '메인' : 'SUB'}</span>
                                <span className="truncate flex-1">{b.name}</span>
                                <span className={clsx(
                                  'text-[9px] font-bold tracking-wider px-1 rounded shrink-0',
                                  b.agent_type === 'flow'
                                    ? 'bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300'
                                    : 'bg-ink-100 dark:bg-ink-800 text-ink-500 dark:text-ink-400',
                                )}>{b.agent_type === 'flow' ? 'FLOW' : 'PROMPT'}</span>
                              </Link>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
              <Link
                href="/agents"
                onClick={() => setAgentMenuOpen(false)}
                className="flex items-center gap-2 px-3 py-2 text-sm border-t border-ink-100 dark:border-ink-700 hover:bg-ink-50 dark:hover:bg-ink-700 text-violet-600 dark:text-violet-400 font-medium"
              >
                <BotIcon className="w-4 h-4" /> 전체 에이전트 보기 / 새 에이전트
              </Link>
              {tenants && tenants.length > 1 && (
                <div className="border-t border-ink-100 dark:border-ink-700 px-3 py-2">
                  <div className="text-[10px] uppercase font-semibold tracking-wider text-ink-400 mb-1">다른 워크스페이스</div>
                  {tenants.filter((t) => t.id !== tenant?.id).map((t) => {
                    const firstBot = (bots || []).find((b) => b.tenant_id === t.id);
                    return (
                      <Link
                        key={t.id}
                        href={firstBot ? `/bots/${firstBot.id}/persona` : '/agents'}
                        onClick={() => setAgentMenuOpen(false)}
                        className="flex items-center gap-2 py-1 text-sm hover:text-violet-700 dark:hover:text-violet-300"
                      >
                        <Building2 className="w-3 h-3 text-ink-400" />
                        <span className="dark:text-ink-100">{t.name}</span>
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin pb-2">
        <div className="px-2 pt-3 pb-2 space-y-0.5">
          <SidebarLink href={`/bots/${botId}/settings`} icon={<Settings className="w-4 h-4 text-ink-500" />} label="에이전트 설정" active={isActive(`/bots/${botId}/settings`)} />
          <SidebarRow icon={<Search className="w-4 h-4" />} label="검색" muted />
          <SidebarRow icon={<HomeIcon className="w-4 h-4" />} label="홈" muted />
          <SidebarRow icon={<MessageSquare className="w-4 h-4" />} label="대화" muted />
        </div>

        <Section title="분석">
          <SidebarRow icon={<BarChart3 className="w-4 h-4" />} label="지표 & 리포트" muted />
          <SidebarRow icon={<Tags className="w-4 h-4" />} label="태그" muted />
          <SidebarRow icon={<Lightbulb className="w-4 h-4" />} label="제안" muted />
        </Section>

        <Section title="빌드">
          <SidebarLink href={`/bots/${botId}/persona`} icon={<FileText className="w-4 h-4 text-rose-500" />} label="페르소나" active={isActive(`/bots/${botId}/persona`)} />

          <Expandable title="지식" icon={<BookOpen className="w-4 h-4 text-emerald-500" />} open={openKb} onToggle={() => setOpenKb(!openKb)} rootHref={`/bots/${botId}/knowledge`} rootActive={isActive(`/bots/${botId}/knowledge`)}>
            <SidebarLink href={`/bots/${botId}/knowledge?new=1`} label="＋ 새 지식" sub active={false} />
            {kbs?.map((k) => (
              <SidebarLink key={k.id} href={`/bots/${botId}/knowledge/${k.id}`} label={k.title} sub active={isActive(`/bots/${botId}/knowledge/${k.id}`)} />
            ))}
          </Expandable>

          {/* Agent type별로 다른 메뉴 — Prompt 봇은 스킬, Flow 봇은 Flow 편집기 */}
        {isFlowAgent ? (
          <SidebarLink
            href={`/bots/${botId}/flow`}
            icon={<GitBranch className="w-4 h-4 text-violet-500" />}
            label={<span className="flex items-center gap-1.5"><span>Flow</span><span className="text-[10px] px-1 py-0.5 rounded bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300 font-medium">그래프</span></span>}
            active={isActive(`/bots/${botId}/flow`)}
          />
        ) : (
          <Expandable title="스킬" icon={<Sparkles className="w-4 h-4 text-violet-500" />} open={openSkill} onToggle={() => setOpenSkill(!openSkill)} rootHref={`/bots/${botId}/skills`} rootActive={isActive(`/bots/${botId}/skills`)}>
            <SidebarLink href={`/bots/${botId}/skills?new=1`} label="＋ 새 스킬" sub active={false} />
            {skills?.map((s) => (
              <SidebarLink key={s.id} href={`/bots/${botId}/skills/${s.id}`}
                label={<span className="flex items-center gap-1.5"><span className="truncate">{s.name}</span>{s.is_frontdoor && <span className="text-[10px] px-1 py-0.5 rounded bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300 font-medium">FD</span>}</span>}
                sub active={isActive(`/bots/${botId}/skills/${s.id}`)} />
            ))}
          </Expandable>
        )}

          <SidebarLink href={`/bots/${botId}/env`} icon={<KeyRound className="w-4 h-4 text-sky-500" />} label="환경변수" active={isActive(`/bots/${botId}/env`)} />

          <Expandable title="도구" icon={<Wrench className="w-4 h-4 text-amber-500" />} open={openTool} onToggle={() => setOpenTool(!openTool)} rootHref={`/bots/${botId}/tools`} rootActive={isActive(`/bots/${botId}/tools`)}>
            <SidebarLink href={`/bots/${botId}/tools?new=1`} label="＋ 새 도구" sub active={false} />
            {tools?.map((t) => (
              <SidebarLink key={t.id} href={`/bots/${botId}/tools/${t.id}`}
                label={<span className="flex items-center gap-1.5">{toolIcon(t)}<span className="truncate">{t.name}</span></span>}
                sub active={isActive(`/bots/${botId}/tools/${t.id}`)} />
            ))}
          </Expandable>

          <SidebarLink
            href={`/bots/${botId}/mcp`}
            icon={<Server className="w-4 h-4 text-amber-500" />}
            label="MCP 서버"
            active={isActive(`/bots/${botId}/mcp`)}
          />
        </Section>

        {currentCallbot && (
          <Section title="콜봇">
            <SidebarLink
              href={`/callbot-agents/${currentCallbot.id}`}
              icon={<BotIcon className="w-4 h-4 text-fuchsia-500" />}
              label={<span className="flex items-center gap-1.5"><span>에이전트 관리</span><span className="text-[10px] px-1 py-0.5 rounded bg-fuchsia-100 dark:bg-fuchsia-900/40 text-fuchsia-700 dark:text-fuchsia-300 font-medium">{currentCallbot.memberships.length}</span></span>}
              active={pathname === `/callbot-agents/${currentCallbot.id}`}
            />
          </Section>
        )}

        <Section title="운영">
          <SidebarLink href={`/bots/${botId}/calls`} icon={<PhoneCall className="w-4 h-4" />} label="통화 로그" active={isActive(`/bots/${botId}/calls`)} />
          <SidebarLink href="/tenants" icon={<Building2 className="w-4 h-4" />} label="고객사" active={pathname === '/tenants'} />
        </Section>
      </div>

      <div className="shrink-0 p-3 border-t border-ink-100 dark:border-ink-700 text-[11px] text-ink-400 dark:text-ink-500">
        Callbot Console v0.1 · vox 내재화 MVP
      </div>
    </aside>
  );
}

function toolIcon(t: Tool) {
  if (t.type === 'builtin' && t.name === 'end_call') return <PhoneOff className="w-3 h-3 text-ink-500" />;
  if (t.type === 'builtin' && (t.name === 'transfer_to_specialist' || t.name === 'handover_to_human')) return <ArrowLeftRight className="w-3 h-3 text-ink-500" />;
  if (t.type === 'rest') return <Globe className="w-3 h-3 text-ink-500" />;
  return <Code className="w-3 h-3 text-ink-500" />;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="px-2 pt-3 pb-1">
      <div className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-400 dark:text-ink-500">{title}</div>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

function SidebarRow({ icon, label, muted }: { icon?: React.ReactNode; label: React.ReactNode; muted?: boolean }) {
  return (
    <div className={clsx('flex items-center gap-2 px-2 py-1.5 rounded-md text-sm cursor-default', muted ? 'text-ink-400 dark:text-ink-500' : 'text-ink-700 dark:text-ink-200 hover:bg-ink-50 dark:hover:bg-ink-800')}>
      {icon}<span className="truncate">{label}</span>
    </div>
  );
}

function SidebarLink({ href, icon, label, active, sub }: { href: string; icon?: React.ReactNode; label: React.ReactNode; active: boolean; sub?: boolean }) {
  return (
    <Link href={href} className={clsx(
      'flex items-center gap-2 rounded-md text-sm',
      sub ? 'pl-8 pr-2 py-1' : 'px-2 py-1.5',
      active ? 'bg-violet-50 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 font-medium' : 'text-ink-700 dark:text-ink-200 hover:bg-ink-50 dark:hover:bg-ink-800',
    )}>
      {icon}<span className="truncate flex-1">{label}</span>
    </Link>
  );
}

function Expandable({ title, icon, open, onToggle, rootHref, rootActive, children }: { title: string; icon: React.ReactNode; open: boolean; onToggle: () => void; rootHref: string; rootActive: boolean; children: React.ReactNode }) {
  return (
    <div>
      <div className={clsx(
        'flex items-center gap-1 rounded-md text-sm',
        rootActive ? 'bg-violet-50 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300' : 'text-ink-700 dark:text-ink-200 hover:bg-ink-50 dark:hover:bg-ink-800',
      )}>
        <button onClick={onToggle} className="flex items-center justify-center w-5 h-7" aria-label={open ? '접기' : '펼치기'}>
          {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        </button>
        <Link href={rootHref} className="flex items-center gap-2 flex-1 py-1.5 pr-2">
          {icon}<span className={clsx('truncate', rootActive && 'font-medium')}>{title}</span>
        </Link>
      </div>
      {open && <div className="space-y-0.5 mt-0.5">{children}</div>}
    </div>
  );
}
