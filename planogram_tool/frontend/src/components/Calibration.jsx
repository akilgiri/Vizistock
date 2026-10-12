import React, { useState, useRef } from "react"
import axios from "axios"
import { Loader2 } from "lucide-react"

export default function Calibration({ file, onNext }) {
  const [points, setPoints] = useState([])
  const [loading, setLoading] = useState(false)
  const [draggingIdx, setDraggingIdx] = useState(null)

  const imgRef = useRef(null)
  const canvasRef = useRef(null)

  // --- CONFIGURATION ---
  const ZOOM_LEVEL = 3
  const LENS_SIZE = 180
  const OFFSET = 40

  // --- MOUSE MOVEMENT (Direct Canvas Rendering for Smoothness) ---
  const handleMouseMove = (e) => {
    if (!imgRef.current || !canvasRef.current || draggingIdx !== null) return

    const rect = imgRef.current.getBoundingClientRect()

    // 1. Cursor relative to image (for logic)
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top

    // 2. Bounds check
    if (x < 0 || y < 0 || x > rect.width || y > rect.height) {
      canvasRef.current.style.display = "none"
      return
    }

    // 3. Show Lens
    canvasRef.current.style.display = "block"

    // 4. Calculate Natural Coordinates for Pixel Mapping
    const scaleX = imgRef.current.naturalWidth / rect.width
    const scaleY = imgRef.current.naturalHeight / rect.height
    const naturalX = x * scaleX
    const naturalY = y * scaleY

    // 5. Position the Lens DOM Element
    let left = e.clientX + OFFSET
    let top = e.clientY + OFFSET

    if (left + LENS_SIZE > window.innerWidth)
      left = e.clientX - LENS_SIZE - OFFSET
    if (top + LENS_SIZE > window.innerHeight)
      top = e.clientY - LENS_SIZE - OFFSET

    canvasRef.current.style.left = `${left}px`
    canvasRef.current.style.top = `${top}px`

    // 6. Direct Canvas Draw (Bypasses React Render Cycle for Buttery Smooth Tracking)
    const ctx = canvasRef.current.getContext("2d")
    ctx.clearRect(0, 0, LENS_SIZE, LENS_SIZE)

    const sourceRadius = LENS_SIZE / ZOOM_LEVEL / 2

    ctx.drawImage(
      imgRef.current,
      naturalX - sourceRadius,
      naturalY - sourceRadius,
      sourceRadius * 2,
      sourceRadius * 2,
      0,
      0,
      LENS_SIZE,
      LENS_SIZE,
    )

    // 7. Draw Crosshairs
    ctx.strokeStyle = "#00FF00"
    ctx.lineWidth = 1.5
    ctx.beginPath()
    ctx.moveTo(LENS_SIZE / 2, 0)
    ctx.lineTo(LENS_SIZE / 2, LENS_SIZE)
    ctx.moveTo(0, LENS_SIZE / 2)
    ctx.lineTo(LENS_SIZE, LENS_SIZE / 2)
    ctx.stroke()
  }

  const handleImageClick = (e) => {
    if (draggingIdx !== null || !imgRef.current) return
    if (points.length >= 4) return

    const rect = imgRef.current.getBoundingClientRect()
    setPoints([
      ...points,
      {
        x: (e.clientX - rect.left) / rect.width,
        y: (e.clientY - rect.top) / rect.height,
      },
    ])
  }

  const handleDrag = (e) => {
    if (draggingIdx === null || !imgRef.current) return
    const rect = imgRef.current.getBoundingClientRect()
    const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
    const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height))

    const newPoints = [...points]
    newPoints[draggingIdx] = { x, y }
    setPoints(newPoints)
  }

  const submitCalibration = async () => {
    setLoading(true)
    const formData = new FormData()
    formData.append("image", file)

    const formattedPoints = points.map((p) => {
      if (!imgRef.current) return [0, 0]
      return [
        p.x * imgRef.current.naturalWidth,
        p.y * imgRef.current.naturalHeight,
      ]
    })

    formData.append("points", JSON.stringify(formattedPoints))

    try {
      const res = await axios.post(
        "http://localhost:8000/api/calibrate",
        formData,
      )
      onNext(res.data.warped_image, res.data.homography_matrix, formattedPoints)
    } catch (err) {
      console.error("Calibration Error:", err)
      alert("Failed to process calibration")
      setLoading(false)
    }
  }

  const imageURL = file ? URL.createObjectURL(file) : ""

  return (
    <div
      className="max-w-6xl mx-auto mt-6 animate-in fade-in"
      onMouseMove={handleDrag}
      onMouseUp={() => setDraggingIdx(null)}
    >
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-2xl font-bold text-white">Calibrate Corners</h2>
          <p className="text-slate-400">
            Click the 4 exact corners of the physical shelf space.
          </p>
        </div>
        <div className="flex gap-4">
          <button
            onClick={() => setPoints([])}
            className="px-4 py-2 bg-midnight-800 text-slate-300 rounded-lg hover:bg-midnight-700"
          >
            Reset Points
          </button>
          <button
            onClick={submitCalibration}
            disabled={points.length !== 4 || loading}
            // ADDED whitespace-nowrap and removed w-48 to prevent line breaking
            className="flex justify-center items-center px-6 py-2 min-w-50 whitespace-nowrap bg-accent-600 hover:bg-accent-500 text-white font-bold rounded-lg disabled:opacity-50 transition"
          >
            {loading ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              "Create Planogram"
            )}
          </button>
        </div>
      </div>

      <div className="flex justify-center w-full bg-midnight-900 border border-midnight-800 rounded-xl p-4 shadow-xl">
        <div
          className="relative inline-block cursor-crosshair select-none"
          onMouseLeave={() => {
            if (canvasRef.current) canvasRef.current.style.display = "none"
          }}
        >
          {imageURL && (
            <img
              ref={imgRef}
              src={imageURL}
              alt="Calibration"
              draggable={false}
              onClick={handleImageClick}
              onMouseMove={handleMouseMove}
              className="block max-h-[70vh] w-auto h-auto rounded shadow-lg border border-midnight-700"
            />
          )}

          {/* HTML5 Canvas Magnifier */}
          <canvas
            ref={canvasRef}
            width={LENS_SIZE}
            height={LENS_SIZE}
            className="fixed rounded-full border-2 border-white shadow-[0_0_20px_rgba(0,0,0,0.9)] pointer-events-none z-50 bg-black"
            style={{ display: "none" }}
          />

          {points.map((p, i) => (
            <div
              key={i}
              onMouseDown={(e) => {
                e.stopPropagation()
                setDraggingIdx(i)
              }}
              className={`absolute w-6 h-6 -ml-3 -mt-3 rounded-full flex items-center justify-center cursor-move transition-transform ${draggingIdx === i ? "scale-125 z-50" : "z-10"}`}
              style={{ left: `${p.x * 100}%`, top: `${p.y * 100}%` }}
            >
              <div className="w-3 h-3 bg-green-500 border-2 border-white rounded-full shadow-lg pointer-events-none" />
              <span className="absolute -top-6 text-white font-bold text-xs bg-black/50 px-1 rounded pointer-events-none">
                {i + 1}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
