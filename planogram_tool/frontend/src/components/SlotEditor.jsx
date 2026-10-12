import React, { useState, useRef, useEffect, useCallback } from "react"
import axios from "axios"
import {
  GripVertical,
  Ruler,
  CheckCircle,
  RefreshCw,
  Cloud,
  HardDrive,
} from "lucide-react"

const VALID_CLASSES = ["can", "bottle", "box", "bag", "other"]

export default function SlotEditor({
  shelfId,
  warpedImage,
  matrix,
  sourcePoints,
  dimensions,
  onComplete,
}) {
  const [dividers, setDividers] = useState([0.33, 0.66])
  const [slots, setSlots] = useState({})
  const [isDragging, setIsDragging] = useState(null)
  const [saveStatus, setSaveStatus] = useState("idle")
  const [displayUnit, setDisplayUnit] = useState(dimensions?.unit || "in")

  const didDragRef = useRef(false)
  const imgContainerRef = useRef(null)

  const getDisplayWidth = useCallback(
    (pctWidth) => {
      let rawValue = pctWidth * dimensions.width
      if (dimensions.unit === "cm" && displayUnit === "in") rawValue /= 2.54
      if (dimensions.unit === "in" && displayUnit === "cm") rawValue *= 2.54
      return rawValue.toFixed(1)
    },
    [dimensions.width, dimensions.unit, displayUnit],
  )

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSlots((prevSlots) => {
      const cuts = [0.0, ...[...dividers].sort((a, b) => a - b), 1.0]
      const newSlots = { ...prevSlots }

      for (let i = 0; i < cuts.length - 1; i++) {
        const key = `slot_${i + 1}`

        if (!newSlots[key]) {
          newSlots[key] = {
            name: "",
            classes: [],
            threshold: 1,
          }
        }

        newSlots[key].x_start = cuts[i]
        newSlots[key].x_end = cuts[i + 1]
        newSlots[key].realWidth = getDisplayWidth(cuts[i + 1] - cuts[i])
      }

      Object.keys(newSlots).forEach((k) => {
        const idx = parseInt(k.split("_")[1])
        if (idx > cuts.length - 1) delete newSlots[k]
      })

      return newSlots
    })
  }, [dividers, getDisplayWidth])

  const applyPreset = (count) => {
    if (count === 1) {
      setDividers([])
      return
    }
    const newDivs = []
    for (let i = 1; i < count; i++) {
      newDivs.push(i / count)
    }
    setDividers(newDivs)
  }

  const toggleClass = (slotKey, cls) => {
    const currentClasses = slots[slotKey].classes || []
    const newClasses = currentClasses.includes(cls)
      ? currentClasses.filter((c) => c !== cls)
      : [...currentClasses, cls]

    setSlots((prev) => ({
      ...prev,
      [slotKey]: { ...prev[slotKey], classes: newClasses },
    }))
  }

  const handleMouseDown = (index, e) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.button === 2) {
      setDividers((prev) => prev.filter((_, i) => i !== index))
      return
    }
    setIsDragging(index)
    didDragRef.current = false
  }

  const handleMouseMove = (e) => {
    if (isDragging === null || !imgContainerRef.current) return
    didDragRef.current = true

    const rect = imgContainerRef.current.getBoundingClientRect()
    let pct = (e.clientX - rect.left) / rect.width
    pct = Math.max(0.02, Math.min(0.98, pct))

    setDividers((prev) => {
      const newDivs = [...prev]
      newDivs[isDragging] = pct
      return newDivs
    })
  }

  const handleMouseUp = () => {
    setIsDragging(null)
  }

  const handleImageClick = (e) => {
    if (isDragging !== null || didDragRef.current) {
      didDragRef.current = false
      return
    }

    if (dividers.length >= 5) {
      alert("Maximum of 6 slots allowed.")
      return
    }

    const rect = imgContainerRef.current.getBoundingClientRect()
    const pct = (e.clientX - rect.left) / rect.width

    if (dividers.some((d) => Math.abs(d - pct) < 0.05)) return

    setDividers((prev) => [...prev, pct])
  }

  const handleSave = async (destination) => {
    setSaveStatus("saving")

    const formattedSlots = {}
    Object.keys(slots).forEach((key) => {
      formattedSlots[key] = {
        name: slots[key].name || `Slot ${key.split("_")[1]}`,
        valid_classes: slots[key].classes,
        x_start: slots[key].x_start,
        x_end: slots[key].x_end,
        threshold: parseInt(slots[key].threshold) || 1,
      }
    })

    const payload = {
      shelf_id: shelfId,
      real_dimensions: dimensions,
      calibration: {
        source_points: sourcePoints,
        homography_matrix: matrix,
        virtual_dim: [1000, 400],
      },
      slots: formattedSlots,
      destination: destination,
    }

    try {
      await axios.post("http://localhost:8000/api/save", payload)
      setSaveStatus("success")
    } catch (err) {
      setSaveStatus("error")
      alert("Save failed: " + (err.response?.data?.detail || err.message))
    }
  }

  if (saveStatus === "success") {
    return (
      <div className="flex flex-col items-center justify-center h-[50vh] animate-in zoom-in-95">
        <div className="bg-emerald-500/10 p-6 rounded-full mb-6 border border-emerald-500/20">
          <CheckCircle size={64} className="text-emerald-400" />
        </div>
        <h2 className="text-3xl font-bold text-white mb-2">
          Configuration Saved!
        </h2>
        <p className="text-slate-400 mb-8">
          Your physical shelf is now mapped and synchronized.
        </p>
        <button
          onClick={onComplete}
          className="flex items-center gap-2 px-6 py-3 bg-accent-600 hover:bg-accent-500 text-white font-bold rounded-lg transition"
        >
          <RefreshCw size={18} /> Configure Another Shelf
        </button>
      </div>
    )
  }

  return (
    <div
      className="grid grid-cols-1 lg:grid-cols-3 gap-8 w-full max-w-7xl mx-auto p-4"
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onContextMenu={(e) => e.preventDefault()}
    >
      <div className="lg:col-span-2 flex flex-col gap-4">
        <h2 className="text-2xl font-bold text-white mb-2">Slot Editor</h2>

        <div className="bg-midnight-900 p-4 rounded-xl border border-midnight-800 shadow-xl">
          <div
            ref={imgContainerRef}
            className="relative w-full cursor-crosshair group overflow-hidden"
            onClick={handleImageClick}
          >
            <img
              src={warpedImage}
              alt="Rectified Planogram"
              className="w-full rounded-lg border border-midnight-700 pointer-events-none select-none"
              draggable={false}
            />

            {dividers.map((d, i) => (
              <div
                key={i}
                className={`absolute top-0 bottom-0 w-1 cursor-col-resize z-20 flex justify-center ${
                  isDragging === i ? "bg-yellow-400" : "bg-accent-500"
                }`}
                style={{ left: `${d * 100}%` }}
                onMouseDown={(e) => handleMouseDown(i, e)}
              >
                <div className="absolute top-1/2 -translate-y-1/2 bg-white rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <GripVertical size={12} className="text-black" />
                </div>
              </div>
            ))}

            {Object.values(slots).map((slot, i) => (
              <div
                key={i}
                className="absolute top-1/2 -translate-y-1/2 flex flex-col items-center justify-center pointer-events-none border-l border-r border-white/10"
                style={{
                  left: `${slot.x_start * 100}%`,
                  width: `${(slot.x_end - slot.x_start) * 100}%`,
                }}
              >
                <span className="bg-black/70 text-white text-[10px] px-1.5 py-0.5 rounded font-bold">
                  {slot.name || `Slot ${i + 1}`}
                </span>
                <div className="flex items-center gap-1 text-[9px] text-accent-400 bg-black/80 px-1 rounded-full border border-accent-500/30 mt-1">
                  <Ruler size={8} /> {slot.realWidth}{" "}
                  {displayUnit.toUpperCase()}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-midnight-900 p-5 rounded-xl border border-midnight-800 shadow-xl flex flex-col gap-3">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
            Quick Layouts
          </span>
          <div className="flex justify-between items-center">
            <div className="flex gap-2">
              {[2, 3, 4, 5].map((num) => (
                <button
                  key={num}
                  onClick={() => applyPreset(num)}
                  className="px-4 py-2 bg-midnight-950 border border-midnight-700 text-slate-300 rounded-lg hover:border-accent-500 hover:text-white transition text-sm font-medium"
                >
                  {num} Slots
                </button>
              ))}
            </div>

            <div className="flex bg-midnight-950 rounded-lg border border-midnight-800 p-1">
              <button
                onClick={() => setDisplayUnit("in")}
                className={`px-4 py-1.5 text-xs font-bold rounded transition ${displayUnit === "in" ? "bg-accent-600 text-white" : "text-slate-400 hover:text-white"}`}
              >
                IN
              </button>
              <button
                onClick={() => setDisplayUnit("cm")}
                className={`px-4 py-1.5 text-xs font-bold rounded transition ${displayUnit === "cm" ? "bg-accent-600 text-white" : "text-slate-400 hover:text-white"}`}
              >
                CM
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-midnight-900 border border-midnight-800 rounded-xl p-6 shadow-xl flex flex-col h-[80vh]">
        <div className="flex justify-between items-center mb-4 border-b border-midnight-800 pb-4">
          <h3 className="font-bold text-white text-lg">Configuration</h3>
          <span className="text-xs font-mono bg-midnight-800 text-slate-400 px-2 py-1 rounded">
            {dividers.length + 1} Slots
          </span>
        </div>

        <div className="space-y-4 overflow-y-auto flex-1 pr-2 custom-scrollbar">
          {Object.entries(slots).map(([key, data]) => (
            <div
              key={key}
              className="p-4 bg-midnight-950/50 rounded-lg border border-midnight-800 focus-within:border-accent-500 transition-colors"
            >
              <div className="mb-4">
                <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1">
                  Product Name
                </label>
                <input
                  className="w-full bg-midnight-900 border border-midnight-700 rounded p-2 text-sm text-white focus:ring-1 focus:ring-accent-500 outline-none"
                  value={data.name}
                  placeholder="e.g. Compliments Cookies: Chocolate Chip"
                  onChange={(e) =>
                    setSlots((prev) => ({
                      ...prev,
                      [key]: { ...data, name: e.target.value },
                    }))
                  }
                />
              </div>

              <div className="mb-4">
                <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1">
                  Low Stock Threshold
                </label>
                <input
                  type="number"
                  min="0"
                  className="w-full bg-midnight-900 border border-midnight-700 rounded p-2 text-sm text-white focus:ring-1 focus:ring-accent-500 outline-none"
                  value={data.threshold}
                  onChange={(e) =>
                    setSlots((prev) => ({
                      ...prev,
                      [key]: { ...data, threshold: e.target.value },
                    }))
                  }
                />
              </div>

              <label className="block text-[10px] font-bold text-slate-500 uppercase mb-2">
                Valid Classes
              </label>
              <div className="flex flex-wrap gap-2">
                {VALID_CLASSES.map((cls) => (
                  <button
                    key={cls}
                    onClick={() => toggleClass(key, cls)}
                    className={`text-[10px] px-2 py-1 rounded border transition-all ${
                      data.classes?.includes(cls)
                        ? "bg-accent-600 border-accent-500 text-white"
                        : "bg-midnight-800 border-midnight-700 text-slate-400"
                    }`}
                  >
                    {cls}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 flex gap-2 pt-4 border-t border-midnight-800">
          <button
            onClick={() => handleSave("local")}
            disabled={saveStatus === "saving"}
            className="flex-1 bg-midnight-800 hover:bg-midnight-700 border border-midnight-700 text-slate-300 py-3 rounded-lg font-bold flex items-center justify-center gap-2 transition disabled:opacity-50 text-sm"
          >
            <HardDrive size={16} /> Local
          </button>

          <button
            onClick={() => handleSave("firestore")}
            disabled={saveStatus === "saving"}
            className="flex-1 bg-midnight-800 hover:bg-midnight-700 border border-midnight-700 text-slate-300 py-3 rounded-lg font-bold flex items-center justify-center gap-2 transition disabled:opacity-50 text-sm"
          >
            <Cloud size={16} /> Cloud
          </button>

          <button
            onClick={() => handleSave("both")}
            disabled={saveStatus === "saving"}
            className="flex-[1.5] bg-accent-600 hover:bg-accent-500 text-white py-3 rounded-lg font-bold flex items-center justify-center gap-2 transition disabled:opacity-50 shadow-lg shadow-accent-500/20"
          >
            <RefreshCw size={18} /> Save & Sync
          </button>
        </div>
      </div>
    </div>
  )
}
