import { useState, useEffect } from 'react'

export default function DroneFootage({ active }) {
  const [signalLost, setSignalLost] = useState(false)

  // Simulate occasional signal jitter
  useEffect(() => {
    if (!active) return;
    const interval = setInterval(() => {
      if (Math.random() > 0.8) {
        setSignalLost(true)
        setTimeout(() => setSignalLost(false), Math.random() * 800 + 200)
      }
    }, 4000)
    return () => clearInterval(interval)
  }, [active])

  if (!active) {
    return (
      <div className="w-full h-full bg-black flex flex-col justify-center items-center text-slate-600 relative overflow-hidden">
        {/* TV Static noise pattern purely in CSS could go here, but keep it minimal */}
        <div className="absolute inset-0 opacity-[0.03] bg-[url('https://www.transparenttextures.com/patterns/stardust.png')] mix-blend-overlay"></div>
        <span className="font-mono text-xs tracking-[0.2em] relative z-10">NO SIGNAL</span>
      </div>
    )
  }

  return (
    <div className="w-full h-full relative group pb-0">
      <img
        src="/drone_feed.png"
        alt="Drone Feed"
        className={`w-full h-full object-cover transition-opacity duration-300 ${signalLost ? 'opacity-30' : 'opacity-100'} filter saturate-150 contrast-125`}
      />

      {/* Glitch Overlay */}
      {signalLost && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/60 backdrop-blur-[1px]">
          <span className="text-red-500 font-mono text-sm tracking-widest animate-pulse drop-shadow-md">
            SIGNAL INTERFERENCE
          </span>
        </div>
      )}

      {/* Target Crosshair / YOLO BBox overlay (Mocked) */}
      {!signalLost && (
        <div className="absolute top-[40%] left-[50%] w-24 h-24 border-2 border-red-500/80 -translate-x-1/2 -translate-y-1/2 shadow-[0_0_15px_rgba(239,68,68,0.5)] bg-red-500/10">
          <span className="absolute -top-6 left-0 text-[10px] text-red-500 font-mono font-bold bg-black/60 px-1">FIRE 96%</span>
        </div>
      )}

      {/* HUD Info */}
      <div className="absolute top-2 left-3 right-3 flex justify-between items-start pointer-events-none drop-shadow-md">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></div>
          <span className="text-[10px] text-white font-mono tracking-wider font-bold shadow-black text-shadow">REC / CAM-01</span>
        </div>
        <span className="text-[10px] text-white font-mono bg-black/40 px-1 rounded">ALT: 120M</span>
      </div>

      {/* Scanline overlay effect */}
      <div className="absolute inset-0 pointer-events-none opacity-20 hover:opacity-10 transition-opacity bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))] bg-[length:100%_4px,3px_100%] z-20"></div>
    </div>
  )
}
