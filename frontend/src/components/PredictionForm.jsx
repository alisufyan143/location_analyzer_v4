import { useState } from 'react'
import { Search, Info } from 'lucide-react'

export default function PredictionForm({ onPredict, isLoading }) {
    const [postcode, setPostcode] = useState('')

    const handleSubmit = (e) => {
        e.preventDefault()
        onPredict(postcode)
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

            <button
                type="submit"
                className="btn btn-primary"
                style={{ width: "100%", marginTop: "1rem" }}
                disabled={isLoading || !postcode.trim()}
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

            <div className="glass-card" style={{ marginTop: "2rem", padding: "1rem" }}>
                <h3 style={{ fontSize: "0.875rem", display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem", color: "var(--text-secondary)" }}>
                    <Info size={16} />
                    How it works
                </h3>
                <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    Simply enter a valid UK postcode. The system will automatically scrape live demographic, affluence, and transport data for this area and feed it into the unified Median Ensemble ML model (combining XGBoost, LightGBM, CatBoost, and Random Forest) to predict fast food retail sales.
                </p>
            </div>
        </form>
    )
}
