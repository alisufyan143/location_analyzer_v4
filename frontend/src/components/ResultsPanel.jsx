import { useState, useRef } from 'react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { TrendingUp, ChevronDown, ChevronUp, Maximize2, Minimize2, Download, BarChart2 } from 'lucide-react'
import html2canvas from 'html2canvas';
import { jsPDF } from 'jspdf';
import ReportLayout from './ReportLayout';

// ── Shared styles ─────────────────────────────────────────────────────────────
const TABLE = { width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }
const TH = {
    textAlign: 'left', padding: '0.35rem 0.6rem', color: 'var(--text-secondary)',
    fontWeight: 600, borderBottom: '1px solid var(--border-color)',
    fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.04em'
}
const THR = { ...TH, textAlign: 'right' }
const TDL = { padding: '0.3rem 0.6rem', color: 'var(--text-secondary)', fontWeight: 500 }
const TDV = { padding: '0.3rem 0.6rem', color: 'var(--text-primary)', fontWeight: 600, textAlign: 'right' }
const ROW_E = { backgroundColor: 'rgba(255,255,255,0.03)' }
const ROW_O = {}

const SECTION_TITLE = {
    fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-secondary)',
    textTransform: 'uppercase', letterSpacing: '0.06em',
    marginBottom: '0.5rem', marginTop: 0,
}
const PANEL = {
    borderRadius: '10px',
    border: '1px solid var(--border-color)',
    padding: '0.75rem 1rem',
    background: 'rgba(255,255,255,0.02)',
    display: 'flex', flexDirection: 'column',
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmtPct(v) {
    if (v === null || v === undefined) return '—'
    // fraction 0–1 scale (Nomis scraper)
    if (v <= 1.0) return `${(v * 100).toFixed(1)}%`
    // already a percentage (CrystalRoof scraper)
    return `${Number(v).toFixed(1)}%`
}
function fmtMoney(v) {
    if (!v) return '—'
    return `£${Number(v).toLocaleString()}`
}

const CLASS_COLORS = {
    ab: '#2ecc71', 'c1/c2': '#3498db', de: '#e74c3c',
    working: '#9b59b6', unemployed: '#e67e22',
    white: '#95a5a6', 'non-white': '#1abc9c',
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionTitle({ children }) {
    return <h4 style={SECTION_TITLE}>{children}</h4>
}

/** Generic 2-col key/value table */
function KVTable({ rows }) {
    if (!rows.length) return <p style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>No data</p>
    return (
        <table style={TABLE}>
            <thead><tr><th style={TH}>Field</th><th style={THR}>Value</th></tr></thead>
            <tbody>
                {rows.map(({ label, value }, i) => (
                    <tr key={label} style={i % 2 === 0 ? ROW_E : ROW_O}>
                        <td style={TDL}>{label}</td>
                        <td style={TDV}>{value}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    )
}

/** Name + distance table (restaurants, pubs) */
function PlaceTable({ items, colName }) {
    if (!items || !items.length) return <p style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>No data</p>
    return (
        <table style={TABLE}>
            <thead>
                <tr>
                    <th style={TH}>#</th>
                    <th style={TH}>{colName}</th>
                    <th style={THR}>Distance</th>
                </tr>
            </thead>
            <tbody>
                {items.map((item, i) => (
                    <tr key={i} style={i % 2 === 0 ? ROW_E : ROW_O}>
                        <td style={{ ...TDL, color: 'var(--text-muted)', width: '1.5rem' }}>{i + 1}</td>
                        <td style={TDL}>{item.name}</td>
                        <td style={TDV}>{item.distance}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    )
}

/** Colored badge percentage table (ethnicity, religion, age, household sections; occupation) */
function BadgeTable({ rows, colorMap }) {
    if (!rows || !rows.length) return <p style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>No data</p>
    return (
        <table style={TABLE}>
            <thead>
                <tr>
                    <th style={TH}>#</th>
                    <th style={TH}>Category</th>
                    <th style={THR}>%</th>
                </tr>
            </thead>
            <tbody>
                {rows.map(({ name, pct }, i) => {
                    const color = (colorMap && colorMap[name.toLowerCase()]) || 'var(--accent-primary)'
                    const isSolid = pct >= 30
                    return (
                        <tr key={i} style={i % 2 === 0 ? ROW_E : ROW_O}>
                            <td style={{ ...TDL, color: 'var(--text-muted)', width: '1.5rem' }}>{i + 1}</td>
                            <td style={{ padding: '0.25rem 0.6rem' }}>
                                <span style={{
                                    display: 'inline-block', padding: '0.12rem 0.45rem',
                                    borderRadius: '4px', fontSize: '0.76rem', fontWeight: 600,
                                    backgroundColor: isSolid ? color : 'transparent',
                                    color: isSolid ? '#fff' : color,
                                    border: `1px solid ${color}`,
                                }}>{name}</span>
                            </td>
                            <td style={TDV}>{Number(pct).toFixed(1)}%</td>
                        </tr>
                    )
                })}
            </tbody>
        </table>
    )
}

/** Collapsible section panel */
function CollapsiblePanel({ title, defaultOpen = true, children }) {
    const [open, setOpen] = useState(defaultOpen)
    return (
        <div style={{ ...PANEL, marginBottom: '0.75rem' }}>
            <div
                onClick={() => setOpen(o => !o)}
                style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    cursor: 'pointer', userSelect: 'none', marginBottom: open ? '0.5rem' : 0
                }}>
                <span style={SECTION_TITLE}>{title}</span>
                {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </div>
            {open && children}
        </div>
    )
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function ResultsPanel({ result, apiBase }) {
    const [granularity, setGranularity] = useState('monthly');
    const [isMinimized, setIsMinimized] = useState(false);
    const [isExporting, setIsExporting] = useState(false);
    const [isExportingHTML, setIsExportingHTML] = useState(false);
    const reportRef = useRef(null);

    const exportToPDF = async () => {
        if (!reportRef.current) return;
        setIsExporting(true);
        try {
            // Temporarily make the off-screen element visible to html2canvas, but hidden via z-index
            const el = reportRef.current;
            const originalTop = el.style.top;
            el.style.top = '0';
            el.style.zIndex = '-100';

            const canvas = await html2canvas(el, { 
                scale: 2, 
                backgroundColor: '#0f172a',
                useCORS: true,
                allowTaint: true
            });
            el.style.top = originalTop;

            const imgData = canvas.toDataURL('image/png');
            const pdf = new jsPDF({
                orientation: 'portrait',
                unit: 'px',
                format: [canvas.width / 2, canvas.height / 2] // Scale down canvas size to fit exactly
            });

            pdf.addImage(imgData, 'PNG', 0, 0, canvas.width / 2, canvas.height / 2);
            pdf.save(`Location_Report_${result.postcode.replace(' ', '_')}.pdf`);
        } catch (err) {
            console.error('PDF Generation failed', err);
        } finally {
            setIsExporting(false);
        }
    };

    const exportToHTML = async () => {
        setIsExportingHTML(true);
        try {
            const exportGranularity = 'weekly';
            const currentChartData = result.time_series?.[exportGranularity] || [];
            if (!currentChartData.length) return;

            const dates = currentChartData.map(d => d.date);
            const sales = currentChartData.map(d => d.predicted_sales);

            const payload = {
                postcode: result.postcode,
                dates,
                sales,
                granularity: exportGranularity,
                features: result.features || {},
                display_data: result.display_data || {}
            };

            const response = await fetch(`${apiBase}/export-plot`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) throw new Error('Failed to generate HTML plot');

            const htmlContent = await response.text();
            const blob = new Blob([htmlContent], { type: 'text/html' });
            const url = URL.createObjectURL(blob);

            const a = document.createElement('a');
            a.href = url;
            a.download = `Interactive_Report_${result.postcode.replace(' ', '_')}.html`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (err) {
            console.error('HTML Export failed', err);
        } finally {
            setIsExportingHTML(false);
        }
    };

    if (!result) return null
    const f = result.features
    const dd = result.display_data || {}

    // result.time_series is now an object: { daily: [], weekly: [], monthly: [] }
    const chartData = result.time_series?.[granularity] || []

    // Calculate highest value in current view
    const peakValue = chartData.length > 0
        ? Math.max(...chartData.map(d => d.predicted_sales))
        : result.predicted_sales;

    const xAxisFormatter = (dateStr) => {
        if (!dateStr) return dateStr;
        try {
            const date = new Date(dateStr);
            if (granularity === 'daily') {
                return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
            }
            // For Weekly and Monthly, always show the year for clarity in 2010-2030 range
            return date.toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
        } catch (e) {
            return dateStr;
        }
    };

    // ── Demographics KV rows (always available from Nomis)
    const DEMO_ROWS = [
        { key: 'postcode', label: 'Postcode', fmt: v => v },
        { key: 'population', label: 'Population', fmt: v => Number(v).toLocaleString() },
        { key: 'households', label: 'Households', fmt: v => Number(v).toLocaleString() },
        { key: 'avg_household_income', label: 'Avg Income', fmt: fmtMoney },
        { key: 'working', label: 'Working', fmt: fmtPct },
        { key: 'unemployed', label: 'Unemployed', fmt: fmtPct },
        { key: 'ab', label: 'AB Class', fmt: fmtPct },
        { key: 'c1/c2', label: 'C1/C2 Class', fmt: fmtPct },
        { key: 'de', label: 'DE Class', fmt: fmtPct },
        { key: 'non-white', label: 'Non-White', fmt: fmtPct },
        { key: 'percent_muslim', label: 'Muslim Pop %', fmt: fmtPct },
        { key: 'ethnic_diversity_index', label: 'Diversity Index', fmt: v => v ? Number(v).toFixed(3) : '—' },
        { key: 'workplace_to_resident_ratio', label: 'Workplace Ratio', fmt: v => v ? Number(v).toFixed(2) : '—' },
        { key: 'rateable_value', label: 'Rateable Value', fmt: v => v ? `£${Number(v).toLocaleString()}` : '—' },
        { key: 'Transport_Accessibility_Score', label: 'Transport Score', fmt: v => v ? `${v}/9` : '—' },
        { key: 'Nearby_Station_Count', label: 'Nearby Stations', fmt: v => v },
        { key: 'Distance_to_Nearest_Station', label: 'Nearest Station', fmt: v => `${Number(v).toFixed(2)} mi` },
        { key: 'Nearest_Station_Type', label: 'Station Type', fmt: v => v },
    ].filter(r => f[r.key] !== undefined && f[r.key] !== null)
        .map(r => ({ label: r.label, value: r.fmt(f[r.key]) }))

    // ── Affluence rating
    const affluence = dd.affluence || {}

    // ── Occupation rows (% values from CrystalRoof — already percentages 0–100)
    const OCCI_LABELS = [
        'managerial and professional',
        'intermediate occupations',
        'routine and manual',
        'never worked, long-term unemployed',
        'full-time students',
        'university degree or higher',
        'no qualification',
        'college / a-levels',
        'professional or trade training',
        'high school graduate',
        'some high school',
        'other qualification',
    ]
    const occupation = dd.occupation || {}
    const occRows = OCCI_LABELS
        .filter(k => occupation[k] !== undefined)
        .map(k => ({ name: k.replace(/\b\w/g, c => c.toUpperCase()), pct: occupation[k] }))
    const otherOccRows = Object.entries(occupation)
        .filter(([k]) => !OCCI_LABELS.includes(k))
        .map(([k, v]) => ({ name: k.replace(/\b\w/g, c => c.toUpperCase()), pct: v }))

    // ── Ethnicity sections (new structured format from fixed parser)
    const ethnicity = dd.ethnicity || {}
    const ethSections = ethnicity.sections || {}
    // Legacy fallback: if old format (details dict), convert it
    const hasNewFormat = !!ethnicity.sections

    // ── Transport stations
    const transport = dd.transport || {}
    const stations = transport.stations || []
    const stationRows = stations.map(s => ({
        name: s.name,
        pct: null,
        distance: `${s.distance} mi`,
        type: s.type,
        lines: (s.lines || []).filter(Boolean).join(', '),
    }))

    // ── Restaurants / pubs
    const amenities = dd.amenities || {}
    const restaurants = amenities.restaurants || []
    const pubs = amenities.pubs || []

    return (
        <div className="glass-panel animate-slide-up results-floating-panel" style={{
            position: 'absolute', bottom: 0, right: 0, left: 0,
            padding: isMinimized ? '0.75rem 2rem' : '1.5rem 2rem',
            display: 'flex', flexDirection: 'column',
            gap: isMinimized ? '0' : '1.5rem',
            zIndex: 1000,
            maxHeight: isMinimized ? '80px' : '55vh',
            overflowY: isMinimized ? 'hidden' : 'auto',
            transition: 'all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1)'
        }}>

            {/* ── MINIMIZED STRIP ─────────────────────────────────────────────────── */}
            {isMinimized && (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-secondary)' }}>
                            <TrendingUp size={18} color="var(--accent-success)" />
                            <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>
                                Predicted {granularity.charAt(0).toUpperCase() + granularity.slice(1)} Sales:
                            </span>
                        </div>
                        <div className="gradient-text" style={{ fontSize: '1.25rem', fontWeight: 700 }}>
                            {result.currency}{peakValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginLeft: '1rem', paddingLeft: '1rem', borderLeft: '1px solid var(--border-color)' }}>
                            {f["Branch Name"] && `${f["Branch Name"]} - `}{result.postcode}
                        </div>
                    </div>

                    <button
                        onClick={() => setIsMinimized(false)}
                        className="btn"
                        style={{ background: 'rgba(255,255,255,0.05)', color: 'var(--text-primary)', padding: '0.4rem 0.8rem', fontSize: '0.8rem' }}
                        title="Restore Panel"
                    >
                        <Maximize2 size={16} /> Maximize
                    </button>
                </div>
            )}

            {/* ── UPPER PANEL: Prediction Info & Large Graph ──────────────────────── */}
            {!isMinimized && (
                <>
                    <div className="results-info-header" style={{ display: 'flex', gap: '2rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1.5rem', position: 'relative' }}>
                        {/* Left: Prediction Number */}
                        <div style={{ minWidth: '220px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem', color: 'var(--text-secondary)' }}>
                                <TrendingUp size={20} color="var(--accent-success)" />
                                <span style={{ fontSize: '0.8rem', fontWeight: 500 }}>
                                    Predicted {granularity.charAt(0).toUpperCase() + granularity.slice(1)} Sales
                                </span>
                            </div>
                            <div className="gradient-text" style={{ fontSize: '2.4rem', lineHeight: 1, fontWeight: 700 }}>
                                {result.currency}{peakValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </div>
                            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                                {result.postcode}
                                {affluence.rating && (
                                    <span style={{
                                        marginLeft: '0.75rem', padding: '0.1rem 0.5rem', borderRadius: '99px',
                                        background: 'rgba(255,255,255,0.08)', fontSize: '0.72rem',
                                        color: 'var(--accent-success)', fontWeight: 600
                                    }}>
                                        Affluence {affluence.rating}/10
                                    </span>
                                )}
                            </p>
                        </div>

                        {/* Right: Large Horizontally-Scrollable Chart */}
                        <div style={{ flex: 1, minWidth: 0, position: 'relative', display: 'flex', flexDirection: 'column' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                                <span style={{ ...SECTION_TITLE, margin: 0, fontSize: '0.85rem' }}>12-Month Forecast Curve</span>
                                <div className="results-actions" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                    {/* Granularity Toggle */}
                                    <div style={{
                                        display: 'flex', gap: '2px', background: 'rgba(255,255,255,0.05)',
                                        padding: '2px', borderRadius: '6px', border: '1px solid var(--border-color)'
                                    }}>
                                        {['daily', 'weekly', 'monthly'].map(mode => (
                                            <button
                                                key={mode}
                                                onClick={() => setGranularity(mode)}
                                                style={{
                                                    background: granularity === mode ? 'var(--accent-primary)' : 'transparent',
                                                    color: granularity === mode ? '#fff' : 'var(--text-secondary)',
                                                    border: 'none', padding: '0.3rem 0.8rem', borderRadius: '4px',
                                                    fontSize: '0.7rem', fontWeight: 600, cursor: 'pointer',
                                                    textTransform: 'capitalize', transition: 'all 0.2s'
                                                }}
                                            >
                                                {mode}
                                            </button>
                                        ))}
                                    </div>

                                    {/* Export PDF Button */}
                                    <button
                                        onClick={exportToPDF}
                                        disabled={isExporting}
                                        className="btn"
                                        style={{
                                            background: 'rgba(16, 185, 129, 0.2)', color: 'var(--accent-success)',
                                            padding: '0.4rem 0.8rem', fontSize: '0.8rem',
                                            border: '1px solid var(--accent-success)',
                                            opacity: isExporting ? 0.7 : 1
                                        }}
                                        title="Export as PDF"
                                    >
                                        <Download size={16} />
                                        {isExporting ? 'Generating...' : 'Export'}
                                    </button>

                                    {/* Export Interactive HTML Button */}
                                    <button
                                        onClick={exportToHTML}
                                        disabled={isExportingHTML}
                                        className="btn"
                                        style={{
                                            background: 'rgba(59, 130, 246, 0.2)', color: 'var(--accent-info, #3b82f6)',
                                            padding: '0.4rem 0.8rem', fontSize: '0.8rem',
                                            border: '1px solid var(--accent-info, #3b82f6)',
                                            opacity: isExportingHTML ? 0.7 : 1
                                        }}
                                        title="Export Interactive Plot (HTML)"
                                    >
                                        <BarChart2 size={16} />
                                        {isExportingHTML ? 'Generating...' : 'Interactive Plot'}
                                    </button>

                                    <button
                                        onClick={() => setIsMinimized(true)}
                                        className="btn"
                                        style={{
                                            background: 'rgba(255,255,255,0.05)', color: 'var(--text-primary)',
                                            padding: '0.4rem 0.8rem', fontSize: '0.8rem'
                                        }}
                                        title="Minimize Panel"
                                    >
                                        <Minimize2 size={16} /> Hide
                                    </button>
                                </div>
                            </div>

                            <div className="custom-scrollbar results-chart-container" style={{ overflowX: 'auto', paddingBottom: '0.5rem', flex: 1 }}>
                                <div style={{
                                    height: '350px', // Fixed height for Recharts stability
                                    minHeight: '220px',
                                    minWidth: 
                                        granularity === 'daily' ? '3000px' : 
                                        granularity === 'weekly' ? '1200px' : 
                                        // Monthly: Scaled by number of months to keep labels readable (min 100%)
                                        chartData.length > 12 ? `${chartData.length * 50}px` : '100%'
                                }}>
                                    <ResponsiveContainer width="100%" height="100%">
                                        <AreaChart data={chartData} margin={{ top: 10, right: 30, left: -10, bottom: 0 }}>
                                            <defs>
                                                <linearGradient id="salesGradLarge" x1="0" y1="0" x2="0" y2="1">
                                                    <stop offset="5%" stopColor="var(--accent-primary)" stopOpacity={0.6} />
                                                    <stop offset="95%" stopColor="var(--accent-primary)" stopOpacity={0} />
                                                </linearGradient>
                                            </defs>
                                            <XAxis
                                                dataKey="date"
                                                tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                                                axisLine={false}
                                                tickLine={false}
                                                minTickGap={granularity === 'daily' ? 40 : 30}
                                                tickFormatter={xAxisFormatter}
                                                dy={10}
                                            />
                                            <YAxis
                                                tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                                                axisLine={false} tickLine={false}
                                                domain={['auto', 'auto']}
                                                tickFormatter={v => v >= 1000 ? `£${(v / 1000).toFixed(1)}k` : `£${v}`}
                                                width={45}
                                            />
                                            <Tooltip
                                                cursor={{ stroke: 'rgba(255,255,255,0.1)', strokeWidth: 1, strokeDasharray: '3 3' }}
                                                contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', fontSize: '0.8rem' }}
                                                formatter={v => [`£${v.toLocaleString(undefined, { minimumFractionDigits: 2 })}`, 'Predicted Sales']}
                                                labelStyle={{ color: 'var(--text-primary)', marginBottom: '0.25rem', fontWeight: 600 }}
                                            />
                                            <Area
                                                type="monotone"
                                                dataKey="predicted_sales"
                                                stroke="var(--accent-primary)"
                                                strokeWidth={3}
                                                fillOpacity={1}
                                                fill="url(#salesGradLarge)"
                                                activeDot={{ r: 6, fill: 'var(--accent-primary)', stroke: '#fff', strokeWidth: 2 }}
                                                dot={{ r: 3, fill: 'var(--bg-primary)', stroke: 'var(--accent-primary)', strokeWidth: 1.5 }}
                                            />
                                        </AreaChart>
                                    </ResponsiveContainer>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* ── LOWER PANEL: 4-Column Data Grid ───────────────────────────── */}
                    <div className="results-grid">

                        {/* Col 1: Postcode Demographics */}
                        <div className="results-grid-col" style={{ borderRight: '1px solid var(--border-color)', paddingRight: '1.5rem' }}>
                            <CollapsiblePanel title="Postcode Demographics">
                                <KVTable rows={DEMO_ROWS} />
                            </CollapsiblePanel>

                            {stationRows.length > 0 && (
                                <CollapsiblePanel title="Transport Stations">
                                    <table style={TABLE}>
                                        <thead><tr><th style={TH}>Station</th><th style={THR}>Dist</th><th style={THR}>Type</th></tr></thead>
                                        <tbody>
                                            {stationRows.map((s, i) => (
                                                <tr key={i} style={i % 2 === 0 ? ROW_E : ROW_O}>
                                                    <td style={TDL}>{s.name}</td>
                                                    <td style={TDV}>{s.distance}</td>
                                                    <td style={TDV}>{s.type}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </CollapsiblePanel>
                            )}
                        </div>

                        {/* Col 2: Ethnicity / Religion / Age / Household */}
                        <div className="results-grid-col" style={{ borderRight: '1px solid var(--border-color)', paddingRight: '1.5rem' }}>
                            {hasNewFormat ? (
                                Object.entries(ethSections).map(([sectionName, rows]) => (
                                    rows && rows.length > 0 && (
                                        <CollapsiblePanel key={sectionName} title={sectionName} defaultOpen={sectionName === 'Ethnicity'}>
                                            <BadgeTable rows={rows} />
                                        </CollapsiblePanel>
                                    )
                                ))
                            ) : (
                                <CollapsiblePanel title="Demographics Breakdown">
                                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                        Detailed breakdown will appear on next refresh for this postcode.
                                    </p>
                                </CollapsiblePanel>
                            )}
                        </div>

                        {/* Col 3: Amenities + Occupation Part 1 */}
                        <div className="results-grid-col" style={{ borderRight: '1px solid var(--border-color)', paddingRight: '1.5rem' }}>
                            {restaurants.length > 0 && (
                                <CollapsiblePanel title={`Restaurants (${restaurants.length})`}>
                                    <PlaceTable items={restaurants} colName="Restaurant" />
                                </CollapsiblePanel>
                            )}
                            {pubs.length > 0 && (
                                <CollapsiblePanel title={`Pubs & Bars (${pubs.length})`} defaultOpen={false}>
                                    <PlaceTable items={pubs} colName="Pub / Bar" />
                                </CollapsiblePanel>
                            )}
                        </div>

                        {/* Col 4: Occupation Part 2 */}
                        <div className="results-grid-col">
                            {occRows.length > 0 && (
                                <CollapsiblePanel title="Occupation & Education" defaultOpen={true}>
                                    <BadgeTable rows={occRows} />
                                    {otherOccRows.length > 0 && <BadgeTable rows={otherOccRows} />}
                                </CollapsiblePanel>
                            )}
                        </div>
                    </div>
                </>
            )}

            {/* Hidden Report Template (Used for PDF Export) */}
            <ReportLayout ref={reportRef} result={result} />
        </div>
    )
}
