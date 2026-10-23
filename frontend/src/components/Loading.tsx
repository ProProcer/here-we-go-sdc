import { useEffect, useState } from 'react';

const messages = [
  'Connecting your career dots...', 'Giving your CV a little detective work...',
  'Looking for your hidden superpowers...', 'Putting your skills in the spotlight...',
  'Your next chapter is warming up...', 'Polishing the career crystal ball...',
  'Taking your experience for a spin...', 'Asking your CV for its origin story...',
];
const pick = (except: number) => (except + 1 + Math.floor(Math.random() * (messages.length - 1))) % messages.length;
function UploadReel() {
  const [reel, setReel] = useState(() => {
    const current = Math.floor(Math.random() * messages.length);
    return { current, next: pick(current), turn: 0 };
  });
  useEffect(() => {
    const timer = window.setInterval(() => setReel(old => ({ current: old.next, next: pick(old.next), turn: old.turn + 1 })), 1600);
    return () => window.clearInterval(timer);
  }, []);
  return <div id="upload-reel" className="upload-reel min-w-0 flex-1 overflow-hidden" aria-hidden="true"><div id="upload-reel-track" key={reel.turn} className="reel-track"><span>{messages[reel.current]}</span><span>{messages[reel.next]}</span></div></div>;
}
export default function Loading({ label, upload }: { label: string; upload: boolean }) {
  return <div id="busy" className="processing" role="status" aria-live="polite">
    <svg className="spinner" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /></svg>
    <strong id="busy-label" className={upload ? 'sr-only' : ''}>{label}</strong>
    {upload && <UploadReel />}
  </div>;
}
