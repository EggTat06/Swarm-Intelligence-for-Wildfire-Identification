import { useState, useEffect, useRef } from 'react';
import { ShieldAlert, Activity, Wifi, Settings, Plus, Minus, Flame } from 'lucide-react';
import MapGrid from './components/MapGrid';
import NotificationsPanel from './components/NotificationsPanel';
import DroneFootage from './components/DroneFootage';

function App() {
  const [missionActive, setMissionActive] = useState(false);
  const [isConnected, setIsConnected] = useState(false);

  const [envState, setEnvState] = useState(null);
  const [drones, setDrones] = useState({});
  const [identifiedFires, setIdentifiedFires] = useState([]);

  const wsRef = useRef(null);

  useEffect(() => {
    wsRef.current = new WebSocket("ws://localhost:8000/ws");

    wsRef.current.onopen = () => setIsConnected(true);
    wsRef.current.onclose = () => setIsConnected(false);

    wsRef.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "environment_state") {
          setEnvState(data);
        } else if (data.type === "swarm_telemetry") {
          // Batch process drones
          const newDrones = {};
          data.drones.forEach(d => {
              newDrones[d.drone_id] = d;
          });
          setDrones(newDrones);
          setIdentifiedFires(data.discovered_fires || []);
        }
      } catch (err) {
        console.error("Failed to parse WS message:", err);
      }
    };

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const handleToggleMission = () => {
    const newState = !missionActive;
    setMissionActive(newState);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
       wsRef.current.send(JSON.stringify({ type: "command", command: newState ? "DEPLOY" : "ABORT" }));
    }
  };

  const handleSwarmControl = (action) => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: "swarm_control", action }));
       }
  }

  const activeDroneCount = Object.keys(drones).length;
  // Performance Metric
  const totalFires = envState?.fires?.length || 0;
  const identifiedCount = identifiedFires.length;

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
            <Wifi className={`w-4 h-4 ${isConnected ? 'text-emerald-400' : 'text-red-500'}`} />
            <span>Connection: {isConnected ? 'Secure' : 'Disconnected'}</span>
          </div>

          <div className="flex items-center gap-2 border-x border-white/10 px-4">
               <button onClick={() => handleSwarmControl('remove')} className="p-1 hover:bg-white/10 rounded">
                   <Minus className="w-4 h-4 text-slate-300" />
               </button>
               <span className="font-mono text-sm w-12 text-center text-emerald-400">{activeDroneCount} UAVs</span>
               <button onClick={() => handleSwarmControl('add')} className="p-1 hover:bg-white/10 rounded">
                   <Plus className="w-4 h-4 text-slate-300" />
               </button>
          </div>

          <button
            onClick={handleToggleMission}
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
          <MapGrid active={missionActive} envState={envState} drones={drones} identifiedFires={identifiedFires} />

          {/* Overlay Stats */}
          <div className="absolute top-4 left-4 p-4 rounded-xl bg-card/80 backdrop-blur border border-white/5 shadow-2xl space-y-3">
            <div className="flex items-center gap-2 text-sm text-slate-400 font-medium">
              <Activity className="w-4 h-4 text-emerald-400" />
              <span>SWARM STATUS</span>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-slate-500">Active Drones</p>
                <p className="text-xl font-bold font-mono">{activeDroneCount}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Performance</p>
                <p className="text-xl font-bold font-mono text-amber-400">
                   {identifiedCount} / {totalFires}
                </p>
              </div>
            </div>
            {envState && (
              <div className="pt-2 mt-2 border-t border-white/10">
                <p className="text-xs text-slate-500 flex items-center gap-1">
                  <Flame className="w-3 h-3 text-red-500" /> Wildfires Active
                </p>
                <div className="flex justify-between text-xs font-mono mt-1 text-slate-300">
                   <span>Detected: {((identifiedCount/Math.max(1, totalFires))*100).toFixed(1)}%</span>
                </div>
              </div>
            )}
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
