import { useEffect, useRef, useState } from 'react';
import { request } from '../api';
import type { Skill, RoleSummary } from '../types';
import { Icon } from './ui';

type SearchRow = Skill | RoleSummary;
export default function Search<T extends SearchRow>({ id, endpoint, resultKey, placeholder, disabled, onSelect, onError }: {
  id: string; endpoint: string; resultKey: 'skills' | 'roles'; placeholder: string; disabled: boolean;
  onSelect: (row: T) => void; onError: (message: string) => void;
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<T[]>([]);
  const [searched, setSearched] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const input = useRef<HTMLInputElement>(null);
  const outputId = id === 'skill-search' ? 'skill-results' : 'target-results';
  const expanded = open && query.trim().length >= 2 && !disabled;
  useEffect(() => {
    let cancelled = false;
    setResults([]); setSearched(false); setActive(-1);
    if (query.trim().length < 2) return;
    const timer = window.setTimeout(async () => {
      try {
        const response = await request<Record<string, T[]>>(`${endpoint}?q=${encodeURIComponent(query.trim())}`, null);
        if (!cancelled) { setResults(response[resultKey]); setSearched(true); }
      } catch (error) {
        if (!cancelled) { setOpen(false); onError(error instanceof Error ? error.message : 'Search is unavailable. Try again.'); }
      }
    }, 250);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [query, endpoint, resultKey, onError]);
  useEffect(() => {
    if (expanded && active >= 0) document.getElementById(`${outputId}-${active}`)?.scrollIntoView({ block: 'nearest' });
  }, [active, expanded, outputId]);
  function choose(row: T) {
    if (disabled) return;
    onSelect(row); setQuery(''); setResults([]); setSearched(false); setActive(-1); setOpen(false);
    input.current?.focus({ preventScroll: true });
  }
  return <div className="autocomplete" onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
    <div className="search-field"><Icon name="search" /><input ref={input} id={id} type="search" role="combobox" aria-autocomplete="list" aria-expanded={expanded} aria-controls={outputId} aria-activedescendant={expanded && active >= 0 ? `${outputId}-${active}` : undefined} placeholder={placeholder} maxLength={100} autoComplete="off" disabled={disabled} value={query}
      onFocus={() => setOpen(true)} onChange={event => { setQuery(event.target.value); setOpen(true); setActive(-1); }}
      onKeyDown={event => {
        if (event.key === 'Escape') { event.preventDefault(); setOpen(false); setActive(-1); }
        if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && results.length) {
          event.preventDefault(); setOpen(true);
          setActive(index => event.key === 'ArrowDown' ? (index + 1) % results.length : (index <= 0 ? results.length - 1 : index - 1));
        }
        if (event.key === 'Enter' && expanded && active >= 0 && results[active]) { event.preventDefault(); choose(results[active]); }
      }} />
      {query && <button type="button" className="search-clear" aria-label="Clear search" disabled={disabled} onClick={() => { setQuery(''); setResults([]); setOpen(false); input.current?.focus(); }}><Icon name="close" /></button>}
    </div>
    <div id={outputId} className="search-results" role="listbox" aria-label={resultKey === 'skills' ? 'Suggested skills' : 'Suggested occupations'} hidden={!expanded}>
      {results.map((row, index) => <button type="button" role="option" id={`${outputId}-${index}`} aria-selected={active === index} tabIndex={-1} key={'skill_id' in row ? row.skill_id : row.role_id} disabled={disabled} onMouseDown={event => event.preventDefault()} onMouseMove={() => setActive(index)} onClick={() => choose(row)}>{'label' in row ? row.label : row.role_title}</button>)}
      {!results.length && <div className="search-empty" role="status">{searched ? 'No matches. Try another name.' : 'Searching...'}</div>}
    </div>
  </div>;
}
