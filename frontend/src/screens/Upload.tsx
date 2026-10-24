import { t } from '../i18n';
import { useState } from 'react';
import { apiUrl } from '../api';
import { Disclosure, Icon } from '../components/ui';

export default function Upload({ pending, uploadedFileName, onReview, onUpload, onSample, onManual }: {
  pending: boolean; uploadedFileName: string | null; onReview: () => void;
  onUpload: (file: File) => void; onSample: () => void; onManual: () => void;
}) {
  const [dragging, setDragging] = useState(false);
  return <section id="intake" className="screen intake-screen">
    <span className="eyebrow">{t("A WORLD OF POSSIBILITIES, STARTING WITH YOU")}</span>
    <h1>{t("Your career journey")}<br /><span>{t("starts here.")}</span></h1>
    <p className="page-intro">{t("Upload your CV to discover your skills and career matches.")}</p>
    <label className={`drop-zone ${uploadedFileName ? 'upload-complete' : ''} ${dragging ? 'dragging' : ''}`} id="drop-zone" htmlFor="cv-file"
      onDragOver={event => { event.preventDefault(); if (!pending) setDragging(true); }}
      onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }}
      onDrop={event => { event.preventDefault(); setDragging(false); if (!pending && event.dataTransfer.files[0]) onUpload(event.dataTransfer.files[0]); }}>
      <span className="upload-art" aria-hidden="true"><span className="paper paper-back" /><span className="paper paper-front"><Icon name="upload" /><span /><span /></span><span className="upload-art-check"><Icon name="check" /></span></span>
      {uploadedFileName ? <>
        <span className="upload-success-label" role="status">{t("Uploaded successfully")}</span>
        <strong className="uploaded-filename">{t(uploadedFileName)}</strong>
        <span className="replace-cv-prompt">{t("Want to try a different CV?")}</span>
        <span className="button secondary upload-browse">{t("Upload another CV ")}<Icon name="upload" /></span>
      </> : <>
        <strong>{t("Drop your CV here")}</strong><span className="drop-hint">{t("or choose a file to get started")}</span>
        <span className="button primary upload-browse">{t("Upload CV ")}<Icon name="arrow" /></span>
      </>}
      <small>{t("PDF, DOCX, TXT, JPG or PNG · up to 2 MB")}</small>
      <input id="cv-file" type="file" accept=".pdf,.docx,.txt,.jpg,.jpeg,.png" aria-label={t("Upload a fictional CV")} disabled={pending} onChange={event => {
        const file = event.target.files?.[0]; if (file) onUpload(file); event.target.value = '';
      }} />
    </label>
    {uploadedFileName ? <div className="upload-success-actions"><button id="review-upload" className="button primary" disabled={pending} onClick={onReview}>{t("Review my skills ")}<Icon name="arrow" /></button></div> : <div className="upload-actions"><span>{t("Just taking a look?")}</span><button id="sample" className="text-button" disabled={pending} onClick={onSample}>{t("Try a sample CV ")}<span aria-hidden="true">↗</span></button><a href={apiUrl('/samples/graduate.pdf')}>{t("Download sample")}</a></div>}
    <Disclosure help title={t("Privacy & upload help")} className="upload-help"><p>{t("Use a fictional CV for this demo. Uploaded files are discarded after processing; extracted profiles expire after one hour. When AI assessment is enabled, extracted skill passages are sent to the AI service to estimate levels. Review those estimates before confirming.")}</p><p>{t("PDFs can have up to five pages. Scans use local OCR. You can correct any missed or mistaken skills.")}</p><button id="manual-fallback" className="text-button" disabled={pending} onClick={onManual}>{t("Enter skills manually instead ↗")}</button></Disclosure>
    <div className="journey-preview" aria-label={t("Your next steps")}><span><b>1</b>{t("Upload your CV")}</span><i /><span><b>2</b>{t("Make it yours")}</span><i /><span><b>3</b>{t("Explore your future")}</span></div>
  </section>;
}
