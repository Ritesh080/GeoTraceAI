'use client';

import axios from 'axios';
import exifr from 'exifr';
import { useCallback, useEffect, useState } from 'react';
import { useDropzone, type FileRejection } from 'react-dropzone';
import { AlertTriangle, Check, Database, ExternalLink, FileImage, Fingerprint, Globe2, Instagram, LoaderCircle, MapPin, Network, RefreshCw, ShieldCheck, UploadCloud } from 'lucide-react';
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
  source?: {
    platform: 'instagram';
    source_group: string;
    canonical_url: string;
    shortcode: string;
    owner_username: string;
    published_at: string;
    caption?: string | null;
    media_type: string;
    retrieved_at: string;
    location?: { name: string; latitude?: number | null; longitude?: number | null } | null;
  };
  osint: {
    status: string;
    privacy: { automatic_external_upload: boolean; external_processing?: boolean; external_provider?: string | null; note: string };
    clues: Array<{ id: string; kind: string; label: string; value: string; source_group: string }>;
    actions: Array<{ id: string; label: string; provider: string; url: string; sends_image: boolean }>;
    dependency_groups: Array<{ id: string; label: string; member_ids: string[]; explanation: string }>;
    conflicts: Array<{ id?: string; summary?: string; candidate_ids?: string[]; distance_km?: number }>;
    uncertainty: { outcome: string; confidence: number | null; calibrated: boolean; independent_source_groups?: number; abstention_reasons: string[] };
    candidates?: Array<{
      id: string;
      rank: number;
      label: string;
      latitude?: number | null;
      longitude?: number | null;
      precision_tier: string;
      basis: string;
      provider: string;
      source_group: string;
      confidence: number | null;
      calibrated: boolean;
      calibration_samples?: number;
      retrieval_score?: number;
      supports: Array<{ evidence_id: string; summary: string; source_group: string }>;
      contradictions: Array<{ evidence_id: string; summary: string; source_group: string }>;
      verification_status: string;
      needs_corroboration: boolean;
    }>;
    provider_status?: Array<{ capability: string; status: string; provider?: string | null }>;
    calibration?: {
      status: string;
      calibrated: boolean;
      reason?: string | null;
      model_fingerprint?: string;
      distance_threshold_km?: number;
      query_count?: number;
      overall?: {
        queries: number;
        top1_accuracy: number | null;
        top5_accuracy: number | null;
        median_error_km: number | null;
        p90_error_km: number | null;
      };
      segments?: Record<string, Record<string, {
        queries: number;
        top1_accuracy: number | null;
        top5_accuracy: number | null;
        median_error_km: number | null;
        p90_error_km: number | null;
      }>>;
    } | null;
    map_verification?: {
      status: string;
      mode: string;
      attribution: string;
      records: Array<{
        candidate_id: string;
        status: string;
        place: { name: string; country: string; distance_km: number };
        label_matches: string[];
        ocr_matches: string[];
        map_url: string;
      }>;
    };
    street_imagery_comparison?: {
      status: string;
      mode: string;
      engine: string;
      index_fingerprint: string;
      reference_images: number;
      method_note: string;
      records: Array<{
        candidate_id: string;
        status: string;
        radius_km: number;
        matches: Array<{
          reference_id: string;
          label: string;
          latitude: number;
          longitude: number;
          heading?: number | null;
          distance_km: number;
          similarity: number;
          source_url: string;
          license: string;
          attribution: string;
          captured_at?: string;
        }>;
      }>;
    };
    source_provenance?: {
      status: string;
      engine: string;
      mode: string;
      index_fingerprint: string;
      reference_images: number;
      independent_origin_groups: number;
      method_note: string;
      matches: Array<{
        reference_id: string;
        title: string;
        source_name: string;
        source_url: string;
        published_at: string;
        license: string;
        attribution: string;
        origin_group: string;
        match_type: string;
        perceptual_distance: number;
        perceptual_similarity: number;
        local_feature_matches: number;
        local_feature_ratio: number;
      }>;
      timeline: Array<{
        reference_id: string;
        title: string;
        source_name: string;
        source_url: string;
        published_at: string;
        license: string;
        attribution: string;
        origin_group: string;
        match_type: string;
        perceptual_similarity: number;
        timeline_role: string;
      }>;
    };
  };
};

type CoverageReport = {
  status: 'full_reference_stack' | 'operational_limited_coverage';
  full_reference_coverage: boolean;
  active_datasets: number;
  total_datasets: number;
  datasets: Array<{
    name: string;
    status: 'active' | 'not_built' | 'invalid';
    purpose: string;
    reference_count: number;
    one_degree_cells?: number;
    independent_origin_groups?: number;
    updated_at?: string;
  }>;
  limitations: string[];
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

function openStreetMapEmbedUrl(latitude: number, longitude: number) {
  const latitudeDelta = 0.008;
  const longitudeDelta = 0.012;
  const bounds = [
    longitude - longitudeDelta,
    latitude - latitudeDelta,
    longitude + longitudeDelta,
    latitude + latitudeDelta,
  ].map(value => value.toFixed(6)).join('%2C');
  return `https://www.openstreetmap.org/export/embed.html?bbox=${bounds}&layer=mapnik&marker=${latitude.toFixed(6)}%2C${longitude.toFixed(6)}`;
}

function openStreetMapUrl(latitude: number, longitude: number) {
  return `https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=16/${latitude}/${longitude}`;
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
    rank: 1,
    label: `${metadata.latitude}, ${metadata.longitude}`,
    latitude: metadata.latitude as number,
    longitude: metadata.longitude as number,
    precision_tier: 'exact_coordinate',
    basis: 'Embedded EXIF GPS coordinates',
    provider: 'GeoTrace browser metadata extractor',
    source_group: 'submitted_asset',
    confidence: null,
    calibrated: false,
    supports: [{ evidence_id: 'embedded_gps', summary: 'The submitted file contains valid GPS coordinates.', source_group: 'submitted_asset' }],
    contradictions: [],
    verification_status: 'needs_independent_corroboration',
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
      { capability: 'EXIF/GPS extraction', status: 'active', provider: 'GeoTrace browser' },
      { capability: 'OCR', status: 'active', provider: 'GeoTrace browser' },
      { capability: 'Visual geolocation', status: 'adapter_ready', provider: null },
      { capability: 'Automated map context verification', status: 'backend_required', provider: 'GeoTrace local place index' },
      { capability: 'Street-level imagery comparison', status: 'backend_required', provider: 'GeoTrace Street Compare v0' },
      { capability: 'Reverse-image and source provenance', status: 'backend_required', provider: 'GeoTrace Provenance v0' },
      { capability: 'Calibrated location confidence', status: 'benchmark_required', provider: null },
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
  const [visualProviderActive, setVisualProviderActive] = useState(false);
  const [visualGeolocation, setVisualGeolocation] = useState(false);
  const [mapProviderActive, setMapProviderActive] = useState(false);
  const [mapVerification, setMapVerification] = useState(false);
  const [streetProviderActive, setStreetProviderActive] = useState(false);
  const [streetImageryComparison, setStreetImageryComparison] = useState(false);
  const [provenanceProviderActive, setProvenanceProviderActive] = useState(false);
  const [sourceProvenance, setSourceProvenance] = useState(false);
  const [selectedMapCandidateId, setSelectedMapCandidateId] = useState<string | null>(null);
  const [instagramUrl, setInstagramUrl] = useState('');
  const [instagramConsent, setInstagramConsent] = useState(false);
  const [coverage, setCoverage] = useState<CoverageReport | null>(null);

  const checkService = useCallback(async () => {
    if (!apiUrl) {
      setService('browser');
      return;
    }
    setService('checking');
    try {
      await axios.get(`${apiUrl}/health`, { timeout: 3000 });
      const [capabilityResponse, coverageResponse] = await Promise.all([
        axios.get<{capabilities: Array<{capability: string; status: string}>}>(`${apiUrl}/capabilities`, { timeout: 3000 }),
        axios.get<CoverageReport>(`${apiUrl}/coverage`, { timeout: 3000 }),
      ]);
      setVisualProviderActive(capabilityResponse.data.capabilities.some(item => item.capability === 'Visual geolocation' && item.status === 'active'));
      setMapProviderActive(capabilityResponse.data.capabilities.some(item => item.capability === 'Automated map context verification' && item.status === 'active'));
      setStreetProviderActive(capabilityResponse.data.capabilities.some(item => item.capability === 'Street-level imagery comparison' && item.status === 'active'));
      setProvenanceProviderActive(capabilityResponse.data.capabilities.some(item => item.capability === 'Reverse-image and source provenance' && item.status === 'active'));
      setCoverage(coverageResponse.data);
      setService('ready');
    } catch {
      setVisualProviderActive(false);
      setVisualGeolocation(false);
      setMapProviderActive(false);
      setMapVerification(false);
      setStreetProviderActive(false);
      setStreetImageryComparison(false);
      setProvenanceProviderActive(false);
      setSourceProvenance(false);
      setCoverage(null);
      setService('offline');
    }
  }, [apiUrl]);

  useEffect(() => { void checkService(); }, [checkService]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);
  useEffect(() => {
    const firstMappedCandidate = result?.osint.candidates?.find(candidate => candidate.latitude != null && candidate.longitude != null);
    setSelectedMapCandidateId(firstMappedCandidate?.id ?? null);
  }, [result]);

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
        form.append('visual_geolocation', visualGeolocation ? 'true' : 'false');
        form.append('map_verification', mapVerification ? 'true' : 'false');
        form.append('street_imagery_comparison', streetImageryComparison ? 'true' : 'false');
        form.append('source_provenance', sourceProvenance ? 'true' : 'false');
        if (visualGeolocation) setAnalysisStage('Running visual geolocation');
        else if (streetImageryComparison) setAnalysisStage('Comparing street imagery');
        else if (sourceProvenance) setAnalysisStage('Tracing image provenance');
        const response = await axios.post<AnalysisResult>(`${apiUrl}/analyze`, form, { timeout: 210000 });
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

  async function runInstagramAnalysis() {
    if (!apiUrl || service !== 'ready' || !instagramUrl.trim() || !instagramConsent || running) return;
    setRunning(true);
    setAnalysisStage('Retrieving Instagram post');
    setError(null);
    setResult(null);
    try {
      const response = await axios.post<AnalysisResult>(
        `${apiUrl}/analyze/instagram`,
        { url: instagramUrl.trim(), consent: true },
        { timeout: 120000 },
      );
      if (preview) URL.revokeObjectURL(preview);
      setPreview(null);
      setFile(null);
      setResult(response.data);
    } catch (requestError) {
      setError(readableError(requestError));
      if (axios.isAxiosError(requestError) && !requestError.response) setService('offline');
    } finally {
      setRunning(false);
    }
  }

  const score = result && result.forensics.reliability_score !== null ? Math.round(result.forensics.reliability_score * 100) : null;
  const coordinateCandidates = result?.osint.candidates?.filter(
    candidate => typeof candidate.latitude === 'number' && typeof candidate.longitude === 'number',
  ) ?? [];
  const selectedMapCandidate = coordinateCandidates.find(candidate => candidate.id === selectedMapCandidateId) ?? coordinateCandidates[0];
  return <section id="live-analysis" className="analysis-section" aria-labelledby="analysis-title">
    <div className="analysis-heading">
      <div><span className="micro">CONNECTED INVESTIGATION</span><h2 id="analysis-title">Analyze the evidence,<br/>from the original bytes.</h2></div>
      <div className={`service-state ${service}`} role="status">
        <span aria-hidden="true"/>{service === 'ready' ? 'GitHub backend ready' : service === 'browser' ? 'Private browser analysis ready' : service === 'checking' ? 'Checking backend' : 'Backend offline'}
        {service === 'offline' && apiUrl && <button type="button" onClick={checkService} aria-label="Check backend again"><RefreshCw size={14}/></button>}
      </div>
    </div>

    {service === 'ready' && coverage && <section className={`coverage-panel ${coverage.full_reference_coverage ? 'complete' : 'limited'}`} aria-labelledby="coverage-title">
      <div className="coverage-summary">
        <Database size={20}/>
        <div><span className="micro">REFERENCE COVERAGE</span><h3 id="coverage-title">{coverage.full_reference_coverage ? 'Full reference stack active' : 'Service ready · limited reference coverage'}</h3><p>{coverage.active_datasets} of {coverage.total_datasets} reference datasets active. Counts describe indexed data, not worldwide accuracy.</p></div>
      </div>
      <div className="coverage-datasets">
        {coverage.datasets.map(dataset => <div key={dataset.name} className={dataset.status}>
          <span>{dataset.name.replaceAll('_', ' ')}</span>
          <strong>{dataset.status === 'active' ? dataset.reference_count.toLocaleString() : dataset.status.replaceAll('_', ' ')}</strong>
          <small>{dataset.status === 'active' ? `${dataset.one_degree_cells ? `${dataset.one_degree_cells.toLocaleString()} geographic cells · ` : ''}${dataset.independent_origin_groups ? `${dataset.independent_origin_groups.toLocaleString()} origin groups · ` : ''}indexed references` : dataset.purpose}</small>
        </div>)}
      </div>
    </section>}

    <div className="analysis-grid">
      <div {...getRootProps({ className: `drop-area ${isDragActive ? 'dragging' : ''}` })}>
        <input {...getInputProps()} aria-label="Choose an image for forensic analysis"/>
        {preview ? <div className="selected-file">
          {/* Object URLs render only the user-selected local image and are released on change/unmount. */}
          <img src={preview} alt="Selected evidence preview"/>
          <div><FileImage size={18}/><span><strong>{file?.name}</strong><small>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : ''}</small></span></div>
        </div> : <div className="drop-copy"><UploadCloud size={32}/><h3>{isDragActive ? 'Release to inspect' : 'Select an evidence image'}</h3><p>JPG, PNG, or WebP · maximum 20 MB</p></div>}
        {service === 'ready' && <label className={`visual-provider-consent ${visualProviderActive ? '' : 'unavailable'}`}>
          <input type="checkbox" checked={visualGeolocation} onChange={event => setVisualGeolocation(event.target.checked)} disabled={!visualProviderActive || running}/>
          <span><strong>Use GeoTrace local visual model</strong><small>{visualProviderActive ? 'Runs inside your backend. No image or descriptor is sent to a third party.' : 'Train GeoTrace Visual v0 with labeled reference images to enable this option.'}</small></span>
        </label>}
        {service === 'ready' && <label className={`visual-provider-consent ${mapProviderActive ? '' : 'unavailable'}`}>
          <input type="checkbox" checked={mapVerification} onChange={event => setMapVerification(event.target.checked)} disabled={!mapProviderActive || running}/>
          <span><strong>Verify candidates with the local map index</strong><small>{mapProviderActive ? 'Checks coordinates and OCR against offline place data. Nothing is sent to a map service.' : 'Build the GeoTrace place index to enable automated map context.'}</small></span>
        </label>}
        {service === 'ready' && <label className={`visual-provider-consent ${streetProviderActive ? '' : 'unavailable'}`}>
          <input type="checkbox" checked={streetImageryComparison} onChange={event => setStreetImageryComparison(event.target.checked)} disabled={!streetProviderActive || running}/>
          <span><strong>Compare with local street imagery</strong><small>{streetProviderActive ? 'Matches candidates against licensed reference images stored in GeoTrace. The evidence image stays local.' : 'Build the licensed street-reference index to enable this comparison.'}</small></span>
        </label>}
        {service === 'ready' && <label className={`visual-provider-consent ${provenanceProviderActive ? '' : 'unavailable'}`}>
          <input type="checkbox" checked={sourceProvenance} onChange={event => setSourceProvenance(event.target.checked)} disabled={!provenanceProviderActive || running}/>
          <span><strong>Trace matching image sources</strong><small>{provenanceProviderActive ? 'Checks exact copies, re-encodes, crops, and resizes against GeoTrace’s local source index.' : 'Build the licensed source-provenance index to enable private reverse-image matching.'}</small></span>
        </label>}
        <div className="drop-actions">
          <Button variant="outline" type="button" onClick={open}>{file ? 'Choose another' : 'Choose image'}</Button>
          <Button type="button" onClick={runAnalysis} disabled={!file || running || !['ready', 'browser'].includes(service)}>{running ? <><LoaderCircle className="spin" size={18}/> {analysisStage}</> : service === 'browser' ? 'Analyze in browser' : 'Run forensic analysis'}</Button>
        </div>
        <div className="instagram-import">
          <div className="instagram-label"><Instagram size={17}/><div><strong>Instagram experiment</strong><span>Import one permitted public image post</span></div></div>
          <label htmlFor="instagram-post-url" className="sr-only">Instagram post URL</label>
          <input id="instagram-post-url" type="url" value={instagramUrl} onChange={event => setInstagramUrl(event.target.value)} placeholder="https://www.instagram.com/p/.../" disabled={service !== 'ready' || running}/>
          <label className="instagram-consent"><input type="checkbox" checked={instagramConsent} onChange={event => setInstagramConsent(event.target.checked)} disabled={service !== 'ready' || running}/><span>I have permission to retrieve and analyze this post.</span></label>
          <Button variant="outline" type="button" onClick={runInstagramAnalysis} disabled={service !== 'ready' || !instagramUrl.trim() || !instagramConsent || running}>{running && analysisStage.includes('Instagram') ? <><LoaderCircle className="spin" size={18}/> {analysisStage}</> : 'Import and analyze post'}</Button>
        </div>
      </div>

      <div className="analysis-output" aria-live="polite">
        {!result && !error && <div className="output-empty"><ShieldCheck size={30}/><h3>{apiUrl ? 'Evidence remains local until analysis starts.' : 'Explore the investigation workflow.'}</h3><p>{apiUrl ? 'The API validates the file, computes its SHA-256 fingerprint, extracts metadata, checks image signals, and deletes the temporary upload.' : 'Browser analysis extracts EXIF/GPS, reads visible text, and prepares private verification. GeoTrace’s trained visual model and offline map index run through the Python backend.'}</p>{!apiUrl && <div className="osint-preview" aria-label="Connected OSINT workflow"><span><b>01</b> EXIF, GPS, and OCR extraction</span><span><b>02</b> Local map-context verification</span><span><b>03</b> Source-dependency grouping</span><span><b>04</b> Candidate and uncertainty gate</span></div>}</div>}
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
          {result.source && <div className="source-record"><Instagram size={16}/><div><span>INSTAGRAM SOURCE</span><a href={result.source.canonical_url} target="_blank" rel="noreferrer">@{result.source.owner_username} · {result.source.shortcode}<ExternalLink size={12}/></a><small>{new Date(result.source.published_at).toLocaleString()} · one provenance group</small></div></div>}
          {result.metadata.ocr_text && <div className="ocr-result"><span>VISIBLE TEXT · {result.metadata.language_hint ?? 'Script unresolved'} · {result.metadata.ocr_confidence}% OCR</span><p>{result.metadata.ocr_text}</p></div>}
          <div className="hash-row"><span>SHA-256</span><code>{result.sha256}</code></div>
          <div className="indicator-list"><span>Indicators</span>{result.forensics.indicators.length ? <ul>{result.forensics.indicators.slice(0,4).map(item=><li key={item}>{item.replaceAll('_',' ')}</li>)}</ul> : <p>No configured indicators triggered.</p>}</div>
          <p className="result-note">{score === null ? 'Browser analysis verifies local file facts. A forensic reliability score requires the Python analysis service.' : 'Reliability describes the submitted file’s forensic signals. It is not a location-confidence score or proof of manipulation.'}</p>
          <div className="osint-panel">
            <div className="osint-title"><div><Globe2 size={18}/><span><small>OSINT HANDOFF</small><strong>External verification</strong></span></div><span className="osint-state">Review ready</span></div>
            <p className="osint-privacy">{result.osint.privacy.note}</p>
            {!!result.osint.candidates?.length && <div className="candidate-list">
              <div className="candidate-list-heading"><span>RANKED LOCATION CANDIDATES</span><small>{result.osint.calibration?.calibrated ? `Confidence calibrated on ${result.osint.calibration.query_count} held-out images.` : 'Confidence remains unscored until it is benchmark-calibrated.'}</small></div>
              {result.osint.candidates.map(candidate => <article className="candidate-location" key={candidate.id}>
                <div className="candidate-rank">#{candidate.rank}</div>
                <div className="candidate-copy">
                  <span>{candidate.precision_tier.replaceAll('_', ' ')}</span>
                  <strong>{candidate.label}</strong>
                  <small>{candidate.provider} · {candidate.confidence !== null ? `${Math.round(candidate.confidence * 100)}% empirical confidence${candidate.calibration_samples ? ` · ${candidate.calibration_samples} benchmark samples` : ''}` : 'unscored'} · {candidate.verification_status.replaceAll('_', ' ')}</small>
                  <div className="candidate-evidence">
                    <b>{candidate.supports.length} support{candidate.supports.length === 1 ? '' : 's'}</b>
                    <b className={candidate.contradictions.length ? 'has-conflict' : ''}>{candidate.contradictions.length} contradiction{candidate.contradictions.length === 1 ? '' : 's'}</b>
                  </div>
                  {candidate.supports[0] && <p>{candidate.supports[0].summary}</p>}
                  {candidate.contradictions[0] && <p className="candidate-conflict">{candidate.contradictions[0].summary}</p>}
                </div>
              </article>)}
            </div>}
            {selectedMapCandidate && typeof selectedMapCandidate.latitude === 'number' && typeof selectedMapCandidate.longitude === 'number' && <div className="coordinate-map">
              <div className="coordinate-map-heading">
                <div><MapPin size={16}/><span><small>COORDINATE MAP</small><strong>{selectedMapCandidate.label}</strong></span></div>
                <a href={openStreetMapUrl(selectedMapCandidate.latitude, selectedMapCandidate.longitude)} target="_blank" rel="noreferrer">Open full map <ExternalLink size={12}/></a>
              </div>
              {coordinateCandidates.length > 1 && <div className="map-candidate-tabs" aria-label="Choose a location candidate to map">
                {coordinateCandidates.map(candidate => <button type="button" key={candidate.id} aria-pressed={candidate.id === selectedMapCandidate.id} onClick={() => setSelectedMapCandidateId(candidate.id)}>#{candidate.rank} {candidate.label}</button>)}
              </div>}
              <iframe
                title={`Map centered on ${selectedMapCandidate.label}`}
                src={openStreetMapEmbedUrl(selectedMapCandidate.latitude, selectedMapCandidate.longitude)}
                loading="lazy"
                referrerPolicy="strict-origin-when-cross-origin"
              />
              <div className="coordinate-map-footer"><code>{selectedMapCandidate.latitude.toFixed(6)}, {selectedMapCandidate.longitude.toFixed(6)}</code><span>Map © OpenStreetMap contributors · loading the map shares these coordinates with OpenStreetMap.</span></div>
            </div>}
            {!!result.osint.provider_status?.length && <div className="capability-grid" aria-label="Geolocation capability coverage">
              {result.osint.provider_status.map(item => <div key={item.capability}><span>{item.capability}</span><strong className={`capability-${item.status}`}>{item.status.replaceAll('_', ' ')}</strong></div>)}
            </div>}
            {result.osint.calibration && <div className={`calibration-record ${result.osint.calibration.calibrated ? 'active' : ''}`}>
              <div className="calibration-heading"><span>CONFIDENCE CALIBRATION</span><strong>{result.osint.calibration.status.replaceAll('_', ' ')}</strong></div>
              {result.osint.calibration.calibrated && result.osint.calibration.overall ? <>
                <div className="calibration-metrics">
                  <div><span>Top-1 within {result.osint.calibration.distance_threshold_km} km</span><strong>{result.osint.calibration.overall.top1_accuracy === null ? '—' : `${Math.round(result.osint.calibration.overall.top1_accuracy * 100)}%`}</strong></div>
                  <div><span>Top-5 within {result.osint.calibration.distance_threshold_km} km</span><strong>{result.osint.calibration.overall.top5_accuracy === null ? '—' : `${Math.round(result.osint.calibration.overall.top5_accuracy * 100)}%`}</strong></div>
                  <div><span>Median error</span><strong>{result.osint.calibration.overall.median_error_km ?? '—'} km</strong></div>
                  <div><span>90th percentile error</span><strong>{result.osint.calibration.overall.p90_error_km ?? '—'} km</strong></div>
                </div>
                <p>{result.osint.calibration.query_count} held-out benchmark images · model {result.osint.calibration.model_fingerprint}. Confidence is benchmark-derived and still requires independent corroboration.</p>
              </> : <p>{result.osint.calibration.reason}</p>}
            </div>}
            {!!result.osint.map_verification?.records.length && <div className="map-verification-record">
              <span>LOCAL MAP CONTEXT</span>
              {result.osint.map_verification.records.map(record => <div key={record.candidate_id}>
                <strong>#{result.osint.candidates?.find(candidate => candidate.id === record.candidate_id)?.rank} · {record.place.name}, {record.place.country}</strong>
                <small>{record.place.distance_km} km from candidate · {record.status.replaceAll('_', ' ')}</small>
              </div>)}
              <p>{result.osint.map_verification.attribution}</p>
            </div>}
            {!!result.osint.street_imagery_comparison?.records.length && <div className="street-comparison-record">
              <div className="street-comparison-heading"><span>STREET-LEVEL COMPARISON</span><small>{result.osint.street_imagery_comparison.engine} · {result.osint.street_imagery_comparison.reference_images} local references</small></div>
              {result.osint.street_imagery_comparison.records.map(record => {
                const best = record.matches[0];
                const rank = result.osint.candidates?.find(candidate => candidate.id === record.candidate_id)?.rank;
                return <div className="street-match" key={record.candidate_id}>
                  <div><strong>Candidate #{rank ?? '?'} · {record.status.replaceAll('_', ' ')}</strong><small>{best ? `${Math.round(best.similarity * 100)}% similarity signal · ${best.distance_km} km away` : `No indexed street imagery within ${record.radius_km} km`}</small></div>
                  {best && <div className="street-reference"><span>{best.label}</span><small>{best.attribution} · {best.license}{best.captured_at ? ` · ${best.captured_at}` : ''}</small>{best.source_url && <a href={best.source_url} target="_blank" rel="noreferrer">Open reference <ExternalLink size={12}/></a>}</div>}
                </div>;
              })}
              <p>{result.osint.street_imagery_comparison.method_note}</p>
            </div>}
            {result.osint.source_provenance && <div className="provenance-record">
              <div className="provenance-heading"><div><Fingerprint size={16}/><span><small>SOURCE PROVENANCE</small><strong>{result.osint.source_provenance.status.replaceAll('_', ' ')}</strong></span></div><span>{result.osint.source_provenance.reference_images} indexed images</span></div>
              {!!result.osint.source_provenance.timeline.length ? <div className="provenance-timeline">
                {result.osint.source_provenance.timeline.map((entry, index) => <article key={entry.reference_id}>
                  <div className="timeline-marker"><span>{index + 1}</span></div>
                  <div><span>{entry.timeline_role.replaceAll('_', ' ')} · {new Date(entry.published_at).toLocaleString()}</span><strong>{entry.title}</strong><small>{entry.source_name} · {entry.match_type.replaceAll('_', ' ')} · {Math.round(entry.perceptual_similarity * 100)}% similarity signal</small><p>{entry.attribution} · {entry.license} · origin group {entry.origin_group}</p><a href={entry.source_url} target="_blank" rel="noreferrer">Open indexed source <ExternalLink size={12}/></a></div>
                </article>)}
              </div> : <div className="provenance-empty">No matching publication was found in the current local index.</div>}
              <p className="provenance-note">{result.osint.source_provenance.method_note}</p>
            </div>}
            <div className="osint-actions">{result.osint.actions.map(action=><a key={action.id} href={action.url} target="_blank" rel="noreferrer"><span><strong>{action.provider}</strong><small>{action.label}</small></span><ExternalLink size={14}/></a>)}</div>
            <div className="dependency-note"><Network size={16}/><div><strong>{result.osint.dependency_groups[0]?.label ?? 'Submitted image'} · one source group</strong><p>{result.osint.dependency_groups[0]?.explanation}</p></div></div>
            <div className="uncertainty-row"><span>Decision</span><strong>{result.osint.uncertainty.outcome.replaceAll('_', ' ')}</strong><small>{result.osint.uncertainty.calibrated && result.osint.uncertainty.confidence !== null ? `${Math.round(result.osint.uncertainty.confidence * 100)}% calibrated confidence` : result.osint.conflicts.length ? `${result.osint.conflicts.length} conflicts detected` : result.osint.street_imagery_comparison?.records.length ? `${result.osint.street_imagery_comparison.records.length} street comparison(s)` : result.osint.map_verification?.records.length ? `${result.osint.map_verification.records.length} map context check(s)` : 'No independent sources collected'}</small></div>
          </div>
        </div>}
      </div>
    </div>
  </section>;
}
