import { t } from '../i18n';
import SDGImpact from '../components/SDGImpact';
import { Chip, EmptyState, ExternalLink } from '../components/ui';
import type { Plan, RoleData } from '../types';

export default function SDG({ data, plan, pending, onBack }: {
  data: RoleData; plan: Plan; pending: boolean; onBack: () => void;
}) {
  return <section id="sdg" className="screen career-detail-page sdg-page">
    <button id="back-to-roadmap" className="button secondary back-link" disabled={pending} onClick={onBack}>{t("← Back to my roadmap")}</button>
    <header className="page-heading"><div><span className="eyebrow">{t(data.match.role_title)}</span><h1>{t("Skills with a wider impact.")}</h1><p className="page-intro">{t("Explore your connections to the Sustainable Development Goals.")}</p></div></header>
    {plan.sdg_summary ? <SDGImpact summary={plan.sdg_summary} /> : <section className="surface" aria-label={t("SDG connections")}>
      <div id="sdg-connections">{plan.sdg_connections.length ? plan.sdg_connections.map((connection, index) => <article className="sdg-connection" key={index}><Chip>{t(connection.sdg_id)}{t(" · Target ")}{t(connection.target_id)}</Chip><p>{t(connection.rationale)}</p><ExternalLink button url={connection.evidence_url}>{t("Read the UN target")}</ExternalLink></article>) : <EmptyState compact title={t("No SDG connections available yet")}>{t("No supported relationships are stored for these learning objectives.")}</EmptyState>}</div>
      <p className="caption">{t("These are conditional connections to UN targets, not measured outcomes.")}</p>
    </section>}
  </section>;
}
