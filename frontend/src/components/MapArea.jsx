import { useEffect } from 'react'
import { MapContainer, TileLayer, Marker, Popup, Circle, useMap } from 'react-leaflet'

// Component to dynamically recenter the map when a new prediction happens
function MapUpdater({ center }) {
    const map = useMap()
    useEffect(() => {
        if (center && center[0] !== 0) {
            map.flyTo(center, 14, { duration: 1.5 })
        }
    }, [center, map])
    return null
}

export default function MapArea({ result }) {
    // Default center: London
    const defaultCenter = [51.505, -0.09]

    // Note: Since we are scraping postcodes, we'd ideally have returned lat/lon from the backend.
    // For this beautiful demo, we will use a purely visual map center. A premium addition in the future
    // is adding a free Geocoding lookup to drop the pin perfectly.
    // For now, let's pretend the backend returned [53.4808, -2.2426] (Manchester) as a dummy for visual testing
    // if not supplied.
    const mapCenter = result?.features?.lat ? [result.features.lat, result.features.lng] : defaultCenter
    const isDefault = !result

    return (
        <div style={{ height: '100%', width: '100%', position: 'relative' }}>



            <MapContainer
                center={defaultCenter}
                zoom={11}
                scrollWheelZoom={true}
                style={{ height: '100%', width: '100%' }}
                zoomControl={false}
            >
                <MapUpdater center={mapCenter} />

                {/* Dark Mode Tile Layer from CartoDB */}
                <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
                    url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                />

                {result && result.features && result.features.lat ? (
                    <>
                        <Marker position={[result.features.lat, result.features.lng]}>
                            <Popup>
                                <div style={{ color: '#000' }}>
                                    <strong>{result.postcode}</strong><br />
                                    Target Location
                                </div>
                            </Popup>
                        </Marker>

                        {/* Draw a subtle 1 mile radius circle representing our catchment area */}
                        <Circle
                            center={[result.features.lat, result.features.lng]}
                            pathOptions={{ fillColor: 'var(--accent-primary)', color: 'var(--accent-primary)', opacity: 0.5, fillOpacity: 0.1 }}
                            radius={1609} // 1 mile in meters
                        />
                    </>
                ) : null}
            </MapContainer>
        </div>
    )
}
