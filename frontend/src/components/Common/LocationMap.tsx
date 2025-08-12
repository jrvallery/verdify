import { useEffect, useRef } from "react"

type LocationMapProps = {
  lat?: number
  lng?: number
  zoom?: number
  height?: number
  readOnly?: boolean
  onChange?: (lat?: number, lng?: number) => void
}

const loadLeaflet = (() => {
  let loaded: Promise<void> | null = null
  return () => {
    if (loaded) return loaded
    loaded = new Promise<void>((resolve, reject) => {
      const existingCss = document.querySelector('link[data-leaflet]')
      if (!existingCss) {
        const link = document.createElement("link")
        link.rel = "stylesheet"
        link.href = "https://unpkg.com/leaflet/dist/leaflet.css"
        link.setAttribute("data-leaflet", "1")
        document.head.appendChild(link)
      }
      if ((window as any).L) {
        resolve()
        return
      }
      const script = document.createElement("script")
      script.src = "https://unpkg.com/leaflet/dist/leaflet.js"
      script.async = true
      script.onload = () => resolve()
      script.onerror = () => reject(new Error("Failed to load Leaflet"))
      document.body.appendChild(script)
    })
    return loaded
  }
})()

export function LocationMap({
  lat,
  lng,
  zoom = 4,
  height = 360,
  readOnly = false,
  onChange,
}: LocationMapProps) {
  const mapRef = useRef<HTMLDivElement | null>(null)
  const mapInstance = useRef<any>(null)
  const markerRef = useRef<any>(null)

  useEffect(() => {
    let disposed = false
    if (!mapRef.current) return

    loadLeaflet()
      .then(() => {
        if (disposed || !mapRef.current) return
        const L = (window as any).L

        // Initialize map once
        if (!mapInstance.current) {
          const initialLat = lat ?? 39.5
          const initialLng = lng ?? -98.35
          const initialZoom = lat !== undefined && lng !== undefined ? 12 : zoom

          mapInstance.current = L.map(mapRef.current).setView(
            [initialLat, initialLng],
            initialZoom,
          )

          const streetLayer = L.tileLayer(
            "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            { attribution: "© OpenStreetMap contributors" },
          )
          const satelliteLayer = L.tileLayer(
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            { attribution: "Tiles © Esri" },
          )

          streetLayer.addTo(mapInstance.current)
          L.control
            .layers({ "Street View": streetLayer, "Satellite View": satelliteLayer }, {})
            .addTo(mapInstance.current)

          if (lat !== undefined && lng !== undefined) {
            markerRef.current = L.marker([lat, lng]).addTo(mapInstance.current)
          }

          if (!readOnly) {
            mapInstance.current.on("click", (e: any) => {
              const newLat = e.latlng.lat
              const newLng = e.latlng.lng
              if (markerRef.current) {
                mapInstance.current.removeLayer(markerRef.current)
              }
              markerRef.current = L.marker([newLat, newLng]).addTo(mapInstance.current)
              onChange?.(newLat, newLng)
            })
          }
        } else {
          // Update view/marker if props changed
          if (lat !== undefined && lng !== undefined) {
            mapInstance.current.setView([lat, lng], 12)
            if (markerRef.current) {
              mapInstance.current.removeLayer(markerRef.current)
            }
            markerRef.current = L.marker([lat, lng]).addTo(mapInstance.current)
          }
        }
      })
      .catch(() => {
        // optional map fail: ignore
      })

    return () => {
      disposed = true
    }
    // Intentionally not including zoom/readOnly/onChange to avoid reinit churn
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lat, lng])

  return (
    <div
      ref={mapRef}
      style={{
        height,
        borderRadius: 8,
        overflow: "hidden",
        border: "1px solid var(--chakra-colors-gray-200)",
      }}
    />
  )
}
