import { useEffect, useRef, useState } from 'react';
import { request } from '../api';
import { Chip, date, Disclosure, EmptyState, ExternalLink, Icon } from './ui';

type Article = { article_id: string; title: string; publisher: string; source_url: string; published_at: string; fetched_at: string; content_scope: string };
type SourceReview = {
  stored_count: number; selected_count: number; assessed_count: number | null; connection_count: number;
  assessment_limit: number; connection_limit: number; legacy_analysis: boolean; updating: boolean;
  articles: { source: Article; outcome: string; reason: string; assessed_by_ai: boolean; reason_origin?: string }[];
};
type TrendData = {
  articles: Article[];
  source_review?: SourceReview;
  interpretations: { article_id: string; task_label: string; what_changed: string; role_relevance: string; learning_action: string; evidence_quote: string; source: Article; skills: { skill_id: string; label: string }[] }[];
  refresh: { status: string; last_attempted_at: string | null; last_successful_at: string | null; article_count: number; feeds: { feed_id: string; publisher: string; url: string; status: string; article_count?: number; fetched_at?: string; attempted_at?: string }[] };
  analysis_status: string; analysis_stale?: boolean; analyzed_at: string | null; analysis_provider: string | null; analysis_error: string | null; scope: string;
};
const timestamp = (value: string | null | undefined) => value ? `${value.slice(0, 19).replace('T', ' ')} UTC` : 'Not yet recorded';
const outcomes: Record<string, string> = {
  connected: 'Career connection shown', indirect_relevance: 'Indirect relevance',
  insufficient_detail: 'Excerpt lacks enough detail', no_clear_connection: 'No clear task connection in excerpt',
  related_not_selected: 'Potentially related · not chosen for a card', not_selected: 'Not selected for AI assessment',
  insufficient_text: 'Not assessed · too little source text', not_assessed: 'AI assessment pending',
  not_recorded: 'Earlier assessment not recorded',
  connection_not_verified: 'Connection withheld · citation not verified',
};

function AnalysisNotice({ pending, hasResult, unavailable, onRetry, disabled }: { pending: boolean; hasResult: boolean; unavailable: boolean; onRetry: () => void; disabled: boolean }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    setSlow(false);
    if (!pending) return;
    const timer = window.setTimeout(() => setSlow(true), 30000);
    return () => window.clearTimeout(timer);
  }, [pending]);
  return <div id="trend-analysis-notice" className="trend-status" role="status">
    <h4>{pending ? hasResult ? 'Updating career research…' : 'Finding research relevant to this career…' : hasResult ? 'Showing your last completed assessment' : 'Career assessment is unavailable right now'}</h4>
    <p>{pending ? hasResult ? 'Your completed findings remain available below while we check for updates.' : 'We’re checking the selected research excerpts for useful task and skill connections. The assessment will appear here when it is ready.' : hasResult ? 'We couldn’t complete the latest update. Your earlier assessment and its original source dates remain visible.' : 'The research sources are available, but we haven’t completed a career assessment. This does not mean that no articles are relevant.'}</p>
    {pending && slow && <p>This is taking longer than usual. You can keep exploring other parts of the app and come back here.</p>}
    {!pending && !unavailable && <button id="retry-trend-analysis" className="button secondary" disabled={disabled} onClick={onRetry}>Retry assessment</button>}
  </div>;
}

export default function LiveTrends({ roleId, token, active }: { roleId: string; token: string | null; active: boolean }) {
  const [data, setData] = useState<TrendData | null>(null);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const requestScope = useRef(0);
  useEffect(() => {
    const scope = ++requestScope.current;
    setData(null); setError('');
    setSubmitting(false);
    if (!active) return;
    let cancelled = false;
    let inFlight = false;
    const load = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const result = await request<TrendData>(`/roles/${encodeURIComponent(roleId)}/trends`, token);
        if (!cancelled) { setData(result); setError(''); }
      } catch (reason) { if (!cancelled) setError(reason instanceof Error ? reason.message : 'Trend sources are temporarily unavailable.'); }
      finally { inFlight = false; }
    };
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => { cancelled = true; if (requestScope.current === scope) ++requestScope.current; window.clearInterval(timer); };
  }, [roleId, token, active]);
  async function refresh() {
    const scope = requestScope.current;
    setSubmitting(true); setError('');
    try { const value = await request<TrendData>(`/roles/${encodeURIComponent(roleId)}/trends/refresh`, token, { method: 'POST' }); if (scope === requestScope.current) setData(value); }
    catch (reason) { if (scope === requestScope.current) setError(reason instanceof Error ? reason.message : 'Could not refresh trends.'); }
    finally { if (scope === requestScope.current) setSubmitting(false); }
  }
  async function retryAnalysis() {
    const scope = requestScope.current;
    setSubmitting(true); setError('');
    try { const value = await request<TrendData>(`/roles/${encodeURIComponent(roleId)}/trends/retry`, token, { method: 'POST' }); if (scope === requestScope.current) setData(value); }
    catch (reason) { if (scope === requestScope.current) setError(reason instanceof Error ? reason.message : 'Could not retry the assessment.'); }
    finally { if (scope === requestScope.current) setSubmitting(false); }
  }
  const review = data?.source_review;
  const pending = data?.analysis_status === 'queued' || data?.analysis_status === 'updating' || Boolean(review?.updating);
  const completed = Boolean(review && review.assessed_count !== null && review.assessed_count > 0);
  const hasResult = completed || Boolean(data?.interpretations.length);
  const unavailable = data?.analysis_status === 'not_configured' || data?.analysis_status === 'no_sources';
  const assessedArticles = review?.articles.filter(item => item.assessed_by_ai) || [];
  const otherArticles = review?.articles.filter(item => !item.assessed_by_ai && item.outcome !== 'not_assessed' && item.outcome !== 'not_recorded') || [];
  function sourceCard(item: SourceReview['articles'][number]) {
    return <article className="source-card" key={item.source.article_id}>
      <Chip>{outcomes[item.outcome] || 'Assessment unavailable'}</Chip>
      <h3><ExternalLink url={item.source.source_url}>{item.source.title}</ExternalLink></h3>
      <p className="caption">{item.source.publisher} · Published <time dateTime={item.source.published_at}>{date(item.source.published_at)}</time> · Fetched <time dateTime={item.source.fetched_at}>{timestamp(item.source.fetched_at)}</time></p>
      <p><strong>{item.reason_origin === 'validation' ? 'Evidence check: ' : item.assessed_by_ai ? 'AI assessment: ' : 'Assessment context: '}</strong>{item.reason}</p>
    </article>;
  }
  return <section id="live-trends" aria-label="Updatable AI trend sources">
    <div className="trend-heading"><div><span className="mini-label">AI & THE FUTURE OF THIS WORK</span><h3>AI trends for this career</h3></div><button id="refresh-trends" className="button secondary" disabled={!token || submitting || pending || data?.refresh.status === 'refreshing'} onClick={() => void refresh()}><Icon name="spark" />{submitting || data?.refresh.status === 'refreshing' ? 'Refreshing sources…' : pending ? 'Assessing research…' : 'Refresh trends'}</button></div>
    <p>How might AI change the work, and what should you learn next? Explore findings from updatable research feeds, connected to this occupation’s tasks and skills.</p>
    <p className="caption">Each connection shows a research finding, its possible effect on your work, and a learning action. Connections are AI interpretations and have not been human reviewed. Research findings do not measure hiring demand.</p>
    {error && <p role="alert" className="feedback">{error}</p>}
    {!data ? !error && <p role="status">Loading source dates and research…</p> : <>
      <div id="live-trend-status" className="trend-status" role="status"><Chip>{data.refresh.status === 'fresh' ? 'Feeds up to date' : data.refresh.status === 'refreshing' ? 'Fetching external sources' : 'Cached sources'}</Chip><p>{data.refresh.article_count} stored articles · Automatic source refresh every 24 hours</p><p>Last successful fetch: <time>{timestamp(data.refresh.last_successful_at)}</time></p>{data.refresh.status === 'cached' && <p>The latest refresh is overdue or a source failed. Available dated records remain visible.</p>}</div>
      {(pending || !hasResult || data.analysis_error || data.analysis_stale) && <AnalysisNotice pending={pending} hasResult={hasResult} unavailable={unavailable} disabled={!token || submitting} onRetry={() => void retryAnalysis()} />}
      {completed && review && <div id="trend-review-summary" className="trend-review-summary">
        <h4>How much research was assessed?</h4>
        <p className="caption">Last completed assessment: <time>{timestamp(data.analyzed_at)}</time>{data.analysis_stale ? ' · Newer source material is available.' : ''}</p>
        <p>{review.stored_count} stored · {review.selected_count} selected for this career · {review.assessed_count === null ? 'AI assessment count not recorded' : `${review.assessed_count} assessed by AI`} · {review.connection_count} career {review.connection_count === 1 ? 'connection' : 'connections'} shown</p>
        <p className="caption">We rank the stored articles against this career’s description and tasks, then send up to {review.assessment_limit} excerpts with enough text to the AI. It can show up to {review.connection_limit} supported connections. Fewer cards do not mean the remaining articles are useless or unrelated.</p>
        {review.legacy_analysis && <p className="caption">This saved analysis predates article-by-article explanations. Its original assessment count and omission reasons are unavailable.{review.updating ? ' Updating explanations…' : ' New explanations will appear after a successful AI assessment.'}</p>}
        <Disclosure id="trend-source-review" title="How sources were assessed">
          <p className="caption">AI explanations reflect only the supplied excerpts and have not been human reviewed. Articles marked “not selected” were ranked by the app and were not assessed by the AI.</p>
          <div id="live-source-list">{assessedArticles.map(sourceCard)}
            {otherArticles.length > 0 && <Disclosure title={`Other fetched research (${otherArticles.length})`}>{otherArticles.map(sourceCard)}</Disclosure>}
          </div>
        </Disclosure>
      </div>}
      <div id="trend-interpretations">
        {data.interpretations.map(item => <article className="source-card trend-card" key={`${item.article_id}-${item.task_label}`}>
          <Chip>AI interpretation · not human reviewed</Chip>
          <span className="mini-label trend-step">WHAT THE RESEARCH REPORTS</span><h3>{item.what_changed}</h3>
          <p className="trend-citation"><ExternalLink url={item.source.source_url}>{item.source.title}</ExternalLink><br />{item.source.publisher} · Published <time dateTime={item.source.published_at}>{date(item.source.published_at)}</time> · Fetched <time dateTime={item.source.fetched_at}>{timestamp(item.source.fetched_at)}</time></p>
          <dl className="trend-implications"><dt>What it could mean for this career</dt><dd>{item.role_relevance}<p className="caption">Related task: {item.task_label}</p></dd><dt>What you can practise</dt><dd>{item.learning_action}<div className="chips">{item.skills.map(skill => <Chip key={skill.skill_id}>{skill.label}</Chip>)}</div></dd></dl>
          <Disclosure title="Supporting source"><blockquote>{item.evidence_quote}</blockquote><p className="caption">This excerpt supports the research finding above. Its application to this occupation is an AI interpretation.</p></Disclosure>
        </article>)}
        {completed && !data.interpretations.length && <p>No verified career connection is available from these assessed excerpts. Expand “How sources were assessed” to see each finding and any evidence checks.</p>}
      </div>
      {!completed && review && <Disclosure title="Browse dated research sources"><p className="caption">These are fetched source articles, not completed career assessments.</p>{review.articles.map(item => <p key={item.source.article_id}><ExternalLink url={item.source.source_url}>{item.source.title}</ExternalLink> · {item.source.publisher} · Published {date(item.source.published_at)}</p>)}</Disclosure>}
      {!review && data.articles.length > 0 && <><h4>Fetched research</h4><p id="trend-version-notice" className="feedback" role="status">This server response does not include article assessments. Restart the app server to load the updated feature, then refresh this page.</p>{data.articles.map(article => <p key={article.article_id}><ExternalLink url={article.source_url}>{article.title}</ExternalLink> · {article.publisher} · Published {date(article.published_at)} · Fetched {timestamp(article.fetched_at)}</p>)}</>}
      {!data.articles.length && <EmptyState compact symbol="book" title="No fetched articles available">Refresh the configured research feeds to retrieve dated sources.</EmptyState>}
      <Disclosure title="Source health & scope"><div id="trend-feed-health">{data.refresh.feeds.map(feed => <p key={feed.feed_id}><ExternalLink url={feed.url}>{feed.publisher}</ExternalLink> · {feed.status === 'ok' ? `${feed.article_count} articles from the last fetch` : 'Refresh failed; available cached articles retained'} · {timestamp(feed.fetched_at || feed.attempted_at)}</p>)}</div><p>{data.scope} These sources do not measure Malaysian vacancy growth. Trend interpretations do not change your personal fit score.</p><p>Last interpretation: {timestamp(data.analyzed_at)}{data.analysis_provider ? ` · ${data.analysis_provider}` : ''}.</p></Disclosure>
    </>}
  </section>;
}
