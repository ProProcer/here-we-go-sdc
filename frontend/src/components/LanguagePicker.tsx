import { setLanguage, t, useLanguage, type Language } from '../i18n';
import Select from './Select';

export default function LanguagePicker() {
  const language = useLanguage();
  return <div className="language-picker"><label className="sr-only" htmlFor="language-select">{t('Language')}</label>
    <span aria-hidden="true" className="language-symbol">文 / A</span>
    <Select id="language-select" label={t('Language')} value={language} onChange={value => setLanguage(value as Language)} options={[
      { value: 'en', label: 'English' }, { value: 'ms', label: 'Bahasa Melayu' }, { value: 'zh', label: '中文（普通话）' },
    ]} />
  </div>;
}
