import { t } from '../i18n';
import LiveTrends from '../components/LiveTrends';
import { Chip, Icon } from '../components/ui';
import type { RoleData } from '../types';

export default function AIOutlook({ data, sessionToken, pending, hasPlan, onBack, onBuild }: {
  data: RoleData; sessionToken: string | null; pending: boolean; hasPlan: boolean;
  onBack: () => void; onBuild: () => void;
}) {
  return <section id="outlook" className="screen career-detail-page ai-outlook-page">
    <button id="back-to-role" className="button secondary back-link" disabled={pending} onClick={onBack}>{t("← Back to role")}</button>
    <header className="page-heading"><div><span className="eyebrow">{t(data.match.role_title)}</span><h1>{t("See what’s changing.")}</h1><p className="page-intro">{t("What AI could change. What you can practise next.")}</p></div><Chip>{t("AI outlook")}</Chip></header>
    <LiveTrends key={data.match.role_id} roleId={data.match.role_id} token={sessionToken} active>
    <div className="role-next-page"><span className="role-next-icon"><Icon name="path" /></span><div><span className="mini-label">{t("YOUR NEXT MOVE")}</span><h2>{t("Turn insight into action.")}</h2><p>{t("Build a learning plan around this career.")}</p></div><button id="build-roadmap" className="button primary" disabled={pending} onClick={onBuild}>{t(hasPlan ? 'Return to my roadmap' : 'Build my roadmap')} <Icon name="arrow" /></button></div>
    </LiveTrends>
  </section>;
}
