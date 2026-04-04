import { useState } from 'react'
import { Search, Info, CalendarRange } from 'lucide-react'

const MONTHS = [
    { value: 1, label: 'January' }, { value: 2, label: 'February' },
    { value: 3, label: 'March' }, { value: 4, label: 'April' },
    { value: 5, label: 'May' }, { value: 6, label: 'June' },
    { value: 7, label: 'July' }, { value: 8, label: 'August' },
    { value: 9, label: 'September' }, { value: 10, label: 'October' },
    { value: 11, label: 'November' }, { value: 12, label: 'December' },
]

// Generate year options: 2010 → 2030
const YEARS = Array.from({ length: 21 }, (_, i) => 2010 + i)

const SELECT_STYLE = {
    background: 'var(--bg-secondary)',
    border: '1px solid var(--border-color)',
    borderRadius: '8px',
    color: 'var(--text-primary)',
    padding: '0.5rem 0.6rem',
    fontSize: '0.82rem',
    flex: 1,
    cursor: 'pointer',
    outline: 'none',
}

export default function PredictionForm({ onPredict, isLoading }) {
    const [postcode, setPostcode] = useState('')
    const [branchName, setBranchName] = useState('')

    // Date range state — defaults to current month → +1 year
    const now = new Date()
    const [fromMonth, setFromMonth] = useState(now.getMonth() + 1)
    const [fromYear, setFromYear] = useState(now.getFullYear())
    const [toMonth, setToMonth] = useState(now.getMonth() + 1)
    const [toYear, setToYear] = useState(now.getFullYear() + 1)

    // Validation: To must be after From
    const fromTotal = fromYear * 12 + fromMonth
    const toTotal = toYear * 12 + toMonth
    const dateError = toTotal <= fromTotal
        ? '"To" must be after "From".'
        : null

    const handleSubmit = (e) => {
        e.preventDefault()
        if (dateError) return
        onPredict(postcode, branchName, {
            from_month: fromMonth, from_year: fromYear,
            to_month: toMonth, to_year: toYear,
            inflate_sales: false,
            inflate_amount: null,
            // V4 Advanced Defaults (Zero-Input AI)
            is_logistics_strike: false,
            is_delivery_crackdown: false,
            inferred_brand_override: null,
            days_since_open: 1000
        })
    }

    return (
        <form onSubmit={handleSubmit} className="form-container">

            <div className="input-group">
                <label className="label">Postcode (Required)</label>
                <input
                    type="text"
                    className="input-field"
                    placeholder="e.g. M1 1AF"
                    value={postcode}
                    onChange={(e) => setPostcode(e.target.value)}
                    required
                    disabled={isLoading}
                />
            </div>

            <div className="input-group" style={{ marginTop: '1rem' }}>
                <label className="label">Branch Name (Optional)</label>
                <input
                    type="text"
                    className="input-field"
                    placeholder="e.g. Pepe's Piri Piri"
                    value={branchName}
                    onChange={(e) => setBranchName(e.target.value)}
                    disabled={isLoading}
                />
            </div>

            {/* ── Prediction Date Range ─────────────────────────────────────── */}
            <div className="input-group" style={{ marginTop: '1rem' }}>
                <label className="label" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <CalendarRange size={14} color="var(--accent-primary)" />
                    Prediction Range
                </label>

                {/* FROM row */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.4rem' }}>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', width: '28px' }}>From</span>
                    <select
                        value={fromMonth}
                        onChange={(e) => setFromMonth(Number(e.target.value))}
                        disabled={isLoading}
                        style={SELECT_STYLE}
                    >
                        {MONTHS.map(m => (
                            <option key={m.value} value={m.value}>{m.label}</option>
                        ))}
                    </select>
                    <select
                        value={fromYear}
                        onChange={(e) => setFromYear(Number(e.target.value))}
                        disabled={isLoading}
                        style={{ ...SELECT_STYLE, flex: 'none', width: '80px' }}
                    >
                        {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
                    </select>
                </div>

                {/* TO row */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.4rem' }}>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', width: '28px' }}>To</span>
                    <select
                        value={toMonth}
                        onChange={(e) => setToMonth(Number(e.target.value))}
                        disabled={isLoading}
                        style={SELECT_STYLE}
                    >
                        {MONTHS.map(m => (
                            <option key={m.value} value={m.value}>{m.label}</option>
                        ))}
                    </select>
                    <select
                        value={toYear}
                        onChange={(e) => setToYear(Number(e.target.value))}
                        disabled={isLoading}
                        style={{ ...SELECT_STYLE, flex: 'none', width: '80px' }}
                    >
                        {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
                    </select>
                </div>

                {/* Validation error */}
                {dateError && (
                    <p style={{ fontSize: '0.72rem', color: 'var(--accent-danger)', marginTop: '0.35rem' }}>
                        ⚠ {dateError}
                    </p>
                )}
            </div>

            <button
                type="submit"
                className="btn btn-primary"
                style={{ width: '100%', marginTop: '1.5rem' }}
                disabled={isLoading || !postcode.trim() || !!dateError}
            >
                {isLoading ? (
                    <>
                        <div className="spinner"></div>
                        Analyzing Location...
                    </>
                ) : (
                    <>
                        <Search size={18} />
                        Generate Prediction
                    </>
                )}
            </button>

            <div className="glass-card" style={{ marginTop: '1.25rem', padding: '1rem' }}>
                <h3 style={{ fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>
                    <Info size={16} />
                    How it works
                </h3>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Enter a valid UK postcode and select your desired forecast window. The system resolves deep demographic and POI data from the V4 ensemble database and feeds it into our SciPy-optimized 3-Model Meta-Ensemble (XGBoost, ExtraTrees, TabNet) to forecast daily fast-food retail sales across your chosen range.
                </p>
            </div>
        </form>
    )
}
