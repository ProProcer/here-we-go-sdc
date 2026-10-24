import { t, useLanguage } from '../i18n';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { request } from '../api';
import { lastResult, rememberResult, resultKey, reuseResult } from '../resultCache';
import { Chip, date, Disclosure, EmptyState, ExternalLink, Icon } from './ui';

type Article = { article_id: string; title: string; publisher: string; source_url: string; published_at: string; fetched_at: string; content_scope: string };
type SourceReview = {
  stored_count: number; selected_count: number; assessed_count: number | null; connection_count: number;
  assessment_limit: number; connection_limit: number; legacy_analysis: boolean; updating: boolean;
  articles: { source: Article; outcome: string; reason: string; assessed_by_ai: boolean; reason_origin?: string }[];
};
type TrendData = {
  content_language?: string; translation_status?: string;
  articles: Article[];
  source_review?: SourceReview;
  interpretations: { article_id: string; task_label: string; what_changed: string; role_relevance: string; learning_action: string; evidence_quote: string; source: Article; skills: { skill_id: string; label: string }[] }[];
  refresh: { status: string; last_attempted_at: string | null; last_successful_at: string | null; article_count: number; feeds: { feed_id: string; publisher: string; url: string; status: string; article_count?: number; fetched_at?: string; attempted_at?: string }[] };
  analysis_status: string; analysis_stale?: boolean; analyzed_at: string | null; analysis_provider: string | null; analysis_error: string | null; scope: string;
};
const timestamp = (value: string | null | undefined) => value ? `${value.slice(0, 19).replace('T', ' ')} UTC` : 'Not yet recorded';

function NewsSpinner() {
  return <svg className="spinner news-spinner" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /></svg>;
}

function AnalysisNotice({ pending, hasResult, unavailable, onRetry, disabled }: { pending: boolean; hasResult: boolean; unavailable: boolean; onRetry: () => void; disabled: boolean }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    setSlow(false);
    if (!pending) return;
    const timer = window.setTimeout(() => setSlow(true), 30000);
    return () => window.clearTimeout(timer);
  }, [pending]);
  return <div id="trend-analysis-notice" className="trend-status" role="status">
    <div className="news-loading-heading">{pending && <NewsSpinner />}<h4>{t(pending ? hasResult ? 'Updating career research…' : 'Finding research relevant to this career…' : hasResult ? 'Showing your last completed assessment' : 'Career assessment is unavailable right now')}</h4></div>
    <p>{t(pending ? hasResult ? 'Your completed findings remain available below while we check for updates.' : 'We’re checking the selected research excerpts for useful task and skill connections. The assessment will appear here when it is ready.' : hasResult ? 'We couldn’t complete the latest update. Your earlier assessment and its original source dates remain visible.' : 'The research sources are available, but we haven’t completed a career assessment. This does not mean that no articles are relevant.')}</p>
    {pending && slow && <p>{t("This is taking longer than usual. You can keep exploring other parts of the app and come back here.")}</p>}
    {!pending && !unavailable && <button id="retry-trend-analysis" className="button secondary" disabled={disabled} onClick={onRetry}>{t("Retry assessment")}</button>}
  </div>;
}

export default function LiveTrends({ roleId, token, active, children }: { roleId: string; token: string | null; active: boolean; children?: ReactNode }) {
  const language = useLanguage();
  const query = language === 'en' ? '' : `?language=${language}`;
  const cacheKey = resultKey(token, 'ai-outlook', [roleId, language]);
  const [data, setData] = useState<TrendData | null>(() => lastResult<TrendData>(cacheKey));
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const requestScope = useRef(0);
  useEffect(() => {
    const scope = ++requestScope.current;
    setData(lastResult<TrendData>(cacheKey)); setError('');
    setSubmitting(false);
    if (!active) return;
    let cancelled = false;
    let inFlight = false;
    const load = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const result = await reuseResult(cacheKey, () => request<TrendData>(`/roles/${encodeURIComponent(roleId)}/trends${query}`, token), value =>
          ['queued', 'updating'].includes(value.analysis_status) || value.source_review?.updating || value.refresh.status === 'refreshing' ? 4000 : 60000);
        if (!cancelled) { setData(result); setError(''); }
      } catch (reason) { if (!cancelled) setError(reason instanceof Error ? reason.message : 'Trend sources are temporarily unavailable.'); }
      finally { inFlight = false; }
    };
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => { cancelled = true; if (requestScope.current === scope) ++requestScope.current; window.clearInterval(timer); };
  }, [roleId, token, active, cacheKey, query]);
  async function refresh() {
    const scope = requestScope.current;
    setSubmitting(true); setError('');
    try { const value = await request<TrendData>(`/roles/${encodeURIComponent(roleId)}/trends/refresh${query}`, token, { method: 'POST' }); if (scope === requestScope.current) setData(rememberResult(cacheKey, value, 4000)); }
    catch (reason) { if (scope === requestScope.current) setError(reason instanceof Error ? reason.message : 'Could not refresh trends.'); }
    finally { if (scope === requestScope.current) setSubmitting(false); }
  }
  async function retryAnalysis() {
    const scope = requestScope.current;
    setSubmitting(true); setError('');
    try { const value = await request<TrendData>(`/roles/${encodeURIComponent(roleId)}/trends/retry${query}`, token, { method: 'POST' }); if (scope === requestScope.current) setData(rememberResult(cacheKey, value, 4000)); }
    catch (reason) { if (scope === requestScope.current) setError(reason instanceof Error ? reason.message : 'Could not retry the assessment.'); }
    finally { if (scope === requestScope.current) setSubmitting(false); }
  }
  const review = data?.source_review;
  const pending = data?.analysis_status === 'queued' || data?.analysis_status === 'updating' || Boolean(review?.updating);
  const waiting = pending || submitting || data?.refresh.status === 'refreshing';
  const completed = Boolean(review && review.assessed_count !== null && review.assessed_count > 0);
  const hasResult = completed || Boolean(data?.interpretations.length);
  const unavailable = data?.analysis_status === 'not_configured' || data?.analysis_status === 'no_sources';
  const connectedArticles = review?.articles.filter(item => item.assessed_by_ai && item.outcome === 'connected') || [];
  const connectedIds = new Set(connectedArticles.map(item => item.source.article_id));
  const connections = data?.interpretations.filter(item => connectedIds.has(item.article_id)) || [];
  function sourceCard(item: SourceReview['articles'][number]) {
    return <article className="source-card" key={item.source.article_id}>
      <Chip kind="confirmed">{t("Career connection shown")}</Chip>
      <h3>{item.source.title}</h3>
      <ExternalLink button url={item.source.source_url}>{t("Read source")}</ExternalLink>
      <p className="caption">{item.source.publisher}{t(" · Published ")}<time dateTime={item.source.published_at}>{t(date(item.source.published_at))}</time>{t(" · Fetched ")}<time dateTime={item.source.fetched_at}>{t(timestamp(item.source.fetched_at))}</time></p>
      <p><strong>{t(item.reason_origin === 'validation' ? 'Evidence check: ' : item.assessed_by_ai ? 'AI assessment: ' : 'Assessment context: ')}</strong>{t(item.reason)}</p>
    </article>;
  }
  return <section id="live-trends" aria-label={t("Updatable AI trend sources")}>
    <div className="trend-heading"><div><span className="mini-label">{t("AI & THE FUTURE OF THIS WORK")}</span><h3>{t("AI trends for this career")}</h3></div><button id="refresh-trends" className="button secondary" disabled={!token || submitting || pending || data?.refresh.status === 'refreshing'} onClick={() => void refresh()}><Icon name="spark" />{t(submitting || data?.refresh.status === 'refreshing' ? 'Refreshing sources…' : pending ? 'Assessing research…' : 'Refresh trends')}</button></div>
    <p className="caption">{t("Research connected to this career’s tasks and skills. AI interpretations · not human reviewed.")}</p>
    {error && <p role="alert" className="feedback">{t(error)}</p>}
    {!data ? !error && <div id="news-loading" className="news-loading" role="status"><NewsSpinner /><span>{t("Loading career news…")}</span></div> : <>
      {data.translation_status === 'unavailable' && <p className="caption" role="status">{t('Original English content shown. Translation is temporarily unavailable.')}</p>}
      <div id="live-trend-status" className="trend-status" role="status"><Chip>{t(data.refresh.status === 'fresh' ? 'Feeds up to date' : data.refresh.status === 'refreshing' ? 'Fetching external sources' : 'Cached sources')}</Chip><span>{t(data.refresh.article_count)}{t(" stored articles")}</span><small>{t("Last fetch: ")}<time>{t(timestamp(data.refresh.last_successful_at))}</time></small>{data.refresh.status === 'cached' && <p>{t("The latest refresh is overdue or a source failed. Available dated records remain visible.")}</p>}</div>
      {(waiting || !hasResult || data.analysis_error || data.analysis_stale) && <AnalysisNotice pending={waiting} hasResult={hasResult} unavailable={unavailable} disabled={!token || submitting} onRetry={() => void retryAnalysis()} />}
      {completed && <p className="connection-count">{connections.length}{t(" career ")}{t(connections.length === 1 ? 'connection' : 'connections')}{t(" shown")}</p>}
      <div id="trend-interpretations">
        {connections.map(item => <article className="source-card trend-card" key={`${item.article_id}-${item.task_label}`}>
          <Chip kind="confirmed">{t("Career connection shown")}</Chip>
          <div className="trend-card-heading"><div><h3>{t(item.task_label)}</h3></div></div>
          <p className="trend-finding-preview">{t(item.what_changed.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() || item.what_changed)}</p>
          <div className="trend-action-preview"><Icon name="path" /><div><strong>{t("Try this next")}</strong><p>{t(item.learning_action.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() || item.learning_action)}</p></div></div>
          <div className="chips">{item.skills.map(skill => <Chip key={skill.skill_id}>{t(skill.label)}</Chip>)}</div>
          <Disclosure title={t("Explore finding & evidence")}>
          <Chip>{t("AI interpretation · not human reviewed")}</Chip>
          <span className="mini-label trend-step">{t("WHAT THE RESEARCH REPORTS")}</span><h3>{t(item.what_changed)}</h3>
          <p className="trend-citation"><strong>{item.source.title}</strong><br />{item.source.publisher}{t(" · Published ")}<time dateTime={item.source.published_at}>{t(date(item.source.published_at))}</time>{t(" · Fetched ")}<time dateTime={item.source.fetched_at}>{t(timestamp(item.source.fetched_at))}</time></p>
          <ExternalLink button url={item.source.source_url}>{t("Read original research")}</ExternalLink>
          <dl className="trend-implications"><dt>{t("What it could mean for this career")}</dt><dd>{t(item.role_relevance)}<p className="caption">{t("Related task: ")}{t(item.task_label)}</p></dd><dt>{t("What you can practise")}</dt><dd>{t(item.learning_action)}<div className="chips">{item.skills.map(skill => <Chip key={skill.skill_id}>{t(skill.label)}</Chip>)}</div></dd></dl>
          <Disclosure title={t("Supporting source")}><blockquote>{item.evidence_quote}</blockquote><p className="caption">{t("This excerpt supports the research finding above. Its application to this occupation is an AI interpretation.")}</p></Disclosure>
          </Disclosure>
        </article>)}
        {completed && !connections.length && !waiting && <EmptyState compact symbol="book" title={t("No career connections to show yet")}>{t("No supported connection was found in the assessed excerpts. Try refreshing the research later.")}</EmptyState>}
      </div>
      {!review && data.articles.length > 0 && <p id="trend-version-notice" className="feedback" role="status">{t("This server response does not include article assessments. Restart the app server to load the updated feature, then refresh this page.")}</p>}
      {!data.articles.length && !waiting && <EmptyState compact symbol="book" title={t("No fetched articles available")}>{t("Refresh the configured research feeds to retrieve dated sources.")}</EmptyState>}

    </>}
    {t(children)}
    {data && <div className="outlook-help">
      {completed && review && <div id="trend-review-summary" className="trend-review-summary">
        <Disclosure help id="trend-source-review" title={t("How sources were assessed")}>
          <p className="caption">{t("Last completed assessment: ")}<time>{t(timestamp(data.analyzed_at))}</time>{t(data.analysis_stale ? ' · Newer source material is available.' : '')}</p>
          <p>{review.stored_count}{t(" stored · ")}{review.selected_count}{t(" selected for this career · ")}{t(review.assessed_count === null ? 'AI assessment count not recorded' : `${review.assessed_count} assessed by AI`)} · {review.connection_count}{t(" career ")}{t(review.connection_count === 1 ? 'connection' : 'connections')}{t(" shown")}</p>
          <ul><li>{t("Up to ")}{review.assessment_limit}{t(" research excerpts are assessed for this career.")}</li><li>{t("Up to ")}{review.connection_limit}{t(" supported connections are shown.")}</li><li>{t("Fewer cards do not mean other articles are unrelated.")}</li><li>{t("Sources refresh automatically every 24 hours.")}</li></ul>
          {review.legacy_analysis && <p className="caption">{t("This saved analysis predates article-by-article explanations. Its original assessment count and omission reasons are unavailable.")}{t(review.updating ? ' Updating explanations…' : ' New explanations will appear after a successful AI assessment.')}</p>}
          <p className="caption">{t("AI explanations reflect only the supplied excerpts and have not been human reviewed.")}</p>
          <div id="live-source-list">{t(connectedArticles.map(sourceCard))}</div>
        </Disclosure>
      </div>}
      <Disclosure help id="trend-source-health" title={t("Source health & scope")}><p>{t(data.scope)}{t(" These sources do not measure Malaysian vacancy growth. Trend interpretations do not change your personal fit score.")}</p><p>{t("Last interpretation: ")}{t(timestamp(data.analyzed_at))}{t(data.analysis_provider ? ` · ${data.analysis_provider}` : '')}.</p></Disclosure>
    </div>}
  </section>;
}
