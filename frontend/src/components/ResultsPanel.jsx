import { BarChart, Bar, AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { TrendingUp, Users, Train, Briefcase } from 'lucide-react'

export default function ResultsPanel({ result }) {
    if (!result) return null

    const f = result.features

    // Prepare a tiny overview chart of demographic makeup
    const demoData = [
        { name: 'Working', value: f.working || 0, color: 'var(--accent-primary)' },
        { name: 'Unemployed', value: f.unemployed || 0, color: 'var(--accent-danger)' },
        { name: 'AB Class', value: f.ab || 0, color: 'var(--accent-success)' },
        { name: 'C1/C2 Class', value: f['c1/c2'] || 0, color: 'var(--accent-secondary)' },
        { name: 'DE Class', value: f.de || 0, color: 'var(--accent-warning)' }
    ].filter(d => d.value > 0)

    return (
        <div className="glass-panel animate-slide-up" style={{
            position: 'absolute',
            bottom: '2rem',
            right: '2rem',
            left: '2rem',
            padding: '2rem',
            display: 'grid',
            gridTemplateColumns: '1fr 2fr',
            gap: '2rem',
            zIndex: 1000,
        }}>

            {/* Left: Headline Prediction & 12 Month Chart */}
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', borderRight: '1px solid var(--border-color)', paddingRight: '2rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem', color: "var(--text-secondary)" }}>
                    <TrendingUp size={24} color="var(--accent-success)" />
                    <h2 style={{ fontSize: '1rem', fontWeight: 500, margin: 0 }}>Predicted Weekly Sales</h2>
                </div>
                <div className="value-highlight gradient-text" style={{ fontSize: '3.5rem', lineHeight: 1 }}>
                    {result.currency}{result.predicted_sales.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.5rem', marginBottom: '2rem' }}>
                    For {result.postcode}
                </p>

                {/* 12-Month Projection Chart */}
                {result.time_series && result.time_series.length > 0 && (
                    <div style={{ height: '350px', width: '100%', marginTop: 'auto' }}>
                        <h3 style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>12-Month Projection</h3>
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={result.time_series} margin={{ top: 5, right: 0, left: 0, bottom: 0 }}>
                                <defs>
                                    <linearGradient id="colorSales" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="var(--accent-primary)" stopOpacity={0.8} />
                                        <stop offset="95%" stopColor="var(--accent-primary)" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} minTickGap={30} />
                                <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} domain={['auto', 'auto']} tickFormatter={(value) => `£${(value / 1000).toFixed(1)}k`} width={50} />
                                <Tooltip
                                    contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', fontSize: '0.875rem' }}
                                    formatter={(value) => [`£${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, 'Weekly Sales']}
                                    labelStyle={{ color: 'var(--text-primary)' }}
                                />
                                <Area type="monotone" dataKey="predicted_sales" stroke="var(--accent-primary)" strokeWidth={3} fillOpacity={1} fill="url(#colorSales)" />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                )}
            </div>

            {/* Right: Key Scraped Features mapped into a cool grid */}
            <div>
                <h3 style={{ fontSize: '1rem', marginBottom: '1rem', color: 'var(--text-primary)' }}>Location Profile</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>

                    <div className="glass-card" style={{ padding: '0.75rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                            <Users size={16} /> <span style={{ fontSize: '0.75rem' }}>Population</span>
                        </div>
                        <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>
                            {(f.population || 0).toLocaleString()}
                        </div>
                    </div>

                    <div className="glass-card" style={{ padding: '0.75rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                            <Briefcase size={16} /> <span style={{ fontSize: '0.75rem' }}>Avg Income</span>
                        </div>
                        <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>
                            £{(f.avg_household_income || 0).toLocaleString()}
                        </div>
                    </div>

                    <div className="glass-card" style={{ padding: '0.75rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                            <Train size={16} /> <span style={{ fontSize: '0.75rem' }}>Transport Score</span>
                        </div>
                        <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>
                            {f.Transport_Accessibility_Score || 'N/A'}/10
                        </div>
                    </div>

                </div>

                {/* Mini Chart */}
                <div style={{ height: '100px', width: '100%' }}>
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={demoData} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
                            <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
                            <Tooltip
                                cursor={{ fill: 'rgba(255,255,255,0.05)' }}
                                contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', fontSize: '0.75rem' }}
                            />
                            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                                {demoData.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={entry.color} />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    )
}
