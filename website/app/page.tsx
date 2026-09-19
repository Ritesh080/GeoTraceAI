'use client';

import { useState, useRef } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { ArrowDown, ArrowUpRight, ArrowRight, Crosshair, Fingerprint, ScanLine, ShieldCheck, Layers, FileText, Check, Maximize2, Github } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { LiveAnalyzer } from '@/components/live-analyzer';

const views = ['Location hypothesis', 'Forensic signals', 'Report preview'] as const;
export default function Home() {
  const [view, setView] = useState(0);
  const reduced = useReducedMotion();
  const panel = useRef<HTMLElement>(null);
  function explore() { setView(0); panel.current?.scrollIntoView({behavior: reduced ? 'instant' : 'smooth', block: 'center'}); document.getElementById('view-0')?.focus({preventScroll: true}); }
  return <>
    <a className="skip" href="#main">Skip to content</a>
    <header className="header shell">
      <a href="/" className="brand" aria-label="GeoTrace AI home"><Crosshair size={30}/><span>GeoTrace<span className="brand-ai">AI</span></span></a>
      <nav aria-label="Main navigation"><a href="https://github.com/Ritesh080/GeoTraceAI/blob/main/CYBER_PIPELINE.md" target="_blank" rel="noreferrer">The architecture <ArrowUpRight size={14}/></a><a href="https://github.com/Ritesh080/GeoTraceAI" target="_blank" rel="noreferrer" className="repo-link"><Github size={17}/> GitHub</a></nav>
      <Button variant="outline" onClick={explore}>Explore the preview <ArrowUpRight size={16}/></Button>
    </header>
    <main id="main" className="shell">
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <div className="eyebrow"><span className="eyebrow-line"/> IMAGE INTELLIGENCE. EVIDENCE FIRST.</div>
          <h1 id="hero-title">Trace what<br/>images <span>don’t say.</span></h1>
          <p className="intro">Every image holds a story beyond the frame. Explore its probable location, examine its digital traces, and follow the evidence behind every finding.</p>
          <div className="actions"><Button onClick={explore}>See it in action <ArrowRight size={18}/></Button><a className="text-link" href="https://github.com/Ritesh080/GeoTraceAI/blob/main/CYBER_PIPELINE.md" target="_blank" rel="noreferrer">Explore the methodology <ArrowUpRight size={15}/></a></div>
          <div className="hero-note"><Fingerprint size={17}/><span>Built around integrity. Designed for investigation.</span></div>
        </div>
        <motion.section ref={panel} className="console" aria-label="Interactive product concept" initial={reduced ? false : {opacity:0, y:16}} animate={{opacity:1,y:0}} transition={{duration:0.65, ease:'easeOut'}}>
          <div className="console-top"><span><Crosshair size={16}/> INVESTIGATION WORKSPACE</span><span className="concept-label">CONCEPT PREVIEW</span></div>
          <div className="case-heading"><div><span className="micro">SAMPLE CASE / GT–001</span><h2>A location is a hypothesis.<br/>Evidence makes it stronger.</h2></div><span className="case-icon"><Layers size={22}/></span></div>
          <div className="tabs" role="tablist" aria-label="Evidence views">{views.map((label,i)=><button key={label} id={`view-${i}`} type="button" role="tab" aria-controls="evidence-panel" aria-selected={view===i} tabIndex={view===i?0:-1} onKeyDown={e=>{ if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault(); const next=e.key==='Home'?0:e.key==='End'?2:(view+(e.key==='ArrowRight'?1:2))%3;setView(next);document.getElementById(`view-${next}`)?.focus();}}} onClick={()=>setView(i)}>{label}</button>)}</div>
          <div role="tabpanel" id="evidence-panel" aria-labelledby={`view-${view}`} tabIndex={0} className="evidence-panel">
            {view===0 ? <div className="map-view">
              <svg className="evidence-map" viewBox="0 0 600 320" role="img" aria-label="Illustrative coordinate grid showing three evidence signals converging on a candidate location; not a real map">
                <defs><pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="#26354d" strokeWidth=".7"/></pattern></defs>
                <rect width="600" height="320" fill="#101c2f"/><rect width="600" height="320" fill="url(#grid)"/>
                <g fill="none" stroke="#344760" strokeWidth="1"><path d="M0 260L90 200 130 230 210 180 250 110 360 130 420 50 510 80 600 0M0 285L90 225 130 255 225 200 270 145 375 160 445 90 515 110 600 40M0 300L95 255 140 280 235 230 280 175 390 190 465 130 540 140 600 90"/><path d="M50 0L110 80 230 100 295 70 400 90 490 10M70 0L130 55 235 75 290 40 390 65 460 0"/></g>
                <g stroke="#5683b3" fill="none"><circle cx="320" cy="169" r="106" strokeDasharray="3 7" opacity=".6"/><circle cx="320" cy="169" r="67" opacity=".5"/><path d="M190 102L320 169 453 108M320 169L372 255" strokeDasharray="4 5"/></g>
                <path d="M190 102L453 108 372 255Z" stroke="#70aafb" fill="#3b82f6" fillOpacity=".06" strokeOpacity=".3"/>
                <g fill="#9db6d3" stroke="#101c2f" strokeWidth="4"><circle cx="190" cy="102" r="6"/><circle cx="453" cy="108" r="6"/><circle cx="372" cy="255" r="6"/></g>
                <g fill="#93a7c0" fontSize="11" fontFamily="Inter Variable, sans-serif"><text x="138" y="83">VISUAL CLUES</text><text x="434" y="88">EXIF GPS</text><text x="389" y="272">OCR CONTEXT</text></g>
                <circle cx="320" cy="169" r="18" fill="#3b82f6" fillOpacity=".2"/><circle cx="320" cy="169" r="7" fill="#60a5fa" stroke="#dbeafe" strokeWidth="2"/><path d="M320 137v10m0 44v10m-32-32h10m44 0h10" stroke="#60a5fa"/>
              </svg>
              <div className="map-caption"><span><Crosshair size={13}/> EVIDENCE CONVERGENCE</span><Maximize2 size={14}/></div>
              <div className="location-result"><span className="location-icon"><Crosshair size={19}/></span><div><span className="micro">ILLUSTRATIVE CANDIDATE</span><strong>New Delhi, India</strong></div><span className="review-label">Needs review</span></div>
            </div> : view===1 ? <div className="signals"><div className="signal-intro"><ShieldCheck size={23}/><p>Indicators inform a finding.<br/><strong>They are never a verdict.</strong></p></div>{[['File integrity','SHA-256 fingerprint','Preserved'],['Metadata','GPS and timestamp checks','Cross-check'],['Image forensics','ELA and noise consistency','Review'],['Reliability','Explainable weighted indicators','Scored']].map(([name,desc,status])=><div className="signal" key={name}><div><strong>{name}</strong><span>{desc}</span></div><span>{status}</span></div>)}</div> : <div className="report"><FileText size={30}/><span className="micro">INVESTIGATION REPORT / CONCEPT</span><h3>Follow the finding.<br/>Keep the evidence.</h3><p>A proposed report brings the location hypothesis, forensic indicators, and conflicting signals into one reviewable record.</p><div><Check size={16}/> Source integrity and provenance</div><div><Check size={16}/> Reasoning and uncertainty</div><div><Check size={16}/> Evidence requiring analyst review</div></div>}
          </div>
          <div className="console-footer"><span><ShieldCheck size={14}/> Original evidence preserved</span><span>Illustrative data</span></div>
        </motion.section>
      </section>
      <div className="hero-bottom"><div><span className="micro">TWO PERSPECTIVES. ONE INVESTIGATION.</span><p>Visual reasoning <span>+</span> Digital forensics</p></div><div className="bottom-note"><ScanLine size={20}/><span>Look beyond the pixels.<br/>Stay grounded in the evidence.</span></div><button className="down" onClick={explore} aria-label="Explore the product preview"><ArrowDown size={20}/></button></div>
      <LiveAnalyzer/>
    </main>
  </>;
}
