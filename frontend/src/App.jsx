import { useState } from 'react'
import axios from 'axios'
import 'leaflet/dist/leaflet.css'
import { MapPin, AlertCircle } from 'lucide-react'
import PredictionForm from './components/PredictionForm'
import MapArea from './components/MapArea'
import ResultsPanel from './components/ResultsPanel'
import ProcessingOverlay from './components/ProcessingOverlay'

function App() {
  const [loading, setLoading] = useState(false)
  const [requestComplete, setRequestComplete] = useState(false) // backend finished; show 100% then hide
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

  const handlePredict = async (postcode, branchName = "", dateRange = {}) => {
    if (!postcode.trim()) {
      setError("Please enter a valid UK postcode.")
      return
    }

    setLoading(true)
    setRequestComplete(false)
    setError(null)
    setResult(null)

    try {
      const response = await axios.post(`${apiBase}/predict`, {
        postcode: postcode,
        branch_name: branchName,
        from_month: dateRange.from_month || null,
        from_year: dateRange.from_year || null,
        to_month: dateRange.to_month || null,
        to_year: dateRange.to_year || null,
        inflate_sales: dateRange.inflate_sales ?? false,
        inflate_amount: dateRange.inflate_amount ?? null,
        is_logistics_strike: dateRange.is_logistics_strike ?? false,
        is_delivery_crackdown: dateRange.is_delivery_crackdown ?? false,
        inferred_brand_override: dateRange.inferred_brand_override ?? null,
        days_since_open: dateRange.days_since_open ?? 1000,
      }, {
        timeout: 300000,
        headers: { 'ngrok-skip-browser-warning': 'true' }
      })
      setResult(response.data)
      setRequestComplete(true)
      setTimeout(() => {
        setLoading(false)
        setRequestComplete(false)
      }, 600)
    } catch (err) {
      console.error(err)
      setError(
        err.response?.data?.detail || "Failed to connect to the prediction server. Is FastAPI running?"
      )
      setLoading(false)
    }
  }


  return (
    <div className="app-container">
      {/* LEFT SIDEBAR: Forms and Controls */}
      <aside className="sidebar">
        <div className="header">
          <h1 className="gradient-text" style={{ fontSize: "1.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <MapPin size={28} color="var(--accent-primary)" />
            Location Analyzer
          </h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginTop: "0.25rem" }}>
            AI-powered retail sales forecasting
          </p>
        </div>

        <PredictionForm onPredict={handlePredict} isLoading={loading} />
        
        {!result && !loading && !error && (
          <div className="glass-card animate-slide-up" style={{ padding: "1.5rem", textAlign: "center", marginTop: "1rem" }}>
            <div style={{ background: "rgba(59, 130, 246, 0.1)", width: "48px", height: "48px", borderRadius: "12px", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 1rem" }}>
              <MapPin size={24} color="var(--accent-primary)" />
            </div>
            <h3 style={{ fontSize: "0.95rem", marginBottom: "0.5rem" }}>Ready to Analyze</h3>
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", lineHeight: "1.4" }}>
              Enter a UK postcode to start your deep-dive location analysis and sales forecast.
            </p>
          </div>
        )}

        {error && (
          <div className="glass-card animate-slide-up" style={{ padding: "1rem", borderLeft: "4px solid var(--accent-danger)", backgroundColor: "rgba(239, 68, 68, 0.1)", marginTop: "1rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--accent-danger)", fontWeight: "600", marginBottom: "0.25rem" }}>
              <AlertCircle size={18} />
              Prediction Error
            </div>
            <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>{error}</p>
          </div>
        )}

      </aside>

      {/* RIGHT MAIN PLATFORM: Map and Overlays */}
      <main className="main-content" style={{ position: 'relative' }}>
        <MapArea result={result} />

        {/* The beautiful glassmorphic 90-second loading overlay */}
        {loading && <ProcessingOverlay completed={requestComplete} />}

        {/* Floating results panel that appears after prediction */}
        {result && !loading && (
          <ResultsPanel result={result} apiBase={apiBase} />
        )}
      </main>
    </div>
  )
}

export default App
