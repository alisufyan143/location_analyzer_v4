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
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  const handlePredict = async (postcode) => {
    if (!postcode.trim()) {
      setError("Please enter a valid UK postcode.")
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await axios.post('http://127.0.0.1:8000/predict', {
        postcode: postcode
      }, { timeout: 300000 })  // 5 min – scraping pipeline takes 60-90s
      setResult(response.data)
    } catch (err) {
      console.error(err)
      setError(
        err.response?.data?.detail || "Failed to connect to the prediction server. Is FastAPI running?"
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app-container">
      {/* LEFT SIDEBAR: Forms and Controls */}
      <aside className="sidebar">
        <div className="header" style={{ marginBottom: "1rem" }}>
          <h1 className="gradient-text" style={{ fontSize: "1.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <MapPin size={28} color="var(--accent-primary)" />
            Location Analyzer
          </h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginTop: "0.25rem" }}>
            AI-powered retail sales forecasting
          </p>
        </div>

        <PredictionForm onPredict={handlePredict} isLoading={loading} />

        {error && (
          <div className="glass-card animate-slide-up" style={{ padding: "1rem", borderLeft: "4px solid var(--accent-danger)", backgroundColor: "rgba(239, 68, 68, 0.1)" }}>
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
        {loading && <ProcessingOverlay />}

        {/* Floating results panel that appears after prediction */}
        {result && !loading && (
          <ResultsPanel result={result} />
        )}
      </main>
    </div>
  )
}

export default App
