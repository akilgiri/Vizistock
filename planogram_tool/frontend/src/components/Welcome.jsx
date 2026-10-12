import React, { useEffect, useState } from "react"
import axios from "axios"
import { Layers, ChevronRight, Server, RefreshCw } from "lucide-react"

export default function Welcome({ onNext }) {
  const [cameras, setCameras] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedCam, setSelectedCam] = useState(null)

  useEffect(() => {
    setTimeout(() => {
      axios
        .get("http://localhost:8000/api/cameras")
        .then((res) => {
          const sortedCameras = res.data.sort((a, b) =>
            a.id.localeCompare(b.id),
          )
          setCameras(sortedCameras)
        })
        .catch((err) => console.error(err))
        .finally(() => setLoading(false))
    }, 800)
  }, [])

  return (
    <div className="max-w-4xl mx-auto mt-16 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="text-center mb-12">
        <h1 className="text-5xl font-bold text-white mb-4 tracking-tight select-none">
          Welcome to <span className="text-accent-500">ViziStock</span>
        </h1>
        <p className="text-slate-400 text-xl max-w-2xl mx-auto select-none">
          Your intelligent shelf system for real-time inventory tracking.
        </p>
      </div>

      <div className="bg-midnight-900 border border-midnight-800 rounded-2xl p-8 shadow-2xl">
        <div className="flex justify-between items-center mb-6 border-b border-midnight-800 pb-4">
          <h2 className="text-xl font-bold text-white flex items-center gap-2 select-none">
            <Layers className="text-accent-400" /> Select Shelf
          </h2>
          {loading && (
            <span className="flex items-center gap-2 text-xs font-mono text-accent-400">
              <RefreshCw size={14} className="animate-spin" />
              Detecting shelves...
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 gap-4">
          {cameras.map((cam) => (
            <div
              key={cam.id}
              onClick={() => setSelectedCam(cam)}
              className={`p-5 rounded-xl border-2 cursor-pointer transition-all flex justify-between items-center group ${
                selectedCam?.id === cam.id
                  ? "border-accent-500 bg-accent-500/10"
                  : "border-midnight-700 bg-midnight-800 hover:border-midnight-600 hover:bg-midnight-700"
              }`}
            >
              <div className="flex items-center gap-4">
                <div
                  className={`p-3 rounded-lg ${selectedCam?.id === cam.id ? "bg-accent-500 text-white" : "bg-midnight-700 text-slate-400"}`}
                >
                  <Server size={24} />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-200 group-hover:text-white transition">
                    {cam.name}
                  </h3>
                  <p className="text-sm text-slate-500 mt-1">Ready for setup</p>
                </div>
              </div>
              <div
                className={`w-5 h-5 rounded-full border-2 transition ${selectedCam?.id === cam.id ? "bg-accent-500 border-accent-500 shadow-[0_0_10px_rgba(59,130,246,0.8)]" : "border-slate-600"}`}
              />
            </div>
          ))}
        </div>

        <div className="mt-8 flex justify-end">
          <button
            onClick={() => onNext(selectedCam)}
            disabled={!selectedCam}
            className="flex items-center gap-2 px-8 py-3 bg-accent-600 hover:bg-accent-500 text-white font-bold rounded-xl disabled:opacity-50 disabled:cursor-not-allowed transition shadow-lg shadow-accent-500/20 select-none"
          >
            Configure Planogram <ChevronRight size={18} />
          </button>
        </div>
      </div>
    </div>
  )
}
