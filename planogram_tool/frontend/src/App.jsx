import React, { useState } from "react"
import Welcome from "./components/Welcome"
import ShelfSetup from "./components/ShelfSetup"
import Calibration from "./components/Calibration"
import SlotEditor from "./components/SlotEditor"
import { Server, Ruler, Crosshair, Grid } from "lucide-react"

export default function App() {
  const [step, setStep] = useState(1)
  const [data, setData] = useState({
    shelf: null,
    dimensions: null,
    file: null,
    calibration: null,
  })

  const handleHardwareSelect = (shelf) => {
    setData((prev) => ({ ...prev, shelf }))
    setStep(2)
  }

  const handleSetupComplete = (dimensions, file) => {
    setData((prev) => ({ ...prev, dimensions, file }))
    setStep(3)
  }

  const handleCalibrationDone = (warpedImg, matrix, points) => {
    setData((prev) => ({ ...prev, calibration: { warpedImg, matrix, points } }))
    setStep(4)
  }

  const handleBack = () => {
    if (step > 1) setStep(step - 1)
  }

  // --- BREADCRUMB LOGIC ---
  const navigateToStep = (targetStep) => {
    if (targetStep < step) {
      setStep(targetStep)
    }
  }

  const handleReset = () => {
    setData({ shelf: null, dimensions: null, file: null, calibration: null })
    setStep(1)
  }

  const steps = [
    { num: 1, label: "Hardware", icon: Server },
    { num: 2, label: "Context", icon: Ruler },
    { num: 3, label: "Calibrate", icon: Crosshair },
    { num: 4, label: "Planogram", icon: Grid },
  ]

  return (
    <div className="min-h-screen bg-midnight-950 flex flex-col font-sans">
      {step > 1 && (
        <header className="bg-midnight-900 border-b border-midnight-800 p-4 flex justify-between items-center shadow-lg">
          <div className="flex items-center gap-2">
            {steps.map((s) => (
              <div key={s.num} className="flex items-center">
                <div
                  onClick={() => navigateToStep(s.num)}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg font-bold transition ${
                    step === s.num
                      ? "bg-accent-500 text-white"
                      : step > s.num
                        ? "bg-emerald-500/20 text-emerald-400 cursor-pointer hover:bg-emerald-500/30"
                        : "text-slate-600 cursor-not-allowed"
                  }`}
                >
                  <s.icon size={16} />
                  <span className="font-medium text-sm">{s.label}</span>
                </div>
                {s.num < 4 && (
                  <div className="w-4 h-[1px] bg-midnight-800 mx-2" />
                )}
              </div>
            ))}
          </div>
          <div className="text-right">
            <h3 className="text-white font-bold">{data.shelf?.name}</h3>
          </div>
        </header>
      )}

      <div className="flex-1">
        {step === 1 && <Welcome onNext={handleHardwareSelect} />}

        {step === 2 && (
          <ShelfSetup
            shelf={data.shelf}
            initialDims={data.dimensions}
            initialFile={data.file}
            onNext={handleSetupComplete}
            onBack={handleBack}
          />
        )}

        {step === 3 && (
          <Calibration
            file={data.file}
            onNext={handleCalibrationDone}
            onBack={handleBack}
          />
        )}

        {step === 4 && (
          <SlotEditor
            shelfId={data.shelf.id}
            warpedImage={data.calibration.warpedImg}
            matrix={data.calibration.matrix}
            sourcePoints={data.calibration.points}
            dimensions={data.dimensions}
            onBack={handleBack}
            onComplete={handleReset}
          />
        )}
      </div>
    </div>
  )
}
