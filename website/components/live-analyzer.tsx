'use client';

import axios from 'axios';
import exifr from 'exifr';
import { useCallback, useEffect, useState } from 'react';
import { useDropzone, type FileRejection } from 'react-dropzone';
import { AlertTriangle, Check, ExternalLink, FileImage, Globe2, LoaderCircle, Network, RefreshCw, ShieldCheck, UploadCloud } from 'lucide-react';
import { Button } from '@/components/ui/button';

type AnalysisResult = {
  status: 'success';
  sha256: string;
  file: { valid: boolean; mime_type: string; extension: string };
  metadata: {
    gps_present?: boolean;
    latitude?: number | null;
    longitude?: number | null;
    coordinates_valid?: boolean;
    camera?: string | null;
    model?: string | null;
    datetime_original?: string | null;
    software?: string | null;
    gps_checked?: boolean;
    ocr_text?: string | null;
    ocr_confidence?: number | null;
    language_hint?: string | null;
  };
  image_forensics?: { structure?: { width?: number; height?: number; megapixels?: number } };
  forensics: {
    reliability_score: number | null;
    reliability_level: string;
    tampering_suspected: boolean;
    indicators: string[];
  };
  osint: {
    status: string;
    privacy: { automatic_external_upload: boolean; note: string };
    clues: Array<{ id: string; kind: string; label: string; value: string; source_group: string }>;
    actions: Array<{ id: string; label: string; provider: string; url: string; sends_image: boolean }>;
    dependency_groups: Array<{ id: string; label: string; member_ids: string[]; explanation: string }>;
    conflicts: Array<{ id?: string; summary?: string }>;
    uncertainty: { outcome: string; confidence: number | null; calibrated: boolean; abstention_reasons: string[] };
    candidates?: Array<{ id: string; label: string; latitude: number; longitude: number; basis: string; needs_corroboration: boolean }>;
    provider_status?: Array<{ capability: string; status: string }>;
  };
};

const CONFIGURED_API_URL = (process.env.NEXT_PUBLIC_GEOTRACE_API_URL || '').replace(/\/$/, '');

function resolveApiUrl() {
  if (CONFIGURED_API_URL) return CONFIGURED_API_URL;
  if (typeof window !== 'undefined' && ['localhost', '127.0.0.1'].includes(window.location.hostname)) {
    return 'http://127.0.0.1:8000';
  }
  return '';
}

function readableError(error: unknown) {
  if (axios.isAxiosError(error)) {
    if (!error.response) return 'The analysis service is offline. Start the GitHub backend service and try again.';
    return error.response.data?.detail || 'The image could not be analyzed.';
  }
  return 'The image could not be analyzed.';
}

function hexDigest(buffer: ArrayBuffer) {
  return Array.from(new Uint8Array(buffer), byte => byte.toString(16).padStart(2, '0')).join('');
}

function detectWritingSystem(text: string) {
  const scripts = [
    { label: 'Devanagari script', pattern: /[\u0900-\u097F]/g },
    { label: 'Arabic script', pattern: /[\u0600-\u06FF]/g },
    { label: 'Cyrillic script', pattern: /[\u0400-\u04FF]/g },
    { label: 'CJK characters', pattern: /[\u3040-\u30FF\u3400-\u9FFF]/g },
    { label: 'Latin script', pattern: /[A-Za-z]/g },
  ];
  const ranked = scripts.map(script => ({ label: script.label, count: text.match(script.pattern)?.length ?? 0 })).sort((a, b) => b.count - a.count);
  return ranked[0].count ? ranked[0].label : null;
}

async function extractOcr(file: File, onProgress: (message: string) => void) {
  onProgress('Loading OCR model');
  const { createWorker } = await import('tesseract.js');
  const worker = await createWorker('eng', 1, {
    logger: event => {
      if (event.status === 'recognizing text') onProgress(`Reading visible text · ${Math.round((event.progress || 0) * 100)}%`);
    },
  });
  try {
    const { data } = await worker.recognize(file);
    const text = data.text.replace(/\s+/g, ' ').trim().slice(0, 500);
    return { text, confidence: Math.round(data.confidence), languageHint: detectWritingSystem(text) };
  } finally {
    await worker.terminate();
  }
}

function browserOsint(sha256: string, metadata: AnalysisResult['metadata']): AnalysisResult['osint'] {
  const hasGps = metadata.gps_present && metadata.coordinates_valid && metadata.latitude != null && metadata.longitude != null;
  const candidates = hasGps ? [{
    id: 'embedded_gps',
    label: `${metadata.latitude}, ${metadata.longitude}`,
    latitude: metadata.latitude as number,
    longitude: metadata.longitude as number,
    basis: 'Embedded EXIF GPS coordinates',
    needs_corroboration: true,
  }] : [];
  const clues = [{ id: 'asset_sha256', kind: 'asset_fingerprint', label: 'Exact file fingerprint', value: sha256, source_group: 'submitted_asset' }];
  if (hasGps) clues.push({ id: 'embedded_gps', kind: 'geographic_reference', label: 'Embedded GPS coordinates', value: candidates[0].label, source_group: 'submitted_asset' });
  if (metadata.ocr_text) clues.push({ id: 'ocr_text', kind: 'visual_text', label: 'Visible text', value: metadata.ocr_text, source_group: 'submitted_asset' });
  const actions = [
    { id: 'hash_search', label: 'Search the exact SHA-256 fingerprint', provider: 'Google Search', url: `https://www.google.com/search?q=%22${encodeURIComponent(sha256)}%22`, sends_image: false },
    { id: 'lens_review', label: 'Run a visual-match search manually', provider: 'Google Lens', url: 'https://lens.google.com/', sends_image: true },
    { id: 'tineye_review', label: 'Check publication and repost history', provider: 'TinEye', url: 'https://tineye.com/', sends_image: true },
  ];
  if (hasGps) {
    actions.push(
      { id: 'osm_map_check', label: 'Inspect the coordinate context', provider: 'OpenStreetMap', url: `https://www.openstreetmap.org/?mlat=${metadata.latitude}&mlon=${metadata.longitude}#map=16/${metadata.latitude}/${metadata.longitude}`, sends_image: false },
      { id: 'google_maps_check', label: 'Cross-check nearby landmarks', provider: 'Google Maps', url: `https://www.google.com/maps/search/?api=1&query=${metadata.latitude}%2C${metadata.longitude}`, sends_image: false },
    );
  }
  if (metadata.ocr_text) actions.push({ id: 'ocr_search', label: 'Search recognized text for geographic context', provider: 'Text search', url: `https://www.google.com/search?q=${encodeURIComponent(metadata.ocr_text.slice(0, 160))}`, sends_image: false });
  const outcome = hasGps ? 'candidate_needs_corroboration' : 'insufficient_evidence';
  return {
    status: 'ready_for_review',
    privacy: {
      automatic_external_upload: false,
      note: 'The image stayed in this browser. GeoTrace AI did not upload it to an OSINT provider.',
    },
    clues,
    actions,
    dependency_groups: [{ id: 'submitted_asset', label: 'Submitted image', member_ids: clues.map(clue => clue.id), explanation: 'File, EXIF, and OCR clues share one image origin and count as one source group.' }],
    conflicts: [],
    uncertainty: {
      outcome,
      confidence: null,
      calibrated: false,
      abstention_reasons: ['No independent web source has been collected yet.', hasGps ? 'Embedded GPS requires external corroboration.' : 'No valid embedded GPS coordinate was found.', 'Landmark recognition requires a configured vision provider.'],
    },
    candidates,
    provider_status: [
      { capability: 'EXIF/GPS', status: 'active_in_browser' },
      { capability: 'OCR', status: 'active_in_browser' },
      { capability: 'Landmark recognition', status: 'provider_required' },
      { capability: 'Reverse-image search', status: 'manual_review' },
    ],
  };
}

async function analyzeInBrowser(file: File, onProgress: (message: string) => void): Promise<AnalysisResult> {
  onProgress('Reading file evidence');
  const bytes = await file.arrayBuffer();
  const sha256 = hexDigest(await crypto.subtle.digest('SHA-256', bytes));
  const bitmap = await createImageBitmap(file);
  const width = bitmap.width;
  const height = bitmap.height;
  bitmap.close();
  const extension = file.name.includes('.') ? `.${file.name.split('.').pop()?.toLowerCase()}` : '';
  onProgress('Extracting EXIF and GPS');
  const [exifResult, gpsResult, ocrResult] = await Promise.allSettled([
    exifr.parse(file, { tiff: true, exif: true }),
    exifr.gps(file),
    extractOcr(file, onProgress),
  ]);
  const exif = exifResult.status === 'fulfilled' && exifResult.value ? exifResult.value as Record<string, unknown> : {};
  const gps = gpsResult.status === 'fulfilled' && gpsResult.value ? gpsResult.value : null;
  const ocr = ocrResult.status === 'fulfilled' ? ocrResult.value : { text: '', confidence: 0, languageHint: null };
  const latitude = typeof gps?.latitude === 'number' ? gps.latitude : null;
  const longitude = typeof gps?.longitude === 'number' ? gps.longitude : null;
  const coordinatesValid = latitude !== null && longitude !== null && Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180;
  const metadata: AnalysisResult['metadata'] = {
    gps_checked: true,
    gps_present: coordinatesValid,
    latitude,
    longitude,
    coordinates_valid: coordinatesValid,
    camera: typeof exif.Make === 'string' ? exif.Make : null,
    model: typeof exif.Model === 'string' ? exif.Model : null,
    datetime_original: exif.DateTimeOriginal instanceof Date ? exif.DateTimeOriginal.toISOString() : null,
    software: typeof exif.Software === 'string' ? exif.Software : null,
    ocr_text: ocr.text || null,
    ocr_confidence: ocr.text ? ocr.confidence : null,
    language_hint: ocr.languageHint,
  };

  const result: AnalysisResult = {
    status: 'success',
    sha256,
    file: { valid: true, mime_type: file.type || 'application/octet-stream', extension },
    metadata,
    image_forensics: { structure: { width, height, megapixels: Number(((width * height) / 1_000_000).toFixed(2)) } },
    forensics: { reliability_score: null, reliability_level: 'unavailable', tampering_suspected: false, indicators: ['browser_analysis_only'] },
    osint: browserOsint(sha256, metadata),
  };
  onProgress('Evidence ready');
  return result;
}

export function LiveAnalyzer() {
  const [apiUrl] = useState<string>(() => resolveApiUrl());
  const [service, setService] = useState<'checking' | 'ready' | 'browser' | 'offline'>('checking');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [analysisStage, setAnalysisStage] = useState('Analyzing');

  const checkService = useCallback(async () => {
    if (!apiUrl) {
      setService('browser');
      return;
    }
    setService('checking');
    try {
      await axios.get(`${apiUrl}/health`, { timeout: 3000 });
      setService('ready');
    } catch {
      setService('offline');
    }
  }, [apiUrl]);

  useEffect(() => { void checkService(); }, [checkService]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const onDrop = useCallback((accepted: File[], rejected: FileRejection[]) => {
    setResult(null);
    setError(null);
    if (!accepted[0]) {
      setError(rejected[0]?.errors[0]?.message || 'Choose a JPG, PNG, or WebP image under 20 MB.');
      return;
    }
    setFile(accepted[0]);
    setPreview(URL.createObjectURL(accepted[0]));
  }, []);

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: { 'image/jpeg': ['.jpg', '.jpeg'], 'image/png': ['.png'], 'image/webp': ['.webp'] },
    maxFiles: 1,
    maxSize: 20 * 1024 * 1024,
    noClick: true,
  });

  async function runAnalysis() {
    if (!file || running) return;
    setRunning(true);
    setAnalysisStage('Analyzing');
    setError(null);
    setResult(null);
    try {
      if (apiUrl) {
        const form = new FormData();
        form.append('file', file);
        const response = await axios.post<AnalysisResult>(`${apiUrl}/analyze`, form, { timeout: 120000 });
        setResult(response.data);
        setService('ready');
      } else {
        setResult(await analyzeInBrowser(file, setAnalysisStage));
        setService('browser');
      }
    } catch (requestError) {
      setError(readableError(requestError));
      if (axios.isAxiosError(requestError) && !requestError.response) setService('offline');
    } finally {
      setRunning(false);
    }
  }

  const score = result && result.forensics.reliability_score !== null ? Math.round(result.forensics.reliability_score * 100) : null;
  return <section id="live-analysis" className="analysis-section" aria-labelledby="analysis-title">
    <div className="analysis-heading">
      <div><span className="micro">CONNECTED INVESTIGATION</span><h2 id="analysis-title">Analyze the evidence,<br/>from the original bytes.</h2></div>
      <div className={`service-state ${service}`} role="status">
        <span aria-hidden="true"/>{service === 'ready' ? 'GitHub backend ready' : service === 'browser' ? 'Private browser analysis ready' : service === 'checking' ? 'Checking backend' : 'Backend offline'}
        {service === 'offline' && apiUrl && <button type="button" onClick={checkService} aria-label="Check backend again"><RefreshCw size={14}/></button>}
      </div>
    </div>

    <div className="analysis-grid">
      <div {...getRootProps({ className: `drop-area ${isDragActive ? 'dragging' : ''}` })}>
        <input {...getInputProps()} aria-label="Choose an image for forensic analysis"/>
        {preview ? <div className="selected-file">
          {/* Object URLs render only the user-selected local image and are released on change/unmount. */}
          <img src={preview} alt="Selected evidence preview"/>
          <div><FileImage size={18}/><span><strong>{file?.name}</strong><small>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : ''}</small></span></div>
        </div> : <div className="drop-copy"><UploadCloud size={32}/><h3>{isDragActive ? 'Release to inspect' : 'Select an evidence image'}</h3><p>JPG, PNG, or WebP · maximum 20 MB</p></div>}
        <div className="drop-actions">
          <Button variant="outline" type="button" onClick={open}>{file ? 'Choose another' : 'Choose image'}</Button>
          <Button type="button" onClick={runAnalysis} disabled={!file || running || !['ready', 'browser'].includes(service)}>{running ? <><LoaderCircle className="spin" size={18}/> {analysisStage}</> : service === 'browser' ? 'Analyze in browser' : 'Run forensic analysis'}</Button>
        </div>
      </div>

      <div className="analysis-output" aria-live="polite">
        {!result && !error && <div className="output-empty"><ShieldCheck size={30}/><h3>{apiUrl ? 'Evidence remains local until analysis starts.' : 'Explore the investigation workflow.'}</h3><p>{apiUrl ? 'The API validates the file, computes its SHA-256 fingerprint, extracts metadata, checks image signals, and deletes the temporary upload.' : 'Browser analysis now extracts EXIF/GPS, reads visible text, and prepares OSINT verification without uploading the image. Landmark recognition and full forensic scoring require a hosted provider.'}</p>{!apiUrl && <div className="osint-preview" aria-label="Connected OSINT workflow"><span><b>01</b> EXIF, GPS, and OCR extraction</span><span><b>02</b> Map and reverse-image verification</span><span><b>03</b> Source-dependency grouping</span><span><b>04</b> Candidate and uncertainty gate</span></div>}</div>}
        {error && <div className="output-error" role="alert"><AlertTriangle size={24}/><div><h3>Analysis unavailable</h3><p>{error}</p></div></div>}
        {result && <div className="result-view">
          <div className="result-top"><div><span className="micro">FORENSIC RELIABILITY</span><strong>{score ?? '—'}<small>/100</small></strong></div><span className={`result-level ${result.forensics.reliability_level}`}>{result.forensics.reliability_level.replace('_', ' ')}</span></div>
          <div className="score-track" aria-label={score === null ? 'Forensic reliability requires the server analysis pipeline' : `Forensic reliability ${score} out of 100`} role={score === null ? undefined : 'progressbar'} aria-valuemin={score === null ? undefined : 0} aria-valuemax={score === null ? undefined : 100} aria-valuenow={score ?? undefined}><span style={{width:`${score ?? 0}%`}}/></div>
          <dl className="result-facts">
            <div><dt>File integrity</dt><dd><Check size={14}/> SHA-256 recorded</dd></div>
            <div><dt>Type</dt><dd>{result.file.mime_type}</dd></div>
            <div><dt>Dimensions</dt><dd>{result.image_forensics?.structure?.width ?? '—'} × {result.image_forensics?.structure?.height ?? '—'}</dd></div>
            <div><dt>GPS metadata</dt><dd>{result.metadata.gps_present ? `${result.metadata.latitude}, ${result.metadata.longitude}` : result.metadata.gps_checked ? 'Not present' : 'Not checked'}</dd></div>
          </dl>
          {result.metadata.ocr_text && <div className="ocr-result"><span>VISIBLE TEXT · {result.metadata.language_hint ?? 'Script unresolved'} · {result.metadata.ocr_confidence}% OCR</span><p>{result.metadata.ocr_text}</p></div>}
          <div className="hash-row"><span>SHA-256</span><code>{result.sha256}</code></div>
          <div className="indicator-list"><span>Indicators</span>{result.forensics.indicators.length ? <ul>{result.forensics.indicators.slice(0,4).map(item=><li key={item}>{item.replaceAll('_',' ')}</li>)}</ul> : <p>No configured indicators triggered.</p>}</div>
          <p className="result-note">{score === null ? 'Browser analysis verifies local file facts. A forensic reliability score requires the Python analysis service.' : 'Reliability describes the submitted file’s forensic signals. It is not a location-confidence score or proof of manipulation.'}</p>
          <div className="osint-panel">
            <div className="osint-title"><div><Globe2 size={18}/><span><small>OSINT HANDOFF</small><strong>External verification</strong></span></div><span className="osint-state">Review ready</span></div>
            <p className="osint-privacy">{result.osint.privacy.note}</p>
            {result.osint.candidates?.[0] && <div className="candidate-location"><span>LOCATION CANDIDATE</span><strong>{result.osint.candidates[0].label}</strong><small>{result.osint.candidates[0].basis} · needs corroboration</small></div>}
            <div className="osint-actions">{result.osint.actions.map(action=><a key={action.id} href={action.url} target="_blank" rel="noreferrer"><span><strong>{action.provider}</strong><small>{action.label}</small></span><ExternalLink size={14}/></a>)}</div>
            <div className="dependency-note"><Network size={16}/><div><strong>{result.osint.dependency_groups[0]?.label ?? 'Submitted image'} · one source group</strong><p>{result.osint.dependency_groups[0]?.explanation}</p></div></div>
            <div className="uncertainty-row"><span>Decision</span><strong>{result.osint.uncertainty.outcome.replaceAll('_', ' ')}</strong><small>{result.osint.conflicts.length ? `${result.osint.conflicts.length} conflicts detected` : 'No independent sources collected'}</small></div>
          </div>
        </div>}
      </div>
    </div>
  </section>;
}
