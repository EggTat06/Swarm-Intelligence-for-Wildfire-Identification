import { useState } from 'react';
import { ShieldAlert, Activity, Wifi, Settings } from 'lucide-react';
import MapGrid from './components/MapGrid';
import NotificationsPanel from './components/NotificationsPanel';
import DroneFootage from './components/DroneFootage';

function App() {
  const [missionActive, setMissionActive] = useState(false);

  return (
    <div className="flex flex-col h-screen bg-dark text-slate-100 font-sans overflow-hidden">
      {/* Top Navbar */}
      <header className="h-16 border-b border-white/10 flex items-center justify-between px-6 bg-card/80 backdrop-blur-md z-10">
        <div className="flex items-center gap-3">
          <ShieldAlert className="text-primary w-6 h-6" />
          <h1 className="text-xl font-bold tracking-wider text-slate-50 uppercase shadow-amber-500 text-shadow-sm">Swarm Commander</h1>
        </div>

        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Wifi className="w-4 h-4 text-emerald-400" />
            <span>Connection: Secure</span>
          </div>
          <button
            onClick={() => setMissionActive(!missionActive)}
            className={`px-6 py-2 rounded-full font-semibold transition-all duration-300 ${missionActive ? 'bg-red-500 hover:bg-red-600 text-white shadow-[0_0_15px_rgba(239,68,68,0.5)]' : 'bg-primary hover:bg-orange-600 text-white shadow-[0_0_15px_rgba(255,69,0,0.5)]'}`}
          >
            {missionActive ? 'ABORT MISSION' : 'DEPLOY SWARM'}
          </button>
          <button className="p-2 hover:bg-white/5 rounded-full transition text-slate-400">
            <Settings className="w-5 h-5" />
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left Panel: 3D Map Grid */}
        <section className="flex-1 relative bg-dark">
          <MapGrid active={missionActive} />

          {/* Overlay Stats */}
          <div className="absolute top-4 left-4 p-4 rounded-xl bg-card/80 backdrop-blur border border-white/5 shadow-2xl space-y-3">
            <div className="flex items-center gap-2 text-sm text-slate-400 font-medium">
              <Activity className="w-4 h-4 text-emerald-400" />
              <span>SWARM STATUS</span>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-slate-500">Active Drones</p>
                <p className="text-xl font-bold font-mono">24 / 24</p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Coverage</p>
                <p className="text-xl font-bold font-mono">14.2 km²</p>
              </div>
            </div>
          </div>
        </section>

        {/* Right Panel: Data & Video */}
        <aside className="w-[420px] bg-card border-l border-white/5 flex flex-col z-10 shadow-[-10px_0_30px_rgba(0,0,0,0.5)]">
          {/* Top Half: Video Feed */}
          <div className="h-[40%] border-b border-white/5 relative p-4 pb-0 flex flex-col">
            <h2 className="text-sm font-semibold tracking-widest text-slate-400 mb-3 uppercase">Optical Feed (YOLOv8)</h2>
            <div className="flex-1 mb-4 rounded-xl overflow-hidden shadow-inner border border-white/10">
              <DroneFootage active={missionActive} />
            </div>
          </div>

          {/* Bottom Half: Notifications */}
          <div className="flex-1 flex flex-col p-4 relative overflow-hidden">
            <h2 className="text-sm font-semibold tracking-widest text-slate-400 mb-3 uppercase flex justify-between">
              <span>Alert Log</span>
              <span className="bg-red-500/20 text-red-400 px-2 py-0.5 rounded text-xs">Live</span>
            </h2>
            <NotificationsPanel active={missionActive} />
          </div>
        </aside>
      </main>
    </div>
  )
}

export default App
