import { t } from '../i18n';
import { useEffect, useRef, useState } from 'react';
import { Icon } from './ui';

interface Option { value: string; label: string }
export default function Select({ id, label, value, options, disabled = false, onChange }: {
  id: string; label: string; value: string; options: readonly Option[];
  disabled?: boolean; onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [upward, setUpward] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const typed = useRef({ text: '', time: 0 });
  const selected = options.findIndex(option => option.value === value);
  const expanded = open && !disabled;
  function show() {
    const bounds = trigger.current?.getBoundingClientRect();
    setUpward(!!bounds && innerHeight - bounds.bottom < 260 && bounds.top > innerHeight - bounds.bottom);
    setActive(Math.max(0, selected)); setOpen(true);
  }
  function choose(index: number) {
    if (disabled || !options[index]) return;
    onChange(options[index].value); setOpen(false); trigger.current?.focus({ preventScroll: true });
  }
  useEffect(() => {
    if (!expanded) return;
    const outside = (event: PointerEvent) => { if (!container.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [expanded]);
  useEffect(() => {
    if (expanded) document.getElementById(`${id}-option-${active}`)?.scrollIntoView({ block: 'nearest' });
  }, [expanded, active, id]);
  return <div ref={container} className={`custom-select ${upward ? 'opens-up' : ''}`} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
    <button ref={trigger} id={id} type="button" role="combobox" className="select-trigger" aria-label={t(label)} aria-haspopup="listbox" aria-expanded={expanded} aria-controls={`${id}-options`} aria-activedescendant={expanded ? `${id}-option-${active}` : undefined} disabled={disabled} onClick={() => expanded ? setOpen(false) : show()} onKeyDown={event => {
      if (event.key === 'Escape' && expanded) { event.preventDefault(); event.stopPropagation(); setOpen(false); }
      if (event.key === 'Tab') setOpen(false);
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        if (!expanded) show();
        else setActive(index => (index + (event.key === 'ArrowDown' ? 1 : options.length - 1)) % options.length);
      }
      if (expanded && (event.key === 'Home' || event.key === 'End')) { event.preventDefault(); setActive(event.key === 'Home' ? 0 : options.length - 1); }
      if (expanded && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); choose(active); }
      if (event.key.length === 1 && event.key !== ' ' && !event.ctrlKey && !event.metaKey && !event.altKey) {
        event.preventDefault();
        const now = Date.now();
        typed.current = { text: (now - typed.current.time < 700 ? typed.current.text : '') + event.key.toLowerCase(), time: now };
        const index = options.findIndex(option => t(option.label).toLowerCase().startsWith(typed.current.text));
        if (!expanded) show();
        if (index >= 0) setActive(index);
      }
    }}><span>{t(options[selected]?.label || 'Choose an option')}</span><Icon name="chevron" /></button>
    <div id={`${id}-options`} className="select-options" role="listbox" aria-label={t(label)} hidden={!expanded}>{options.map((option, index) => <button type="button" role="option" id={`${id}-option-${index}`} key={option.value} tabIndex={-1} aria-selected={option.value === value} className={active === index ? 'active' : ''} onMouseDown={event => event.preventDefault()} onMouseMove={() => setActive(index)} onClick={() => choose(index)}><span>{t(option.label)}</span>{option.value === value && <Icon name="check" />}</button>)}</div>
  </div>;
}
