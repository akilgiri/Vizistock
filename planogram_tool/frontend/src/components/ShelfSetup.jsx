import React, { useState } from "react"
import axios from "axios"
import { Ruler, UploadCloud, Info, Camera, Loader2 } from "lucide-react"

export default function ShelfSetup({
  shelf,
  initialDims,
  initialFile,
  onNext,
}) {
  const [dims, setDims] = useState(
    initialDims || { width: 36.0, depth: 18.0, unit: "in" },
  )
  const [file, setFile] = useState(initialFile || null)
  const [isCapturing, setIsCapturing] = useState(false)

  const handleFile = (e) => {
    if (e.target.files[0]) setFile(e.target.files[0])
  }

  const handleLiveCapture = async () => {
    setIsCapturing(true)
    try {
      const res = await axios.get(
        `http://localhost:8000/api/capture?shelf_id=${shelf?.id || ""}`,
      )
      const fetchRes = await fetch(res.data.image)
      const blob = await fetchRes.blob()
      const captureFile = new File(
        [blob],
        `live_capture_${shelf?.id || "shelf"}.jpg`,
        { type: "image/jpeg" },
      )
      setFile(captureFile)
    } catch (error) {
      console.error("Live capture failed:", error)
      alert("Could not connect to shelf camera network.")
    }
    setIsCapturing(false)
  }

  return (
    <div className="max-w-5xl mx-auto mt-10 grid grid-cols-1 lg:grid-cols-2 gap-12 animate-in fade-in duration-500">
      <div className="space-y-8">
        <div>
          <h2 className="text-3xl font-bold text-white mb-4">
            Shelf Configuration
          </h2>
          <div className="bg-blue-900/20 border border-blue-800 rounded-lg p-4 text-blue-200 text-sm leading-relaxed flex gap-3">
            <Info className="shrink-0 mt-1" size={18} />
            <p>
              Accurate dimensions are critical for the{" "}
              <strong>Planogram</strong> to map physical space to digital slots.
            </p>
          </div>
        </div>

        <div className="bg-midnight-900 border border-midnight-800 rounded-xl p-6 shadow-xl">
          <h3 className="text-white font-semibold flex items-center gap-2 mb-6">
            <Ruler className="text-accent-500" /> Physical Dimensions
          </h3>

          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase mb-2">
                Width
              </label>
              <input
                type="number"
                step="any"
                min="0"
                value={dims.width}
                onChange={(e) => setDims({ ...dims, width: e.target.value })}
                className="w-full bg-midnight-800 border border-midnight-700 rounded-lg p-3 text-white focus:ring-2 focus:ring-accent-500 outline-none transition"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase mb-2">
                Depth
              </label>
              <input
                type="number"
                step="any"
                min="0"
                value={dims.depth}
                onChange={(e) => setDims({ ...dims, depth: e.target.value })}
                className="w-full bg-midnight-800 border border-midnight-700 rounded-lg p-3 text-white focus:ring-2 focus:ring-accent-500 outline-none transition"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase mb-2">
              Unit
            </label>
            <div className="flex gap-4">
              {["in", "cm"].map((u) => (
                <button
                  key={u}
                  onClick={() => setDims({ ...dims, unit: u })}
                  className={`flex-1 py-2 rounded-lg border text-sm font-medium transition uppercase ${
                    dims.unit === u
                      ? "bg-accent-500 border-accent-500 text-white"
                      : "bg-midnight-800 border-midnight-700 text-slate-400 hover:border-slate-500"
                  }`}
                >
                  {u}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="flex flex-col justify-center">
        {/* Adjusted padding from p-8 to p-6 to save vertical space */}
        <div className="bg-midnight-900 border border-midnight-800 rounded-xl p-6 text-center shadow-xl h-fit">
          {/* Adjusted icon size to be slightly more compact */}
          <div className="w-12 h-12 bg-midnight-800 rounded-full flex items-center justify-center mx-auto mb-4 text-accent-500">
            <UploadCloud size={24} />
          </div>
          <h3 className="text-xl font-bold text-white mb-2">Reference View</h3>
          {/* Adjusted bottom margin from mb-8 to mb-5 */}
          <p className="text-slate-400 text-sm mb-5 px-4 leading-relaxed">
            Please capture or upload a{" "}
            <strong className="text-white">reference snapshot</strong> from the
            camera feed of the empty shelf.
          </p>

          <button
            onClick={handleLiveCapture}
            disabled={isCapturing}
            className="w-full mb-4 flex items-center justify-center gap-2 py-3 bg-midnight-800 hover:bg-midnight-700 border border-midnight-700 text-white font-bold rounded-lg transition disabled:opacity-50"
          >
            {isCapturing ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              <Camera size={18} />
            )}
            {isCapturing ? "Snapping..." : "Capture Live from Shelf"}
          </button>

          <label className="block w-full cursor-pointer group">
            {/* Adjusted padding from p-8 to p-6 inside the dropzone */}
            <div className="border-2 border-dashed border-midnight-700 rounded-xl p-6 hover:border-accent-500 hover:bg-midnight-800/50 transition flex flex-col items-center">
              {file ? (
                <div className="relative w-full flex justify-center">
                  <img
                    src={URL.createObjectURL(file)}
                    // Reduced max-h slightly to ensure it doesn't blow out the container height
                    className="w-full max-h-40 object-cover rounded shadow-lg opacity-80 group-hover:opacity-100 transition"
                    alt="Preview"
                  />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="bg-black/60 text-white px-3 py-1 rounded text-sm backdrop-blur-sm opacity-0 group-hover:opacity-100 transition">
                      Change File
                    </span>
                  </div>
                </div>
              ) : (
                <span className="text-slate-500 group-hover:text-accent-400 transition font-medium py-4">
                  Click to upload .jpg / .png
                </span>
              )}
            </div>
            <input
              type="file"
              className="hidden"
              onChange={handleFile}
              accept="image/*"
            />
          </label>

          {/* Adjusted top margin from mt-8 to mt-5 */}
          <button
            onClick={() => {
              const formattedDims = {
                ...dims,
                width: parseFloat(dims.width) || 0,
                depth: parseFloat(dims.depth) || 0,
              }
              onNext(formattedDims, file)
            }}
            disabled={!file}
            className="w-full mt-5 py-3 bg-accent-600 hover:bg-accent-500 text-white font-bold rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition shadow-lg shadow-accent-500/20"
          >
            {file ? "Begin Calibration" : "Upload to Continue"}
          </button>
        </div>
      </div>
    </div>
  )
}
