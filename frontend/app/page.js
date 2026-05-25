'use client';

import { useEffect, useState } from 'react';

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'https://dtap-demo1.onrender.com/api';

const CHART_W = 720;
const CHART_H = 260;
const CHART_PAD = 36;

const EMPTY_FORM = {
  soilLevel: '2048',
  ambientLightLevel: '400',
  humidityLevels: '40',
  temperatureLevels: '22',
};

// Icons (Lucide)
const LeafIcon = () => <svg xmlns="http://www.جة" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/></svg>;
const ActivityIcon = () => <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>;
const AudioIcon = () => <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>;
const TableIcon = () => <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/><path d="M15 3v18"/></svg>;
const SettingsIcon = () => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>;
const LogoutIcon = () => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>;

function linePath(pts, w, h, val, max) {
  if (!pts.length || max <= 0) return '';
  const step = pts.length > 1 ? w / (pts.length - 1) : 0;
  return pts
    .map((p, i) => {
      const x = i * step;
      const y = h - (val(p) / max) * h;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function fmtDate(iso) {
  return new Date(iso).toLocaleString();
}

function getHealthIndex(r) {
  if (!r) return null;
  let score = 100;
  
  // Soil penalty (optimal: 20-80%)
  const soilPct = (r.soilLevel / 4095) * 100;
  if (soilPct < 20) score -= (20 - soilPct) * 1.5;
  else if (soilPct > 80) score -= (soilPct - 80) * 1.5;

  // Temperature penalty (optimal: 15-32°C)
  if (r.temperatureLevels < 15) score -= (15 - r.temperatureLevels) * 2;
  else if (r.temperatureLevels > 32) score -= (r.temperatureLevels - 32) * 2;

  // Humidity penalty (optimal: 25-85%)
  if (r.humidityLevels < 25) score -= (25 - r.humidityLevels) * 0.5;
  else if (r.humidityLevels > 85) score -= (r.humidityLevels - 85) * 0.5;

  // Light penalty (optimal: >50 lux)
  if (r.ambientLightLevel < 50) score -= (50 - r.ambientLightLevel) * 0.2;

  return Math.max(0, Math.min(100, Math.round(score)));
}

function formatSoil(raw) {
  return ((raw / 4095) * 100).toFixed(1);
}

export default function HomePage() {
  const [deviceId, setDeviceId] = useState('');
  const [isSetup, setIsSetup] = useState(false);
  const [setupInput, setSetupInput] = useState('');

  const [form, setForm] = useState(EMPTY_FORM);
  const [readings, setReadings] = useState([]);
  const [latest, setLatest] = useState(null);
  const [plantStatus, setPlantStatus] = useState(null);
  const [appMode, setAppMode] = useState('sfw');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState('');
  const [audioUrl, setAudioUrl] = useState('');

  useEffect(() => {
    const savedId = localStorage.getItem('planty_device_id');
    if (savedId) {
      setDeviceId(savedId);
      setIsSetup(true);
    } else {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isSetup && deviceId) {
      loadReadings(deviceId);
      loadStatus(deviceId);
      loadMode();
    }
  }, [isSetup, deviceId]);

  useEffect(() => {
    return () => { if (audioUrl) URL.revokeObjectURL(audioUrl); };
  }, [audioUrl]);

  async function loadReadings(id) {
    setLoading(true);
    setError('');
    try {
      const r = await fetch(`${apiBaseUrl}/readings/?deviceId=${encodeURIComponent(id)}`, { cache: 'no-store' });
      if (!r.ok) throw new Error('Failed to load readings.');
      const d = await r.json();
      setReadings(d.items || []);
      setLatest(d.latest || null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadStatus(id) {
    try {
      const r = await fetch(`${apiBaseUrl}/plant/status/?deviceId=${encodeURIComponent(id)}`, { cache: 'no-store' });
      if (r.status === 404) { setPlantStatus(null); return; }
      if (!r.ok) throw new Error('Failed to load status.');
      setPlantStatus(await r.json());
    } catch (e) {
      setError(e.message);
    }
  }

  async function loadMode() {
    try {
      const r = await fetch(`${apiBaseUrl}/mode/`, { cache: 'no-store' });
      if (r.ok) { const d = await r.json(); setAppMode(d.mode); }
    } catch {}
  }

  function handleSetupSubmit(e) {
    e.preventDefault();
    if (!setupInput.trim()) return;
    localStorage.setItem('planty_device_id', setupInput.trim());
    setDeviceId(setupInput.trim());
    setIsSetup(true);
  }

  function logout() {
    localStorage.removeItem('planty_device_id');
    setDeviceId('');
    setIsSetup(false);
    setReadings([]);
    setLatest(null);
    setPlantStatus(null);
    setAudioUrl('');
  }

  function onChange(e) {
    const { name, value } = e.target;
    setForm((f) => ({ ...f, [name]: value }));
  }

  async function onSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const r = await fetch(`${apiBaseUrl}/readings/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          soilLevel: Number(form.soilLevel),
          ambientLightLevel: Number(form.ambientLightLevel),
          humidityLevels: Number(form.humidityLevels),
          temperatureLevels: Number(form.temperatureLevels),
          deviceId: deviceId,
        }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || 'Failed to save.');
      setForm(EMPTY_FORM);
      await Promise.all([loadReadings(deviceId), loadStatus(deviceId)]);
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function toggleMode() {
    const next = appMode === 'sfw' ? 'nsfw' : 'sfw';
    try {
      const r = await fetch(`${apiBaseUrl}/mode/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: next }),
      });
      if (r.ok) setAppMode(next);
    } catch {}
  }

  async function playVoice() {
    setSpeaking(true);
    setError('');
    try {
      const r = await fetch(`${apiBaseUrl}/plant/voice/?deviceId=${encodeURIComponent(deviceId)}`);
      if (!r.ok) { const d = await r.json(); throw new Error(d.error || 'Voice failed.'); }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      setAudioUrl(url);
      const cond = r.headers.get('X-Plant-Condition');
      const msg = r.headers.get('X-Plant-Message');
      if (cond && msg) setPlantStatus((s) => ({ ...(s || {}), condition: cond, message: msg }));
    } catch (e) {
      setError(e.message);
    } finally {
      setSpeaking(false);
    }
  }

  if (!isSetup) {
    return (
      <div className="app theme-good">
        <div className="setup-overlay">
          <form className="setup-card" onSubmit={handleSetupSubmit}>
            <div className="setup-icon"><LeafIcon /></div>
            <h1 className="setup-title">Welcome to Planty</h1>
            <p className="setup-desc">Enter your unique Planty Device ID to connect to your dashboard.</p>
            <div className="setup-form">
              <input 
                autoFocus
                className="setup-input" 
                placeholder="e.g. ESP32_LIVING_ROOM" 
                value={setupInput} 
                onChange={e => setSetupInput(e.target.value)} 
                required 
              />
              <button className="btn-primary" type="submit">Connect Device</button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  const cond = latest?.condition || plantStatus?.condition || 'unknown';
  const themeClass = cond === 'bad' ? 'theme-bad' : cond === 'neutral' ? 'theme-neutral' : 'theme-good';
  const healthIndex = getHealthIndex(latest);

  const chartPts = [...readings].reverse();
  const lightMax = Math.max(100, ...chartPts.map((r) => Math.ceil(r.ambientLightLevel / 100) * 100));
  const tempMax = Math.max(40, ...chartPts.map((r) => Math.ceil(r.temperatureLevels / 10) * 10));
  const pw = CHART_W - CHART_PAD * 2;
  const ph = CHART_H - CHART_PAD * 2;
  const soilD = linePath(chartPts, pw, ph, (r) => (r.soilLevel / 4095) * 100, 100);
  const lightD = linePath(chartPts, pw, ph, (r) => r.ambientLightLevel, lightMax);
  const humD = linePath(chartPts, pw, ph, (r) => r.humidityLevels, 100);
  const tempD = linePath(chartPts, pw, ph, (r) => r.temperatureLevels, tempMax);

  return (
    <div className={`app ${themeClass}`}>
      <header className="header">
        <div className="header-inner">
          <div className="brand">
            <LeafIcon />
            <div>
              <h1 className="title">Planty Patootie</h1>
              <p className="subtitle">ID: {deviceId}</p>
            </div>
          </div>
          <div className="header-actions">
            <button className="mode-toggle" onClick={toggleMode} title="Toggle SFW / NSFW Mode">
              <SettingsIcon />
              <span>{appMode.toUpperCase()}</span>
            </button>
            <button className="btn-secondary" onClick={logout} title="Switch Device">
              <LogoutIcon />
              <span>Logout</span>
            </button>
          </div>
        </div>
      </header>

      <main className="main">
        <div className="grid">
          <aside className="sidebar">
            
            {latest && (
              <div className="card metrics-card">
                <div className="health-index-wrap">
                  <span className="health-index-val">{healthIndex}</span>
                  <span className="health-index-label">Health Index</span>
                </div>
                <div className="metrics-grid">
                  <div className="metric">
                    <span className="metric-label">Soil</span>
                    <span className="metric-value">{formatSoil(latest.soilLevel)}%</span>
                  </div>
                  <div className="metric">
                    <span className="metric-label">Light</span>
                    <span className="metric-value">{latest.ambientLightLevel} lx</span>
                  </div>
                  <div className="metric">
                    <span className="metric-label">Humidity</span>
                    <span className="metric-value">{latest.humidityLevels}%</span>
                  </div>
                  <div className="metric">
                    <span className="metric-label">Temp</span>
                    <span className="metric-value">{latest.temperatureLevels}°C</span>
                  </div>
                </div>
                <p className="timestamp">Updated {fmtDate(latest.recordedAt)}</p>
              </div>
            )}

            <form className="card form-card" onSubmit={onSubmit}>
              <h2 className="card-title">
                <ActivityIcon /> Add Reading
              </h2>
              <div className="field">
                <label htmlFor="soilLevel">Soil Moisture (Raw ADC 0-4095)</label>
                <input id="soilLevel" name="soilLevel" type="range" min="0" max="4095" value={form.soilLevel} onChange={onChange} />
                <span className="field-value">{formatSoil(form.soilLevel)}%</span>
              </div>
              <div className="field">
                <label htmlFor="ambientLightLevel">Ambient Light (lux)</label>
                <input id="ambientLightLevel" name="ambientLightLevel" type="number" min="0" value={form.ambientLightLevel} onChange={onChange} required />
              </div>
              <div className="field">
                <label htmlFor="humidityLevels">Humidity (%)</label>
                <input id="humidityLevels" name="humidityLevels" type="number" step="0.1" value={form.humidityLevels} onChange={onChange} required />
              </div>
              <div className="field">
                <label htmlFor="temperatureLevels">Temperature (°C)</label>
                <input id="temperatureLevels" name="temperatureLevels" type="number" step="0.1" value={form.temperatureLevels} onChange={onChange} required />
              </div>
              <button className="btn-primary" type="submit" disabled={submitting}>
                {submitting ? 'Analyzing...' : 'Submit Reading'}
              </button>
            </form>
          </aside>

          <div className="content">
            <section className="card voice-card">
              <h2 className="card-title">
                <AudioIcon /> Plant Voice
              </h2>
              {plantStatus ? (
                <div className="voice-body">
                  <div className="voice-header">
                    <span className="cond-badge">{cond}</span>
                    <button className="btn-primary" onClick={playVoice} disabled={speaking}>
                      <AudioIcon /> {speaking ? 'Generating...' : 'Listen'}
                    </button>
                  </div>
                  <blockquote className="quote">&ldquo;{plantStatus.message}&rdquo;</blockquote>
                  {audioUrl && <audio controls autoPlay src={audioUrl} className="player" />}
                  <ul className="messages">
                    {(plantStatus.messages || []).map((m, i) => (
                      <li key={i} className="msg-item">{m}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="empty">Submit a reading to awaken your plant.</p>
              )}
            </section>

            <section className="card chart-card">
              <h2 className="card-title">
                <ActivityIcon /> Sensor Trends
              </h2>
              {chartPts.length ? (
                <>
                  <div className="chart-legend">
                    <span className="leg"><span className="swatch s-soil" /> Soil</span>
                    <span className="leg"><span className="swatch s-light" /> Light</span>
                    <span className="leg"><span className="swatch s-hum" /> Humidity</span>
                    <span className="leg"><span className="swatch s-temp" /> Temperature</span>
                  </div>
                  <div className="chart-wrap">
                    <svg className="chart" viewBox={`0 0 ${CHART_W} ${CHART_H}`} role="img" aria-label="Sensor trend chart">
                      <g transform={`translate(${CHART_PAD},${CHART_PAD})`}>
                        {[0, 0.25, 0.5, 0.75, 1].map((s) => {
                          const y = ph - ph * s;
                          return <line key={s} x1="0" y1={y} x2={pw} y2={y} className="grid-line" />;
                        })}
                        {soilD && <path d={soilD} className="line soil-l" />}
                        {lightD && <path d={lightD} className="line light-l" />}
                        {humD && <path d={humD} className="line hum-l" />}
                        {tempD && <path d={tempD} className="line temp-l" />}
                        {chartPts.map((r, i) => {
                          const x = chartPts.length > 1 ? (i * pw) / (chartPts.length - 1) : pw / 2;
                          return (
                            <g key={r.id}>
                              <circle cx={x} cy={ph - ((r.soilLevel / 4095) * 100) / 100 * ph} r="3.5" className="dot d-soil" />
                              <circle cx={x} cy={ph - (r.ambientLightLevel / lightMax) * ph} r="3.5" className="dot d-light" />
                              <circle cx={x} cy={ph - (r.humidityLevels / 100) * ph} r="3.5" className="dot d-hum" />
                              <circle cx={x} cy={ph - (r.temperatureLevels / tempMax) * ph} r="3.5" className="dot d-temp" />
                              <text x={x} y={ph + 18} textAnchor="middle" className="axis-label">{fmtTime(r.recordedAt)}</text>
                            </g>
                          );
                        })}
                      </g>
                    </svg>
                  </div>
                </>
              ) : (
                <p className="empty">Add readings to see trends.</p>
              )}
            </section>

            <section className="card table-card">
              <h2 className="card-title">
                <TableIcon /> History Log
              </h2>
              {loading ? (
                <p className="empty">Loading...</p>
              ) : readings.length ? (
                <div className="tbl-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Soil</th>
                        <th>Light</th>
                        <th>Humidity</th>
                        <th>Temp</th>
                        <th>Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {readings.map((r) => (
                        <tr key={r.id}>
                          <td>{formatSoil(r.soilLevel)}%</td>
                          <td>{r.ambientLightLevel} lx</td>
                          <td>{r.humidityLevels}%</td>
                          <td>{r.temperatureLevels}°C</td>
                          <td className="mono">{fmtTime(r.recordedAt)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="empty">No history yet.</p>
              )}
            </section>
          </div>
        </div>
      </main>

      {error && <div className="toast" role="alert">{error}</div>}

      <footer className="footer">
        <p>Planty Patootie &middot; Device: {deviceId} &middot; Aalto DTAP</p>
      </footer>
    </div>
  );
}