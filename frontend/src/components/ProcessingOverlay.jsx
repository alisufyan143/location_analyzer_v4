import { useState, useEffect } from 'react'
import { Loader2, Database, Map, Cpu, CheckCircle } from 'lucide-react'

const steps = [
    { text: "Checking saved data & fetching postcode...", icon: Database, delay: 0 },
    { text: "Extracting demographics (Nomis & Doogal)...", icon: UsersIcon, delay: 15 },
    { text: "Scanning transport & amenities...", icon: Map, delay: 40 },
    { text: "Running ML ensemble (XGBoost & LightGBM)...", icon: Cpu, delay: 65 },
    { text: "Finalizing 12‑month forecast...", icon: CheckCircle, delay: 85 }
]
const completedStep = { text: "Complete!", icon: CheckCircle }

function UsersIcon(props) {
    return (
        <svg
            {...props}
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
    )
}

export default function ProcessingOverlay({ completed = false }) {
    const [progress, setProgress] = useState(0)
    const [currentStepIndex, setCurrentStepIndex] = useState(0)

    useEffect(() => {
        if (completed) return
        // Estimate progress over ~2 min so bar doesn't sit at 99% for long when backend is slow
        const DURATION_MS = 120000
        const intervalTime = 100
        const increment = (100 / (DURATION_MS / intervalTime))

        const timer = setInterval(() => {
            setProgress(p => {
                const nextProgress = Math.min(p + increment, 99) // cap 99% until backend completes

                const stepIndex = steps.findLastIndex(s => nextProgress >= s.delay)
                if (stepIndex !== -1) setCurrentStepIndex(stepIndex)
                return nextProgress
            })
        }, intervalTime)
        return () => clearInterval(timer)
    }, [completed])

    const isComplete = completed
    const displayProgress = isComplete ? 100 : progress
    const currentStep = isComplete ? completedStep : steps[currentStepIndex]
    const CurrentIcon = currentStep.icon

    return (
        <div style={{
            position: 'absolute',
            top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(15, 23, 42, 0.85)',
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
            zIndex: 9999,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            animation: 'fadeIn 0.5s ease-out'
        }}>
            <div className="glass-panel" style={{
                padding: '3rem',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                maxWidth: '500px',
                width: '90%',
                textAlign: 'center',
                boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5), inset 0 0 0 1px rgba(255, 255, 255, 0.1)'
            }}>

                <div style={{ position: 'relative', marginBottom: '2rem' }}>
                    <div className="pulse-ring" style={{
                        position: 'absolute',
                        top: -10, left: -10, right: -10, bottom: -10,
                        border: '2px solid var(--accent-primary)',
                        borderRadius: '50%',
                        animation: 'pulse-ring 2s cubic-bezier(0.215, 0.61, 0.355, 1) infinite'
                    }} />
                    <div style={{
                        background: 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))',
                        borderRadius: '50%',
                        width: '64px', height: '64px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: 'white'
                    }}>
                        <CurrentIcon size={32} className={!isComplete && currentStepIndex < 4 ? 'spinning-slow' : ''} />
                    </div>
                </div>

                <h2 style={{ fontSize: '1.5rem', marginBottom: '0.5rem', color: 'var(--text-primary)' }}>
                    {isComplete ? 'Analysis complete' : 'Analyzing location data'}
                </h2>

                <p style={{
                    color: 'var(--accent-primary)',
                    fontWeight: 500,
                    minHeight: '24px',
                    marginBottom: '2rem',
                    transition: 'all 0.3s ease'
                }}>
                    {currentStep.text}
                </p>

                <div style={{ width: '100%', marginBottom: '0.5rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                        <span>Progress</span>
                        <span style={{ fontVariantNumeric: 'tabular-nums' }}>{Math.floor(displayProgress)}%</span>
                    </div>
                    <div style={{
                        height: '6px',
                        width: '100%',
                        background: 'rgba(255, 255, 255, 0.1)',
                        borderRadius: '999px',
                        overflow: 'hidden'
                    }}>
                        <div style={{
                            height: '100%',
                            width: `${displayProgress}%`,
                            background: 'linear-gradient(90deg, var(--accent-primary), var(--accent-secondary))',
                            borderRadius: '999px',
                            transition: 'width 0.1s linear',
                            boxShadow: '0 0 10px var(--accent-primary)'
                        }} />
                    </div>
                </div>

                {!isComplete && (
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '1.5rem' }}>
                        Backend is fetching data and running the model. This usually takes 1–2 minutes. Please do not refresh.
                    </p>
                )}
            </div>
        </div>
    )
}
