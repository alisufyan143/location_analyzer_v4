import React, { forwardRef } from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

const ReportLayout = forwardRef(({ result }, ref) => {
    if (!result) return null;

    const f = result.features;
    const weeklyData = result.time_series?.weekly || [];
    const monthlyData = result.time_series?.monthly || [];

    // Address formatting
    const parts = [f.ward, f.district, f.region].filter(Boolean);
    const addressStr = parts.length > 0 ? parts.join(', ') : 'Location Data Unavailable';

    // ── Additional Data Parsing ──
    const dd = result.display_data || {};
    const affluence = dd.affluence || {};

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
    ];
    const occupation = dd.occupation || {};
    const occRows = OCCI_LABELS
        .filter(k => occupation[k] !== undefined)
        .map(k => ({ name: k.replace(/\b\w/g, c => c.toUpperCase()), pct: occupation[k] }));
    const otherOccRows = Object.entries(occupation)
        .filter(([k]) => !OCCI_LABELS.includes(k))
        .map(([k, v]) => ({ name: k.replace(/\b\w/g, c => c.toUpperCase()), pct: v }));

    const ethnicity = dd.ethnicity || {};
    const ethSections = ethnicity.sections || {};
    const hasNewFormat = !!ethnicity.sections;

    const transport = dd.transport || {};
    const stations = transport.stations || [];
    const stationRows = stations.map(s => ({
        name: s.name,
        distance: `${s.distance} mi`,
        type: s.type,
    }));

    const amenities = dd.amenities || {};
    const restaurants = amenities.restaurants || [];
    const pubs = amenities.pubs || [];

    // Formatter
    const fmtPct = (v) => {
        if (v === null || v === undefined) return '—';
        if (v <= 1.0) return `${(v * 100).toFixed(1)}%`;
        return `${Number(v).toFixed(1)}%`;
    };

    const ReportTable = ({ title, columns, data }) => {
        if (!data || data.length === 0) return null;
        return (
            <div style={{ marginBottom: '30px' }}>
                <h3 style={{ fontSize: '18px', marginBottom: '15px', color: '#f8fafc' }}>{title} ({data.length})</h3>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px', background: 'rgba(30, 41, 59, 0.3)', borderRadius: '8px', overflow: 'hidden' }}>
                    <thead>
                        <tr style={{ background: 'rgba(255,255,255,0.1)' }}>
                            {columns.map((col, idx) => (
                                <th key={idx} style={{ padding: '10px 15px', textAlign: col.align || 'left', color: '#94a3b8', width: col.width }}>
                                    {col.header}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {data.map((row, rowIdx) => (
                            <tr key={rowIdx} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                {columns.map((col, colIdx) => (
                                    <td key={colIdx} style={{ padding: '10px 15px', textAlign: col.align || 'left', fontWeight: col.bold ? 'bold' : 'normal', color: col.color || 'inherit' }}>
                                        {col.accessor(row)}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    };

    return (
        <div
            ref={ref}
            style={{
                position: 'absolute',
                top: '-9999px',
                left: '-9999px',
                width: '1200px', // Wider width to comfortably fit data
                background: '#0f172a', // Match app background
                color: '#f8fafc',
                padding: '60px',
                fontFamily: "'Inter', sans-serif"
            }}
        >
            {/* Header */}
            <div style={{ borderBottom: '2px solid rgba(255,255,255,0.1)', paddingBottom: '20px', marginBottom: '30px' }}>
                <h1 style={{ fontFamily: "'Outfit', sans-serif", fontSize: '32px', margin: 0, color: '#3b82f6' }}>
                    Location Predictor Report
                </h1>
                <h2 style={{ fontSize: '24px', margin: '10px 0 5px 0' }}>{result.postcode}</h2>
                <p style={{ color: '#94a3b8', margin: 0 }}>{addressStr}</p>
            </div>

            {/* KPI */}
            <div style={{ marginBottom: '40px' }}>
                <p style={{ color: '#94a3b8', textTransform: 'uppercase', fontSize: '12px', fontWeight: 'bold' }}>Predicted First Month Sales</p>
                <div style={{ fontSize: '48px', fontWeight: 'bold', color: '#10b981' }}>
                    {result.currency}{result.predicted_sales.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </div>
            </div>

            {/* Graphs Container */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '40px', marginBottom: '40px' }}>
                {/* Monthly Chart */}
                <div style={{ background: 'rgba(30, 41, 59, 0.5)', padding: '20px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.1)' }}>
                    <h3 style={{ fontSize: '18px', marginBottom: '15px' }}>12-Month Forecast Curve</h3>
                    <div style={{ height: '300px' }}>
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={monthlyData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                                <XAxis dataKey="date" tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={false} tickLine={false} dy={10} />
                                <YAxis tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={false} tickLine={false} width={60} tickFormatter={v => v >= 1000 ? `£${(v / 1000).toFixed(1)}k` : `£${v}`} />
                                <Area type="monotone" dataKey="predicted_sales" stroke="#3b82f6" strokeWidth={3} fillOpacity={0.2} fill="#3b82f6" />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Weekly Chart */}
                <div style={{ background: 'rgba(30, 41, 59, 0.5)', padding: '20px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.1)' }}>
                    <h3 style={{ fontSize: '18px', marginBottom: '15px' }}>52-Week Forecast Trend</h3>
                    <div style={{ height: '300px' }}>
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={weeklyData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                                <XAxis dataKey="date" tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={false} tickLine={false} minTickGap={50} dy={10} />
                                <YAxis tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={false} tickLine={false} width={60} tickFormatter={v => v >= 1000 ? `£${(v / 1000).toFixed(1)}k` : `£${v}`} />
                                <Area type="monotone" dataKey="predicted_sales" stroke="#8b5cf6" strokeWidth={3} fillOpacity={0.2} fill="#8b5cf6" />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>

            {/* Monthly Data Table */}
            <div style={{ marginBottom: '40px' }}>
                <h3 style={{ fontSize: '18px', marginBottom: '15px', color: '#f8fafc' }}>Raw Monthly Predictions</h3>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px', background: 'rgba(30, 41, 59, 0.3)', borderRadius: '8px', overflow: 'hidden' }}>
                    <thead>
                        <tr style={{ background: 'rgba(255,255,255,0.1)' }}>
                            <th style={{ padding: '12px 20px', textAlign: 'left', color: '#94a3b8', width: '50%' }}>Month</th>
                            <th style={{ padding: '12px 20px', textAlign: 'right', color: '#94a3b8', width: '50%' }}>Predicted Sales</th>
                        </tr>
                    </thead>
                    <tbody>
                        {monthlyData.map((d, i) => (
                            <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                <td style={{ padding: '12px 20px' }}>{d.date}</td>
                                <td style={{ padding: '12px 20px', textAlign: 'right', fontWeight: 'bold' }}>
                                    {result.currency}{d.predicted_sales.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Demographics Table */}
            <div>
                <h3 style={{ fontSize: '18px', marginBottom: '15px', color: '#f8fafc' }}>Key Demographics</h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                        <tbody>
                            <tr>
                                <td style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: '#94a3b8' }}>Population</td>
                                <td style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', textAlign: 'right', fontWeight: 'bold' }}>{Number(f.population).toLocaleString()}</td>
                            </tr>
                            <tr>
                                <td style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: '#94a3b8' }}>Households</td>
                                <td style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', textAlign: 'right', fontWeight: 'bold' }}>{Number(f.households).toLocaleString()}</td>
                            </tr>
                            <tr>
                                <td style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: '#94a3b8' }}>Avg Income</td>
                                <td style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', textAlign: 'right', fontWeight: 'bold' }}>£{Number(f.avg_household_income).toLocaleString()}</td>
                            </tr>
                            <tr>
                                <td style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: '#94a3b8' }}>Transport Score</td>
                                <td style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', textAlign: 'right', fontWeight: 'bold' }}>{f.Transport_Accessibility_Score}/9</td>
                            </tr>
                        </tbody>
                    </table>

                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                        <tbody>
                            <tr>
                                <td style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: '#94a3b8' }}>AB Class (High)</td>
                                <td style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', textAlign: 'right', fontWeight: 'bold', color: '#2ecc71' }}>{fmtPct(f.ab)}</td>
                            </tr>
                            <tr>
                                <td style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: '#94a3b8' }}>C1/C2 Class (Mid)</td>
                                <td style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', textAlign: 'right', fontWeight: 'bold', color: '#3498db' }}>{fmtPct(f['c1/c2'])}</td>
                            </tr>
                            <tr>
                                <td style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: '#94a3b8' }}>DE Class (Low)</td>
                                <td style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', textAlign: 'right', fontWeight: 'bold', color: '#e74c3c' }}>{fmtPct(f.de)}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Additional Tables Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '30px', marginTop: '40px' }}>
                {/* Left Column */}
                <div>
                    <ReportTable
                        title="Transport Stations"
                        data={stationRows}
                        columns={[
                            { header: 'Station', accessor: r => r.name, width: '60%' },
                            { header: 'Dist', accessor: r => r.distance, align: 'right', width: '20%' },
                            { header: 'Type', accessor: r => r.type, align: 'right', width: '20%' }
                        ]}
                    />

                    <ReportTable
                        title="Restaurants"
                        data={restaurants}
                        columns={[
                            { header: 'Restaurant', accessor: r => r.name, width: '70%' },
                            { header: 'Distance', accessor: r => `${r.distance} yards`, align: 'right', width: '30%' }
                        ]}
                    />

                    <ReportTable
                        title="Pubs & Bars"
                        data={pubs}
                        columns={[
                            { header: 'Pub / Bar', accessor: r => r.name, width: '70%' },
                            { header: 'Distance', accessor: r => `${r.distance} yards`, align: 'right', width: '30%' }
                        ]}
                    />
                </div>

                {/* Right Column */}
                <div>
                    <ReportTable
                        title="Occupation & Education"
                        data={occRows}
                        columns={[
                            { header: 'Category', accessor: r => r.name, width: '70%' },
                            { header: '%', accessor: r => `${r.pct}%`, align: 'right', width: '30%', bold: true }
                        ]}
                    />

                    {hasNewFormat ? (
                        Object.entries(ethSections).map(([secName, rows]) => (
                            <ReportTable
                                key={secName}
                                title={secName}
                                data={rows}
                                columns={[
                                    { header: 'Category', accessor: r => r.name, width: '70%' },
                                    { header: '%', accessor: r => `${r.pct}%`, align: 'right', width: '30%', bold: true }
                                ]}
                            />
                        ))
                    ) : (
                        <ReportTable
                            title="Ethnicity"
                            data={Object.entries(ethnicity.details || {}).map(([k, v]) => ({ name: k, pct: v }))}
                            columns={[
                                { header: 'Category', accessor: r => r.name, width: '70%' },
                                { header: '%', accessor: r => `${r.pct}%`, align: 'right', width: '30%', bold: true }
                            ]}
                        />
                    )}
                </div>
            </div>
        </div>
    );
});

export default ReportLayout;
